import io
import os
import uuid
from typing import Dict, Union, List
import polars as pl


class DataLoader:
    def __init__(self):
        self.supported_csv_extensions = ['.csv']
        self.supported_excel_extensions = ['.xlsx', '.xls']
        self.upload_dir = "data"

    def _is_csv(self, filename: str) -> bool:
        return any(filename.lower().endswith(ext) for ext in self.supported_csv_extensions)

    def _is_excel(self, filename: str) -> bool:
        return any(filename.lower().endswith(ext) for ext in self.supported_excel_extensions)

    def _load_csv(self, file_path: str) -> pl.DataFrame:
        encodings = ['utf-8', 'latin-1', 'iso-8859-1', 'cp1252']

        for encoding in encodings:
            try:
                df = pl.read_csv(file_path, encoding=encoding, try_parse_dates=True)
                return df
            except Exception:
                continue

        df = pl.read_csv(file_path, encoding='utf-8', try_parse_dates=True)
        return df

    def _load_excel(self, file_path: str) -> Dict[str, pl.DataFrame]:
        result = {}
        excel_file = pl.read_excel(file_path, sheet_id=None)

        base_name = os.path.splitext(os.path.basename(file_path))[0]
        for sheet_name, df in excel_file.items():
            key = f"{base_name}::{sheet_name}"
            result[key] = df

        return result

    def save_file(self, file_content: bytes, filename: str) -> str:
        if not os.path.exists(self.upload_dir):
            os.makedirs(self.upload_dir)

        file_id = str(uuid.uuid4())
        safe_filename = f"{file_id}_{filename}"
        file_path = os.path.join(self.upload_dir, safe_filename)

        with open(file_path, 'wb') as f:
            f.write(file_content)

        return file_path

    def load_single_file(self, file_path: str) -> Dict[str, pl.DataFrame]:
        filename = os.path.basename(file_path)
        result = {}

        original_filename = filename
        if '_' in filename:
            parts = filename.split('_', 1)
            if len(parts) > 1 and len(parts[0]) == 36:
                original_filename = parts[1]

        if self._is_csv(original_filename):
            df = self._load_csv(file_path)
            df = self._cleanup_data(df)
            result[original_filename] = df

        elif self._is_excel(original_filename):
            sheet_dict = self._load_excel(file_path)
            for key in sheet_dict:
                sheet_dict[key] = self._cleanup_data(sheet_dict[key])
            result.update(sheet_dict)

        else:
            raise ValueError(f"Unsupported file format: {original_filename}")

        return result

    def _cleanup_data(self, df: pl.DataFrame) -> pl.DataFrame:
        if df.height == 0:
            return df

        empty_cols = []
        for col in df.columns:
            if df[col].is_null().all():
                empty_cols.append(col)
        if empty_cols:
            df = df.drop(empty_cols)

        if df.width > 0 and df.height > 0:
            non_empty_rows = []
            for i in range(df.height):
                row = df.row(i)
                if not all(v is None or (isinstance(v, str) and v.strip() == '') for v in row):
                    non_empty_rows.append(i)
            if len(non_empty_rows) < df.height:
                df = df.filter(pl.Series([i in non_empty_rows for i in range(df.height)]))

        string_cols = [col for col in df.columns if df[col].dtype == pl.Utf8]
        if string_cols:
            for col in string_cols:
                df = df.with_columns(
                    pl.col(col).str.strip_chars()
                )

        return df

    @staticmethod
    def detect_sensitive_columns(data_dict: Dict[str, pl.DataFrame]) -> Dict[str, List[str]]:
        SENSITIVE_KEYWORDS = [
            'email', 'phone', 'tel', 'mobile', 'cell',
            'salary', 'wage', 'income', 'payment', 'credit',
            'password', 'secret', 'key', 'token', 'auth',
            'ssn', 'social', 'national_id', 'passport',
            'address', 'zip', 'postal', 'dob', 'birth',
            'gender', 'race', 'religion', 'political',
            'account', 'iban', 'card', 'cvv',
            'name', 'first_name', 'last_name', 'full_name'
        ]

        sensitive_columns = {}

        for table_name, df in data_dict.items():
            table_sensitive = []

            for col in df.columns:
                col_lower = col.lower()

                for keyword in SENSITIVE_KEYWORDS:
                    if keyword in col_lower:
                        table_sensitive.append(col)
                        break

            if table_sensitive:
                sensitive_columns[table_name] = table_sensitive

        return sensitive_columns

    @staticmethod
    def to_pandas(df: pl.DataFrame):
        return df.to_pandas()

    @staticmethod
    def from_pandas(pd_df):
        return pl.from_pandas(pd_df)
