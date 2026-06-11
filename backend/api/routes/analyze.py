from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.discrepancy_profiler import DiscrepancyDetector, DiscrepancyProfiler
from core.quality_audit import NumericAnomalyDetector, TextAnomalyDetector
from core.quality_audit_helpers import MAX_SAMPLES_PER_ANOMALY
from core.schema_analyzer import SchemaAnalyzer

from .. import session

router = APIRouter()


class AnalysisSettings(BaseModel):
    text_threshold: float = 80.0
    iqr_multiplier: float = 1.5
    zscore_threshold: float = 3.0
    min_frequency: int = 5
    max_unique_for_fuzzy: int = 5000
    enable_format_check: bool = True
    enable_duplicate_check: bool = True
    enable_type_mismatch_check: bool = True
    enable_constant_check: bool = True
    enable_date_anomaly_check: bool = True
    enable_cardinality_check: bool = True
    enable_domain_check: bool = True
    enable_placeholder_null_check: bool = True
    future_date_threshold_days: int = 0
    min_cardinality_ratio_id: float = 0.9
    duplicate_subset: Optional[List[str]] = None
    sample_size: Optional[int] = Field(default=None, ge=100)
    sample_fraction: Optional[float] = Field(default=None, gt=0.0, le=1.0)
    sample_seed: int = 42


@router.get("/relationships")
async def get_relationships() -> Dict:
    session_id = "default"
    relationships = session.relationships_store.get(session_id, [])
    data = session.data_store.get(session_id, {})

    analyzer = SchemaAnalyzer()
    analyzer.data_dict = data

    mermaid_code = ""
    if len(data) > 0 and relationships:
        mermaid_code = analyzer.generate_mermaid_er_diagram(relationships)
    elif len(data) > 0:
        mermaid_code = analyzer.generate_mermaid_er_diagram([])

    return {
        "relationships": relationships,
        "mermaid_diagram": mermaid_code,
    }


@router.get("/schema")
async def get_schema_analysis() -> Dict:
    session_id = "default"
    data = session.data_store.get(session_id, {})

    if not data:
        raise HTTPException(status_code=404, detail="No data loaded")

    analyzer = SchemaAnalyzer()

    type_distribution = analyzer.get_data_type_distribution(data)
    null_statistics = analyzer.get_null_statistics(data)

    return {
        "type_distribution": type_distribution,
        "null_statistics": null_statistics,
    }


