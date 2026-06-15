import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, Field

import config
import polars as pl

from ai.actions import SUPPORTED_ACTIONS, coerce_proposal
from ai.chat import (
    AIAvailabilityError,
    AIRuntimeError,
    PayloadTooLargeError,
    call_deepseek,
    estimate_payload_tokens,
    parse_plan,
)
from api.session import data_store, current_database, sensitive_columns_store, relationships_store
from core.ai_enricher import AIPayloadBuilder
from core.data_transformer import (
    TransformError,
    apply_proposal,
    atomic_write_csv,
    coverage_note,
    preflight_affected_rows,
)
from core.database_manager import DatabaseManager
from core.quality_audit import NumericAnomalyDetector, TextAnomalyDetector
from core.discrepancy_profiler import DiscrepancyDetector
from .analyze import categorize_by_severity


def _build_traffic_light_report(data: Dict) -> Dict:
    text_detector = TextAnomalyDetector(similarity_threshold=80.0, min_frequency=5)
    numeric_detector = NumericAnomalyDetector(iqr_multiplier=1.5, zscore_threshold=3.0)
    discrepancy_detector = DiscrepancyDetector()

    all_results: Dict = {}
    for table_name, df in data.items():
        text_results = text_detector.detect_all_columns(df)
        numeric_results = numeric_detector.detect_all_columns(df, method="both")
        discrepancy_results = discrepancy_detector.detect_all_columns(df)
        table_level_results = discrepancy_detector.detect_table_level(df)

        text_serializable: Dict = {}
        for col, results in text_results.items():
            text_serializable[col] = {}
            for key, value in results.items():
                if isinstance(value, list):
                    text_serializable[col][key] = value

        numeric_serializable: Dict = {}
        for col, results in numeric_results.items():
            numeric_serializable[col] = results

        discrepancy_serializable: Dict = {}
        for col, anomalies in discrepancy_results.items():
            discrepancy_serializable[col] = anomalies

        if (
            text_serializable
            or numeric_serializable
            or discrepancy_serializable
            or table_level_results
        ):
            all_results[table_name] = {
                "text": text_serializable,
                "numeric": numeric_serializable,
                "discrepancies": discrepancy_serializable,
                "table_level": table_level_results,
            }

    categorized = categorize_by_severity(all_results)
    return {
        "red": categorized.get("red", []),
        "yellow": categorized.get("yellow", []),
        "green": categorized.get("green", []),
    }


router = APIRouter()
db_manager = DatabaseManager()


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    payload: Dict[str, Any] = Field(default_factory=dict)
    history: List[ChatMessage] = Field(default_factory=list)
    message: Optional[str] = None
    use_ia_payload: bool = Field(
        default=True,
        description=(
            "When true (default), the backend regenerates the compact IA payload "
            "from the current in-memory tables. When false, the caller-provided "
            "`payload` is sent as-is (legacy behaviour)."
        ),
    )


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
    estimated_affected_rows: Optional[int] = None
    coverage_note: Optional[str] = None


class ApplyResponse(BaseModel):
    database: str
    applied: List[ApplyResultItem] = Field(default_factory=list)
    skipped: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[Dict[str, Any]] = Field(default_factory=list)
    table_summaries: List[Dict[str, Any]] = Field(default_factory=list)
    remaining_anomalies: List[Dict[str, Any]] = Field(default_factory=list)


@router.get("/status")
async def ai_status() -> Dict[str, Any]:
    return {
        "available": config.is_ai_enabled(),
        "model": config.DEEPSEEK_MODEL,
    }


