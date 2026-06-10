from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, List
import json

from core.ai_enricher import AIPayloadBuilder
from .. import session
from .analyze import categorize_by_severity

router = APIRouter()


class SensitiveColumnsUpdate(BaseModel):
    sensitive_columns: Dict[str, List[str]]


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


@router.get("/preview")
async def get_payload_preview() -> Dict:
    session_id = "default"
    data = session.data_store.get(session_id, {})
    sensitive_columns = session.sensitive_columns_store.get(session_id, {})
    relationships = session.relationships_store.get(session_id, [])

    if not data:
        raise HTTPException(status_code=404, detail="No data loaded")

    from core.quality_audit import TextAnomalyDetector, NumericAnomalyDetector

    text_detector = TextAnomalyDetector(similarity_threshold=80.0, min_frequency=5)
    numeric_detector = NumericAnomalyDetector(iqr_multiplier=1.5, zscore_threshold=3.0)

    all_results = {}
    for table_name, df in data.items():
        text_results = text_detector.detect_all_columns(df)
        numeric_results = numeric_detector.detect_all_columns(df, method='both')

        text_results_serializable = {}
        for col, results in text_results.items():
            text_results_serializable[col] = {}
            for key, value in results.items():
                if isinstance(value, list):
                    text_results_serializable[col][key] = value

        numeric_results_serializable = {}
        for col, results in numeric_results.items():
            numeric_results_serializable[col] = results

        if text_results_serializable or numeric_results_serializable:
            all_results[table_name] = {
                'text': text_results_serializable,
                'numeric': numeric_results_serializable
            }

    categorized = categorize_by_severity(all_results)

    traffic_light_report = {
        'red': categorized.get('red', []),
        'yellow': categorized.get('yellow', []),
        'green': categorized.get('green', [])
    }

    payload_builder = AIPayloadBuilder()

    preview_payload = payload_builder.generate_preview_payload(
        data_dict=data,
        traffic_light_report=traffic_light_report,
        sensitive_columns=sensitive_columns,
        relationships=relationships,
        max_sample_rows=10,
        include_green=True
    )

    payload_summary = payload_builder.generate_summary(
        data_dict=data,
        sensitive_columns=sensitive_columns,
        traffic_light_report=traffic_light_report
    )

    return {
        "payload": preview_payload,
        "summary": payload_summary
    }


@router.get("/download")
async def download_payload() -> Dict:
    session_id = "default"
    data = session.data_store.get(session_id, {})
    sensitive_columns = session.sensitive_columns_store.get(session_id, {})
    relationships = session.relationships_store.get(session_id, [])

    if not data:
        raise HTTPException(status_code=404, detail="No data loaded")

    from core.quality_audit import TextAnomalyDetector, NumericAnomalyDetector

    text_detector = TextAnomalyDetector(similarity_threshold=80.0, min_frequency=5)
    numeric_detector = NumericAnomalyDetector(iqr_multiplier=1.5, zscore_threshold=3.0)

    all_results = {}
    for table_name, df in data.items():
        text_results = text_detector.detect_all_columns(df)
        numeric_results = numeric_detector.detect_all_columns(df, method='both')

        text_results_serializable = {}
        for col, results in text_results.items():
            text_results_serializable[col] = {}
            for key, value in results.items():
                if isinstance(value, list):
                    text_results_serializable[col][key] = value

        numeric_results_serializable = {}
        for col, results in numeric_results.items():
            numeric_results_serializable[col] = results

        if text_results_serializable or numeric_results_serializable:
            all_results[table_name] = {
                'text': text_results_serializable,
                'numeric': numeric_results_serializable
            }

    categorized = categorize_by_severity(all_results)

    traffic_light_report = {
        'red': categorized.get('red', []),
        'yellow': categorized.get('yellow', []),
        'green': categorized.get('green', [])
    }

    payload_builder = AIPayloadBuilder()

    preview_payload = payload_builder.generate_preview_payload(
        data_dict=data,
        traffic_light_report=traffic_light_report,
        sensitive_columns=sensitive_columns,
        relationships=relationships,
        max_sample_rows=10,
        include_green=True
    )

    return {"json": json.dumps(preview_payload, indent=2, default=str)}
