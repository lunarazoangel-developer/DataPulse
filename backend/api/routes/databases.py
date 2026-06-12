from typing import Dict

from fastapi import APIRouter, HTTPException

from core.database_manager import DatabaseError, DatabaseManager
from .files import _load_database_into_session
from .. import session

router = APIRouter()
db_manager = DatabaseManager()


@router.get("")
async def list_databases() -> Dict:
    databases = db_manager.list_databases()
    return {
        "databases": [d.to_dict() for d in databases],
        "count": len(databases),
    }


@router.get("/current")
async def get_current_database() -> Dict:
    session_id = "default"
    name = session.current_database.get(session_id) or ""
    if not name:
        return {"database": None}
    return {"database": name}


@router.get("/{name}")
async def open_database(name: str) -> Dict:
    session_id = "default"
    if not db_manager.database_exists(name):
        raise HTTPException(status_code=404, detail=f"Database '{name}' not found")
    try:
        result = _load_database_into_session(session_id, name)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error opening database: {str(e)}")
    return {
        "message": f"Database '{name}' loaded into session",
        "database": result["database"],
        "tables": result["tables"],
        "table_count": result["table_count"],
        "relationships_count": result["relationships_count"],
    }


@router.delete("/{name}")
async def delete_database(name: str) -> Dict:
    if not db_manager.database_exists(name):
        raise HTTPException(status_code=404, detail=f"Database '{name}' not found")

    session_id = "default"
    if session.current_database.get(session_id) == name:
        session.data_store[session_id] = {}
        session.current_database[session_id] = ""
        session.sensitive_columns_store[session_id] = {}
        session.relationships_store[session_id] = []

    try:
        db_manager.delete_database(name)
    except DatabaseError as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"message": f"Database '{name}' deleted successfully"}