@router.post("/chat", response_model=ChatResponse)
async def ai_chat(request: ChatRequest, response: Response) -> ChatResponse:
    if not config.is_ai_enabled():
        raise HTTPException(
            status_code=503,
            detail="AI service not configured. Set DEEPSEEK_API_KEY in backend/.env",
        )

    history = [{"role": m.role, "content": m.content} for m in request.history]

    payload_to_send: Dict[str, Any]
    if request.use_ia_payload:
        session_id = "default"
        data = data_store.get(session_id, {})
        if not data:
            raise HTTPException(status_code=404, detail="No data loaded")
        sensitive = sensitive_columns_store.get(session_id, {})
        rels = relationships_store.get(session_id, [])
        traffic_light = _build_traffic_light_report(data)
        builder = AIPayloadBuilder()
        payload_to_send = builder.build_ia_payload(
            data_dict=data,
            traffic_light_report=traffic_light,
            sensitive_columns=sensitive,
            relationships=rels,
        )
    else:
        payload_to_send = request.payload

    estimated = estimate_payload_tokens(payload_to_send, history, request.message)
    response.headers["X-Estimated-Tokens"] = str(estimated)
    response.headers["X-Token-Cap"] = str(config.get_max_input_tokens())
    response.headers["X-Payload-Mode"] = "ia" if request.use_ia_payload else "legacy"

    try:
        raw_reply = await call_deepseek(
            payload=payload_to_send,
            history=history,
            user_message=request.message,
        )
    except PayloadTooLargeError as exc:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "payload_too_large",
                "message": str(exc),
                "estimated_tokens": exc.estimated_tokens,
                "threshold": exc.threshold,
                "suggestion": (
                    "Reduce sample_size, disable noisy detectors, "
                    "sube DEEPSEEK_MAX_INPUT_TOKENS en backend/.env "
                    "o envia el reporte igual (no recomendado)."
                ),
            },
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


def _concern_key(proposal: Dict[str, Any]) -> Optional[Tuple[str, str]]:
    """Derive a (table, column) concern from a proposal so we can re-detect on it."""
    table = proposal.get("table")
    column = proposal.get("column")
    if not table or not column:
        return None
    return (table, column)


def _post_apply_scan(
    dirty_tables: Dict[str, pl.DataFrame],
    proposals: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Re-run discrepancy detectors on the modified tables.

    Returns one entry per (table, column, detection_type) that still has a
    positive ``violation_count`` after the apply step. The
    ``proposals`` argument is the normalized list (already coerced by
    ``coerce_proposal``), so we can read the table and the column
    directly.

    We do not filter by the proposal's ``action`` because actions like
    ``replace_regex`` are not the same namespace as ``detection_type``
    values like ``Format Violation`` or ``Type Mismatch``; the user and
    the IA both need to know "any remaining issue in the columns I just
    touched", not "a specific subtype".
    """
    if not dirty_tables or not proposals:
        return []

    concerns: List[Tuple[str, str]] = []
    seen = set()
    for norm in proposals:
        key = _concern_key(norm)
        if not key:
            continue
        table, column = key
        if table not in dirty_tables:
            continue
        if (table, column) in seen:
            continue
        seen.add((table, column))
        concerns.append((table, column))

    if not concerns:
        return []

    from core.discrepancy_profiler import DiscrepancyDetector

    disc_det = DiscrepancyDetector()
    by_table: Dict[str, List[str]] = {}
    for table, column in concerns:
        by_table.setdefault(table, []).append(column)

    remaining: List[Dict[str, Any]] = []
    for tname, columns in by_table.items():
        df = dirty_tables[tname]
        if df.is_empty():
            continue
        try:
            fresh = disc_det.detect_all_columns(df)
        except Exception:
            continue
        for column in columns:
            anomalies = fresh.get(column) or []
            for anom in anomalies:
                vc = int(anom.get("violation_count", 0) or 0)
                if vc <= 0:
                    continue
                remaining.append({
                    "table": tname,
                    "column": column,
                    "detection_type": anom.get("issue_type", "unknown"),
                    "severity": anom.get("severity", "yellow"),
                    "violation_count": vc,
                    "note": "Still present after apply",
                })
    return remaining


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
    normalized_for_scan: List[Dict[str, Any]] = []

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
        estimated = preflight_affected_rows(df, norm)
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
        normalized_for_scan.append(norm)
        applied.append(
            ApplyResultItem(
                id=norm["id"],
                table=table_name,
                column=norm.get("column", ""),
                action=norm["action"],
                risk=norm["risk"],
                rows_changed=rows_changed,
                rows_after=new_df.height,
                estimated_affected_rows=estimated,
                coverage_note=coverage_note(estimated, df.height),
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
        remaining_anomalies=_post_apply_scan(dirty_tables, normalized_for_scan),
    )
