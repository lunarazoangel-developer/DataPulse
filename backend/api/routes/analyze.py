from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, List, Optional

from core.schema_analyzer import SchemaAnalyzer
from core.quality_audit import TextAnomalyDetector, NumericAnomalyDetector
from .. import session

router = APIRouter()


class AnalysisSettings(BaseModel):
    text_threshold: float = 80.0
    iqr_multiplier: float = 1.5
    zscore_threshold: float = 3.0


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
        "mermaid_diagram": mermaid_code
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
        "null_statistics": null_statistics
    }


@router.post("/anomalies")
async def analyze_anomalies(settings: AnalysisSettings) -> Dict:
    session_id = "default"
    data = session.data_store.get(session_id, {})

    if not data:
        raise HTTPException(status_code=404, detail="No data loaded")

    text_detector = TextAnomalyDetector(
        similarity_threshold=settings.text_threshold,
        min_frequency=5
    )

    numeric_detector = NumericAnomalyDetector(
        iqr_multiplier=settings.iqr_multiplier,
        zscore_threshold=settings.zscore_threshold
    )

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

    return {
        "results": all_results,
        "categorized": categorized,
        "summary": {
            "red_count": sum(len(item['data']) for item in categorized.get('red', [])),
            "yellow_count": sum(len(item['data']) for item in categorized.get('yellow', [])),
            "green_count": sum(len(item['data']) for item in categorized.get('green', []))
        }
    }


def categorize_by_severity(all_results: dict) -> dict:
    categorized = {'red': [], 'yellow': [], 'green': []}

    for table_name, results in all_results.items():
        if results.get('text'):
            for col_name, detection_results in results['text'].items():
                if not detection_results:
                    continue

                for det_type in ['fuzzy', 'low_frequency', 'case_variants', 'whitespace']:
                    if det_type in detection_results and detection_results[det_type]:
                        data = detection_results[det_type]

                        for severity in ['red', 'yellow', 'green']:
                            severity_items = [item for item in data if item.get('severity') == severity]
                            if severity_items:
                                categorized[severity].append({
                                    'table': table_name,
                                    'column': col_name,
                                    'detection_type': det_type,
                                    'data': severity_items
                                })

        if results.get('numeric'):
            for col_name, anomaly_list in results['numeric'].items():
                if not anomaly_list:
                    continue

                for severity in ['red', 'yellow', 'green']:
                    severity_items = [item for item in anomaly_list if item.get('severity') == severity]
                    if severity_items:
                        categorized[severity].append({
                            'table': table_name,
                            'column': col_name,
                            'detection_type': 'numeric',
                            'data': severity_items
                        })

    return categorized
