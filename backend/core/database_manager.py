import json
import os
import re
from datetime import datetime
from typing import Dict, List, Optional

import polars as pl


META_FILENAME = "meta.json"
SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


class DatabaseError(Exception):
    pass


class DatabaseInfo:
    def __init__(
        self,
        name: str,
        path: str,
        created_at: str,
        tables: List[Dict],
        file_count: int,
        total_rows: int,
    ):
        self.name = name
        self.path = path
        self.created_at = created_at
        self.tables = tables
        self.file_count = file_count
        self.total_rows = total_rows

    def to_dict(self) -> Dict:
        return {
            "name": self.name,
            "created_at": self.created_at,
            "tables": self.tables,
            "table_count": len(self.tables),
            "file_count": self.file_count,
            "total_rows": self.total_rows,
        }


class DatabaseManager:
    def __init__(self, data_root: str = "data"):
        self.data_root = data_root
        if not os.path.exists(self.data_root):
            os.makedirs(self.data_root, exist_ok=True)

    @staticmethod
    def _timestamp() -> str:
        return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    @staticmethod
    def _is_safe_name(name: str) -> bool:
        if not name:
            return False
        return re.fullmatch(r"[A-Za-z0-9_\-]+", name) is not None

    def _db_path(self, name: str) -> str:
        return os.path.join(self.data_root, name)

    def _meta_path(self, name: str) -> str:
        return os.path.join(self._db_path(name), META_FILENAME)

    def list_databases(self) -> List[DatabaseInfo]:
        databases: List[DatabaseInfo] = []
        if not os.path.isdir(self.data_root):
            return databases

        for entry in sorted(os.listdir(self.data_root), reverse=True):
            full = os.path.join(self.data_root, entry)
            if not os.path.isdir(full):
                continue
            if not self._is_safe_name(entry):
                continue
            info = self._read_meta(entry)
            if info is not None:
                databases.append(info)
        return databases

    def _read_meta(self, name: str) -> Optional[DatabaseInfo]:
        meta_file = self._meta_path(name)
        path = self._db_path(name)
        if not os.path.isdir(path):
            return None
        if os.path.isfile(meta_file):
            try:
                with open(meta_file, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                return DatabaseInfo(
                    name=name,
                    path=path,
                    created_at=meta.get("created_at", ""),
                    tables=meta.get("tables", []),
                    file_count=meta.get("file_count", 0),
                    total_rows=meta.get("total_rows", 0),
                )
            except (json.JSONDecodeError, OSError):
                pass
        return self._build_info_from_disk(name, path)

    def _build_info_from_disk(self, name: str, path: str) -> DatabaseInfo:
        files = [
            f
            for f in os.listdir(path)
            if os.path.isfile(os.path.join(path, f))
            and not f == META_FILENAME
            and os.path.splitext(f)[1].lower() in SUPPORTED_EXTENSIONS
        ]
        try:
            created_at = datetime.fromtimestamp(
                os.path.getmtime(path)
            ).isoformat(timespec="seconds")
        except OSError:
            created_at = ""
        return DatabaseInfo(
            name=name,
            path=path,
            created_at=created_at,
            tables=[],
            file_count=len(files),
            total_rows=0,
        )

    def create_database(self) -> DatabaseInfo:
        name = self._timestamp()
        path = self._db_path(name)
        os.makedirs(path, exist_ok=True)
        info = DatabaseInfo(
            name=name,
            path=path,
            created_at=datetime.now().isoformat(timespec="seconds"),
            tables=[],
            file_count=0,
            total_rows=0,
        )
        self._write_meta(info)
        return info

    def database_exists(self, name: str) -> bool:
        return self._is_safe_name(name) and os.path.isdir(self._db_path(name))

    def save_file(self, db_name: str, file_content: bytes, filename: str) -> str:
        if not self.database_exists(db_name):
            raise DatabaseError(f"Database '{db_name}' does not exist")

        safe_name = os.path.basename(filename)
        target = os.path.join(self._db_path(db_name), safe_name)
        base, ext = os.path.splitext(safe_name)
        counter = 1
        while os.path.exists(target):
            target = os.path.join(
                self._db_path(db_name), f"{base}_{counter}{ext}"
            )
            counter += 1

        with open(target, "wb") as f:
            f.write(file_content)
        return target

    def list_files(self, db_name: str) -> List[str]:
        if not self.database_exists(db_name):
            raise DatabaseError(f"Database '{db_name}' does not exist")
        path = self._db_path(db_name)
        files = []
        for entry in sorted(os.listdir(path)):
            full = os.path.join(path, entry)
            if (
                os.path.isfile(full)
                and entry != META_FILENAME
                and os.path.splitext(entry)[1].lower() in SUPPORTED_EXTENSIONS
            ):
                files.append(full)
        return files

    def update_meta_from_loaded(
        self,
        db_name: str,
        loaded_data: Dict[str, pl.DataFrame],
        file_count: int,
    ) -> DatabaseInfo:
        tables = []
        total_rows = 0
        for table_name, df in loaded_data.items():
            tables.append(
                {
                    "name": table_name,
                    "rows": df.height,
                    "columns": df.width,
                }
            )
            total_rows += df.height
        try:
            created_at = datetime.fromtimestamp(
                os.path.getmtime(self._db_path(db_name))
            ).isoformat(timespec="seconds")
        except OSError:
            created_at = datetime.now().isoformat(timespec="seconds")

        info = DatabaseInfo(
            name=db_name,
            path=self._db_path(db_name),
            created_at=created_at,
            tables=tables,
            file_count=file_count,
            total_rows=total_rows,
        )
        self._write_meta(info)
        return info

    def _write_meta(self, info: DatabaseInfo) -> None:
        meta_file = self._meta_path(info.name)
        payload = {
            "name": info.name,
            "created_at": info.created_at,
            "tables": info.tables,
            "table_count": len(info.tables),
            "file_count": info.file_count,
            "total_rows": info.total_rows,
        }
        with open(meta_file, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)

    def delete_database(self, db_name: str) -> None:
        if not self.database_exists(db_name):
            raise DatabaseError(f"Database '{db_name}' does not exist")
        path = self._db_path(db_name)
        for entry in os.listdir(path):
            full = os.path.join(path, entry)
            if os.path.isfile(full) or os.path.islink(full):
                os.remove(full)
            elif os.path.isdir(full):
                self._rm_tree(full)
        os.rmdir(path)

    @staticmethod
    def _rm_tree(path: str) -> None:
        for entry in os.listdir(path):
            full = os.path.join(path, entry)
            if os.path.isfile(full) or os.path.islink(full):
                os.remove(full)
            elif os.path.isdir(full):
                DatabaseManager._rm_tree(full)
                os.rmdir(full)
