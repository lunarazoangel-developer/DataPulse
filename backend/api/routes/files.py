from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import Dict, List

from core.data_loader import DataLoader
from core.database_manager import DatabaseError, DatabaseManager
from core.schema_analyzer import SchemaAnalyzer
from .. import session

router = APIRouter()
data_loader = DataLoader()
schema_analyzer = SchemaAnalyzer()
db_manager = DatabaseManager()


def _load_database_into_session(session_id: str, db_name: str) -> Dict:
    if not db_manager.database_exists(db_name):
        raise HTTPException(status_code=404, detail=f"Database '{db_name}' not found")

    file_paths = db_manager.list_files(db_name)
    if not file_paths:
        raise HTTPException(
            status_code=400,
            detail=f"Database '{db_name}' has no supported files",
        )

    loaded_data: Dict = {}
    for file_path in file_paths:
        file_data = data_loader.load_single_file(file_path)
        loaded_data.update(file_data)

    session.data_store[session_id] = loaded_data
    session.current_database[session_id] = db_name

    info = db_manager.update_meta_from_loaded(
        db_name, loaded_data, file_count=len(file_paths)
    )

    relationships = schema_analyzer.detect_relationships(loaded_data)
    session.relationships_store[session_id] = relationships

    sensitive_cols = DataLoader.detect_sensitive_columns(loaded_data)
    session.sensitive_columns_store[session_id] = sensitive_cols

    return {
        "database": db_name,
        "tables": list(loaded_data.keys()),
        "table_count": len(loaded_data),
        "relationships_count": len(relationships),
        "database_info": info.to_dict(),
    }


@router.post("/upload")
async def upload_files(files: List[UploadFile] = File(...)) -> Dict:
    session_id = "default"

    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    try:
        info = db_manager.create_database()
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))

    saved_paths: List[str] = []
    for uploaded_file in files:
        file_content = await uploaded_file.read()
        filename = uploaded_file.filename or "unnamed"
        try:
            path = db_manager.save_file(info.name, file_content, filename)
            saved_paths.append(path)
        except DatabaseError as e:
            raise HTTPException(status_code=500, detail=str(e))
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"Error saving {filename}: {str(e)}"
            )

    try:
        result = _load_database_into_session(session_id, info.name)
    except HTTPException:
        try:
            db_manager.delete_database(info.name)
        except DatabaseError:
            pass
        raise
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error loading files: {str(e)}")

    return {
        "message": f"Database '{info.name}' created with {len(saved_paths)} file(s)",
        "database": info.name,
        "tables": result["tables"],
        "table_count": result["table_count"],
        "relationships_count": result["relationships_count"],
    }


@router.get("/tables")
async def get_tables() -> Dict:
    session_id = "default"
    data = session.data_store.get(session_id, {})
    database = session.current_database.get(session_id)

    tables = []
    for table_name, df in data.items():
        tables.append(
            {
                "name": table_name,
                "rows": df.height,
                "columns": df.width,
                "column_names": df.columns,
            }
        )

    return {"database": database, "tables": tables}


@router.delete("/clear")
async def clear_data() -> Dict:
    session_id = "default"

    session.data_store[session_id] = {}
    session.current_database[session_id] = ""
    session.sensitive_columns_store[session_id] = {}
    session.relationships_store[session_id] = []

    return {
        "message": "In-memory session cleared. Saved databases on disk are still available."
    }
