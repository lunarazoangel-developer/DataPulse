from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import List, Dict
import os

from core.data_loader import DataLoader
from core.schema_analyzer import SchemaAnalyzer
from .. import session

router = APIRouter()
data_loader = DataLoader()
schema_analyzer = SchemaAnalyzer()


@router.post("/upload")
async def upload_files(files: List[UploadFile] = File(...)) -> Dict:
    session_id = "default"

    if session_id in session.data_store:
        session.data_store[session_id] = {}
    if session_id in session.file_paths:
        for old_path in session.file_paths.get(session_id, []):
            if os.path.exists(old_path):
                os.remove(old_path)
        session.file_paths[session_id] = []
    else:
        session.data_store[session_id] = {}
        session.file_paths[session_id] = []

    loaded_data = {}
    file_paths_list = []

    for uploaded_file in files:
        file_content = await uploaded_file.read()
        filename = uploaded_file.filename

        try:
            file_path = data_loader.save_file(file_content, filename)
            file_paths_list.append(file_path)

            file_data = data_loader.load_single_file(file_path)
            loaded_data.update(file_data)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Error loading {filename}: {str(e)}")

    session.data_store[session_id] = loaded_data
    session.file_paths[session_id] = file_paths_list

    relationships = schema_analyzer.detect_relationships(loaded_data)
    session.relationships_store[session_id] = relationships

    sensitive_cols = DataLoader.detect_sensitive_columns(loaded_data)
    session.sensitive_columns_store[session_id] = sensitive_cols

    return {
        "message": f"Loaded {len(loaded_data)} table(s) successfully",
        "tables": list(loaded_data.keys()),
        "table_count": len(loaded_data),
        "relationships_count": len(relationships)
    }


@router.get("/tables")
async def get_tables() -> Dict:
    session_id = "default"
    data = session.data_store.get(session_id, {})

    tables = []
    for table_name, df in data.items():
        tables.append({
            "name": table_name,
            "rows": df.height,
            "columns": df.width,
            "column_names": df.columns
        })

    return {"tables": tables}


@router.delete("/clear")
async def clear_data() -> Dict:
    session_id = "default"

    for file_path in session.file_paths.get(session_id, []):
        if os.path.exists(file_path):
            os.remove(file_path)

    data_dir = "data"
    if os.path.exists(data_dir):
        for filename in os.listdir(data_dir):
            file_path = os.path.join(data_dir, filename)
            if os.path.isfile(file_path):
                os.remove(file_path)

    session.data_store[session_id] = {}
    session.file_paths[session_id] = []
    session.sensitive_columns_store[session_id] = {}
    session.relationships_store[session_id] = []

    return {"message": "All data cleared successfully"}