@router.post("/anomalies")
async def analyze_anomalies(settings: AnalysisSettings) -> Dict:
    session_id = "default"
    data = session.data_store.get(session_id, {})

    if not data:
        raise HTTPException(status_code=404, detail="No data loaded")

    text_detector = TextAnomalyDetector(
        similarity_threshold=settings.text_threshold,
        min_frequency=settings.min_frequency,
    )

    numeric_detector = NumericAnomalyDetector(
        iqr_multiplier=settings.iqr_multiplier,
        zscore_threshold=settings.zscore_threshold,
    )

    discrepancy_detector = DiscrepancyDetector(
        enable_format_check=settings.enable_format_check,
        enable_duplicate_check=settings.enable_duplicate_check,
        enable_type_mismatch_check=settings.enable_type_mismatch_check,
        enable_constant_check=settings.enable_constant_check,
        enable_date_anomaly_check=settings.enable_date_anomaly_check,
        enable_cardinality_check=settings.enable_cardinality_check,
        enable_domain_check=settings.enable_domain_check,
        enable_placeholder_null_check=settings.enable_placeholder_null_check,
        future_date_threshold_days=settings.future_date_threshold_days,
        min_cardinality_ratio_id=settings.min_cardinality_ratio_id,
        sample_size=settings.sample_size,
        sample_fraction=settings.sample_fraction,
        sample_seed=settings.sample_seed,
    )

    profiler = DiscrepancyProfiler()

    all_results: Dict = {}
    column_profiles: Dict[str, Dict] = {}
    timings_aggregate: Dict[str, float] = {}
    sampled_tables: List[Dict] = []

    for table_name, df in data.items():
        text_results = text_detector.detect_all_columns(df)
        numeric_results = numeric_detector.detect_all_columns(df, method="both")
        discrepancy_results = discrepancy_detector.detect_all_columns(df)
        table_level_results = discrepancy_detector.detect_table_level(
            df, duplicate_subset=settings.duplicate_subset
        )

        if discrepancy_detector.was_sampled:
            sampled_tables.append(
                {
                    "table": table_name,
                    "rows_scanned": discrepancy_detector.actual_sample_size,
                    "rows_total": len(df),
                }
            )

        for k, v in discrepancy_detector.last_timings_ms.items():
            timings_aggregate[k] = timings_aggregate.get(k, 0.0) + v

        text_results_serializable: Dict = {}
        for col, results in text_results.items():
            text_results_serializable[col] = {}
            for key, value in results.items():
                if isinstance(value, list):
                    text_results_serializable[col][key] = value

        numeric_results_serializable: Dict = {}
        for col, results in numeric_results.items():
            numeric_results_serializable[col] = results

        discrepancy_serializable: Dict = {}
        for col, anomalies in discrepancy_results.items():
            discrepancy_serializable[col] = anomalies

        if (
            text_results_serializable
            or numeric_results_serializable
            or discrepancy_serializable
            or table_level_results
        ):
            all_results[table_name] = {
                "text": text_results_serializable,
                "numeric": numeric_results_serializable,
                "discrepancies": discrepancy_serializable,
                "table_level": table_level_results,
            }

        column_profiles[table_name] = profiler.profile_dataframe(df)

    categorized = categorize_by_severity(all_results)

    return {
        "results": all_results,
        "categorized": categorized,
        "summary": {
            "red_count": sum(len(item["data"]) for item in categorized.get("red", [])),
            "yellow_count": sum(
                len(item["data"]) for item in categorized.get("yellow", [])
            ),
            "green_count": sum(
                len(item["data"]) for item in categorized.get("green", [])
            ),
        },
        "column_profiles": column_profiles,
        "discrepancy_timings_ms": timings_aggregate,
        "sampled_tables": sampled_tables,
    }


def categorize_by_severity(all_results: dict) -> dict:
    categorized = {"red": [], "yellow": [], "green": []}

    for table_name, results in all_results.items():
        if results.get("text"):
            for col_name, detection_results in results["text"].items():
                if not detection_results:
                    continue

                for det_type in [
                    "fuzzy",
                    "low_frequency",
                    "case_variants",
                    "whitespace",
                ]:
                    if det_type in detection_results and detection_results[det_type]:
                        data = detection_results[det_type]

                        for severity in ["red", "yellow", "green"]:
                            severity_items = [
                                item for item in data if item.get("severity") == severity
                            ]
                            if severity_items:
                                categorized[severity].append(
                                    {
                                        "table": table_name,
                                        "column": col_name,
                                        "detection_type": det_type,
                                        "data": severity_items[:MAX_SAMPLES_PER_ANOMALY],
                                    }
                                )

        if results.get("numeric"):
            for col_name, anomaly_list in results["numeric"].items():
                if not anomaly_list:
                    continue

                for severity in ["red", "yellow", "green"]:
                    severity_items = [
                        item for item in anomaly_list if item.get("severity") == severity
                    ]
                    if severity_items:
                        categorized[severity].append(
                            {
                                "table": table_name,
                                "column": col_name,
                                "detection_type": "numeric",
                                "data": severity_items[:MAX_SAMPLES_PER_ANOMALY],
                            }
                        )

        if results.get("discrepancies"):
            for col_name, anomalies in results["discrepancies"].items():
                if not anomalies:
                    continue
                for anomaly in anomalies:
                    severity = anomaly.get("severity", "green")
                    categorized[severity].append(
                        {
                            "table": table_name,
                            "column": col_name,
                            "detection_type": anomaly.get(
                                "issue_type", "discrepancy"
                            ),
                            "data": [anomaly],
                        }
                    )

        if results.get("table_level"):
            for anomaly in results["table_level"]:
                severity = anomaly.get("severity", "green")
                categorized[severity].append(
                    {
                        "table": table_name,
                        "column": None,
                        "detection_type": anomaly.get("issue_type", "table_level"),
                        "data": [anomaly],
                    }
                )

    return categorized
