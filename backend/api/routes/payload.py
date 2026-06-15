import json
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from core.ai_enricher import AIPayloadBuilder
from core.discrepancy_profiler import DiscrepancyDetector
from core.quality_audit import NumericAnomalyDetector, TextAnomalyDetector
from core.quality_audit_helpers import MAX_SAMPLES_PER_ANOMALY

from .. import session
from .analyze import categorize_by_severity

router = APIRouter()


class SensitiveColumnsUpdate(BaseModel):
    sensitive_columns: Dict[str, List[str]]


def _format_bytes(n: float) -> str:
    n = float(n)
    for unit in ["B", "KB", "MB", "GB"]:
        if abs(n) < 1024.0:
            if unit == "B":
                return f"{int(n)} {unit}"
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} TB"


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


def _build_ia_payload(data: Dict, sensitive_columns: Dict, relationships: List) -> Dict[str, Any]:
    traffic_light = _build_traffic_light_report(data)
    builder = AIPayloadBuilder()
    return builder.build_ia_payload(
        data_dict=data,
        traffic_light_report=traffic_light,
        sensitive_columns=sensitive_columns,
        relationships=relationships,
    )


def _build_summary_payload(data: Dict, sensitive_columns: Dict, relationships: List) -> Dict[str, Any]:
    traffic_light = _build_traffic_light_report(data)
    builder = AIPayloadBuilder()
    return builder.generate_preview_payload(
        data_dict=data,
        traffic_light_report=traffic_light,
        sensitive_columns=sensitive_columns,
        relationships=relationships,
        max_sample_rows=MAX_SAMPLES_PER_ANOMALY,
        include_green=True,
        summary_only=True,
    )


@router.get("/sensitive-columns")
async def get_sensitive_columns() -> Dict:
    session_id = "default"
    sensitive_columns = session.sensitive_columns_store.get(session_id, {})
    return {"sensitive_columns": sensitive_columns}


@router.post("/sensitive-columns")
async def update_sensitive_columns(update: SensitiveColumnsUpdate) -> Dict:
    session_id = "default"
    session.sensitive_columns_store[session_id] = update.sensitive_columns
    return {"message": "Sensitive columns updated successfully"}


@router.get("/size")
async def get_payload_size() -> Dict:
    session_id = "default"
    data = session.data_store.get(session_id, {})
    sensitive_columns = session.sensitive_columns_store.get(session_id, {})
    relationships = session.relationships_store.get(session_id, [])

    if not data:
        raise HTTPException(status_code=404, detail="No data loaded")

    payload = _build_summary_payload(data, sensitive_columns, relationships)
    serialized = json.dumps(payload, indent=2, default=str)
    size_bytes = len(serialized.encode("utf-8"))

    return {
        "size_bytes": size_bytes,
        "size_human": _format_bytes(size_bytes),
        "max_samples_per_anomaly": MAX_SAMPLES_PER_ANOMALY,
        "payload_mode": "summary",
    }


@router.get("/preview")
async def get_payload_preview() -> Dict:
    session_id = "default"
    data = session.data_store.get(session_id, {})
    sensitive_columns = session.sensitive_columns_store.get(session_id, {})
    relationships = session.relationships_store.get(session_id, [])

    if not data:
        raise HTTPException(status_code=404, detail="No data loaded")

    traffic_light = _build_traffic_light_report(data)
    builder = AIPayloadBuilder()
    preview_payload = builder.generate_preview_payload(
        data_dict=data,
        traffic_light_report=traffic_light,
        sensitive_columns=sensitive_columns,
        relationships=relationships,
        max_sample_rows=MAX_SAMPLES_PER_ANOMALY,
        include_green=True,
        summary_only=True,
    )
    payload_summary = builder.generate_summary(
        data_dict=data,
        sensitive_columns=sensitive_columns,
        traffic_light_report=traffic_light,
    )

    return {
        "payload": preview_payload,
        "summary": payload_summary,
    }


@router.get("/download")
async def download_payload() -> Dict:
    session_id = "default"
    data = session.data_store.get(session_id, {})
    sensitive_columns = session.sensitive_columns_store.get(session_id, {})
    relationships = session.relationships_store.get(session_id, [])

    if not data:
        raise HTTPException(status_code=404, detail="No data loaded")

    preview_payload = _build_summary_payload(data, sensitive_columns, relationships)
    serialized = json.dumps(preview_payload, indent=2, default=str)
    size_bytes = len(serialized.encode("utf-8"))

    return {
        "json": serialized,
        "size_bytes": size_bytes,
        "size_human": _format_bytes(size_bytes),
    }


@router.get("/ia-context")
async def get_ia_context() -> Dict:
    """Return the exact compact payload the IA receives (without sending it).

    Useful for debugging and for showing the user "this is what the AI sees".
    """
    session_id = "default"
    data = session.data_store.get(session_id, {})
    sensitive_columns = session.sensitive_columns_store.get(session_id, {})
    relationships = session.relationships_store.get(session_id, [])

    if not data:
        raise HTTPException(status_code=404, detail="No data loaded")

    payload = _build_ia_payload(data, sensitive_columns, relationships)
    return {"payload": payload, "payload_mode": "ia"}


@router.get("/ia-size")
async def get_ia_size() -> Dict:
    """Estimate the size in bytes (and tokens) of the IA payload alone."""
    session_id = "default"
    data = session.data_store.get(session_id, {})
    sensitive_columns = session.sensitive_columns_store.get(session_id, {})
    relationships = session.relationships_store.get(session_id, [])

    if not data:
        raise HTTPException(status_code=404, detail="No data loaded")

    payload = _build_ia_payload(data, sensitive_columns, relationships)
    serialized = json.dumps(payload, indent=2, default=str)
    size_bytes = len(serialized.encode("utf-8"))
    estimated_tokens = (size_bytes + 3) // 4

    return {
        "size_bytes": size_bytes,
        "size_human": _format_bytes(size_bytes),
        "estimated_tokens": estimated_tokens,
        "payload_mode": "ia",
    }
