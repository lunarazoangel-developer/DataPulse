import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

import config
import polars as pl

from ai.actions import SUPPORTED_ACTIONS, coerce_proposal
from ai.chat import (
    AIAvailabilityError,
    AIRuntimeError,
    call_deepseek,
    parse_plan,
)
from api.session import data_store, current_database
from core.data_transformer import TransformError, apply_proposal, atomic_write_csv
from core.database_manager import DatabaseManager


router = APIRouter()
db_manager = DatabaseManager()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    payload: Dict[str, Any] = Field(default_factory=dict)
    history: List[ChatMessage] = Field(default_factory=list)
    message: Optional[str] = None


class ChatResponse(BaseModel):
    message: str
    available: bool = True
    model: str
    summary: str = ""
    proposals: List[Dict[str, Any]] = Field(default_factory=list)


class ApplyRequest(BaseModel):
    database: Optional[str] = None
    proposals: List[Dict[str, Any]] = Field(default_factory=list)


class ApplyResultItem(BaseModel):
    id: str
    table: str
    column: str
    action: str
    risk: str
    rows_changed: int
    rows_after: int


class ApplyResponse(BaseModel):
    database: str
    applied: List[ApplyResultItem] = Field(default_factory=list)
    skipped: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    table_summaries: List[Dict[str, Any]] = Field(default_factory=list)


@router.get("/status")
async def ai_status() -> Dict[str, Any]:
    return {
        "available": config.is_ai_enabled(),
        "model": config.DEEPSEEK_MODEL,
    }


@router.post("/chat", response_model=ChatResponse)
async def ai_chat(request: ChatRequest) -> ChatResponse:
    if not config.is_ai_enabled():
        raise HTTPException(
            status_code=503,
            detail="AI service not configured. Set DEEPSEEK_API_KEY in backend/.env",
        )

    history = [{"role": m.role, "content": m.content} for m in request.history]

    try:
        raw_reply = await call_deepseek(
            payload=request.payload,
            history=history,
            user_message=request.message,
        )
    except AIAvailabilityError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except AIRuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    summary, proposals = parse_plan(raw_reply)

    return ChatResponse(
        message=raw_reply,
        available=True,
        model=config.DEEPSEEK_MODEL,
        summary=summary,
        proposals=proposals,
    )


def _resolve_database(requested: Optional[str]) -> str:
    """Pick the database to operate on, preferring the requested one."""
    if requested and db_manager.database_exists(requested):
        return requested
    current = current_database.get("default", "")
    if current and db_manager.database_exists(current):
        return current
    raise HTTPException(
        status_code=400,
        detail="No database loaded. Open a saved database or upload files first.",
    )


def _ensure_session_loaded(db_name: str) -> Dict[str, pl.DataFrame]:
    """Return the in-memory tables, reloading from disk if necessary."""
    session_id = "default"
    cached = data_store.get(session_id, {})
    if cached and current_database.get(session_id) == db_name:
        return cached

    from core.data_loader import DataLoader

    file_paths = db_manager.list_files(db_name)
    if not file_paths:
        raise HTTPException(
            status_code=400,
            detail=f"Database '{db_name}' has no supported files",
        )
    loader = DataLoader()
    loaded: Dict[str, pl.DataFrame] = {}
    for fp in file_paths:
        loaded.update(loader.load_single_file(fp))
    data_store[session_id] = loaded
    current_database[session_id] = db_name
    return loaded


def _build_table_file_map(db_name: str) -> Dict[str, str]:
    """Map in-memory table name -> on-disk file path."""
    mapping: Dict[str, str] = {}
    file_paths = db_manager.list_files(db_name)
    for fp in file_paths:
        fname = os.path.basename(fp)
        lower = fname.lower()
        if lower.endswith(".csv"):
            mapping[fname] = fp
        elif lower.endswith((".xlsx", ".xls")):
            try:
                sheets = pl.read_excel(fp, sheet_id=None)
            except Exception:
                continue
            base = os.path.splitext(fname)[0]
            for sheet_name in sheets.keys():
                mapping[f"{base}::{sheet_name}"] = fp
    return mapping


def _file_path_for_table(db_name: str, table_name: str, file_map: Dict[str, str]) -> Optional[str]:
    return file_map.get(table_name)


@router.post("/apply", response_model=ApplyResponse)
async def ai_apply(request: ApplyRequest) -> ApplyResponse:
    if not request.proposals:
        raise HTTPException(status_code=400, detail="No proposals provided")

    db_name = _resolve_database(request.database)
    tables = _ensure_session_loaded(db_name)
    file_map = _build_table_file_map(db_name)

    applied: List[ApplyResultItem] = []
    skipped: List[Dict[str, Any]] = []
    errors: List[Dict[str, Any]] = []

    dirty_tables: Dict[str, pl.DataFrame] = {}

    for raw in request.proposals:
        norm = coerce_proposal(raw)
        if not norm:
            errors.append(
                {
                    "id": raw.get("id") if isinstance(raw, dict) else None,
                    "reason": "Unsupported action or invalid proposal",
                }
            )
            continue
        if norm["action"] not in SUPPORTED_ACTIONS:
            skipped.append({"id": norm["id"], "reason": "Action not in supported set"})
            continue

        table_name = norm.get("table")
        if not table_name or table_name not in tables:
            errors.append(
                {"id": norm["id"], "table": table_name, "reason": f"Table '{table_name}' not found"}
            )
            continue

        df = dirty_tables.get(table_name, tables[table_name])
        try:
            new_df, rows_changed = apply_proposal(df, norm)
        except TransformError as exc:
            errors.append(
                {
                    "id": norm["id"],
                    "table": table_name,
                    "column": norm.get("column"),
                    "action": norm["action"],
                    "reason": str(exc),
                }
            )
            continue
        except Exception as exc:
            errors.append(
                {
                    "id": norm["id"],
                    "table": table_name,
                    "column": norm.get("column"),
                    "action": norm["action"],
                    "reason": f"Unexpected error: {exc}",
                }
            )
            continue

        dirty_tables[table_name] = new_df
        applied.append(
            ApplyResultItem(
                id=norm["id"],
                table=table_name,
                column=norm.get("column", ""),
                action=norm["action"],
                risk=norm["risk"],
                rows_changed=rows_changed,
                rows_after=new_df.height,
            )
        )

    for table_name, new_df in dirty_tables.items():
        file_path = _file_path_for_table(db_name, table_name, file_map)
        if not file_path:
            errors.append(
                {
                    "table": table_name,
                    "reason": "Could not resolve on-disk path for this table",
                }
            )
            tables[table_name] = new_df
            continue
        if not file_path.lower().endswith(".csv"):
            errors.append(
                {
                    "table": table_name,
                    "reason": "Persisting changes to Excel files is not supported in v1 (re-upload as CSV)",
                }
            )
            tables[table_name] = new_df
            continue
        try:
            atomic_write_csv(new_df, file_path)
        except Exception as exc:
            errors.append(
                {
                    "table": table_name,
                    "reason": f"Failed to persist CSV: {exc}",
                }
            )
        tables[table_name] = new_df

    data_store["default"] = tables
    current_database["default"] = db_name

    table_summaries: List[Dict[str, Any]] = []
    for tname, df in tables.items():
        table_summaries.append(
            {"table": tname, "rows": df.height, "columns": df.width}
        )
    try:
        db_manager.update_meta_from_loaded(
            db_name, tables, file_count=len(db_manager.list_files(db_name))
        )
    except Exception:
        pass

    return ApplyResponse(
        database=db_name,
        applied=applied,
        skipped=skipped,
        errors=errors,
        table_summaries=table_summaries,
    )
