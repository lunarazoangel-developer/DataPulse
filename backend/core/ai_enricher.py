from typing import Dict, List, Any
import polars as pl
from datetime import datetime


class AIPayloadBuilder:
    REDACTION_PLACEHOLDER = "[REDACTED]"

    def __init__(self):
        pass

    def sanitize_schema(
        self,
        data_dict: Dict[str, pl.DataFrame],
        sensitive_columns: Dict[str, List[str]]
    ) -> Dict[str, Dict[str, Any]]:
        schemas = {}

        for table_name, df in data_dict.items():
            table_sensitive = sensitive_columns.get(table_name, [])

            safe_columns = [col for col in df.columns if col not in table_sensitive]

            schemas[table_name] = {
                'columns': safe_columns,
                'column_count': len(safe_columns),
                'total_columns': len(df.columns),
                'redacted_columns': table_sensitive,
                'redacted_count': len(table_sensitive),
                'dtypes': {col: str(df[col].dtype) for col in safe_columns}
            }

        return schemas

    def sanitize_samples(
        self,
        data_dict: Dict[str, pl.DataFrame],
        sensitive_columns: Dict[str, List[str]],
        max_rows: int = 10
    ) -> Dict[str, List[Dict]]:
        samples = {}

        for table_name, df in data_dict.items():
            table_sensitive = sensitive_columns.get(table_name, [])

            sample_df = df.head(max_rows)

            for col in table_sensitive:
                if col in sample_df.columns:
                    sample_df = sample_df.with_columns(
                        pl.lit(self.REDACTION_PLACEHOLDER).alias(col)
                    )

            samples[table_name] = sample_df.to_dicts()

        return samples

    def generate_preview_payload(
        self,
        data_dict: Dict[str, pl.DataFrame],
        traffic_light_report: Dict[str, List[Dict]],
        sensitive_columns: Dict[str, List[str]],
        relationships: List[Dict] = None,
        max_sample_rows: int = 10,
        include_green: bool = True
    ) -> Dict[str, Any]:
        schemas = self.sanitize_schema(data_dict, sensitive_columns)
        samples = self.sanitize_samples(data_dict, sensitive_columns, max_sample_rows)

        green_samples = self._generate_green_samples(
            traffic_light_report.get('green', []),
            data_dict,
            sensitive_columns,
            max_sample_rows
        )

        total_columns = sum(schema['column_count'] for schema in schemas.values())
        total_redacted = sum(schema['redacted_count'] for schema in schemas.values())
        total_tables = len(data_dict)

        red_count = sum(len(item.get('data', [])) for item in traffic_light_report.get('red', []))
        yellow_count = sum(len(item.get('data', [])) for item in traffic_light_report.get('yellow', []))
        green_count = sum(len(item.get('data', [])) for item in traffic_light_report.get('green', []))

        metadata = {
            'total_tables': total_tables,
            'total_columns': total_columns,
            'total_redacted_columns': total_redacted,
            'sample_rows_per_table': max_sample_rows,
            'red_anomalies_count': red_count,
            'yellow_anomalies_count': yellow_count,
            'green_anomalies_count': green_count,
            'generated_at': datetime.utcnow().isoformat() + 'Z',
            'security_note': 'Sensitive columns have been redacted from this payload'
        }

        sanitized_relationships = self._sanitize_relationships(relationships, sensitive_columns) if relationships else []

        payload = {
            'metadata': metadata,
            'schemas': schemas,
            'samples': samples,
            'green_samples': green_samples,
            'relationships': sanitized_relationships,
            'anomalies': {
                'red': traffic_light_report.get('red', []),
                'yellow': traffic_light_report.get('yellow', []),
                'green': traffic_light_report.get('green', [])
            }
        }

        return payload

    def _sanitize_relationships(
        self,
        relationships: List[Dict],
        sensitive_columns: Dict[str, List[str]]
    ) -> List[Dict]:
        if not relationships:
            return []

        sanitized = []
        for rel in relationships:
            source = rel.get('source', '')
            target = rel.get('target', '')
            column = rel.get('column', '')

            source_sensitive = sensitive_columns.get(source, [])
            target_sensitive = sensitive_columns.get(target, [])

            if column not in source_sensitive and column not in target_sensitive:
                sanitized.append({
                    'from_table': source,
                    'to_table': target,
                    'via_column': column,
                    'relationship_type': rel.get('relationship_type', 'unknown')
                })

        return sanitized

    def _generate_green_samples(
        self,
        green_anomalies: List[Dict],
        data_dict: Dict[str, pl.DataFrame],
        sensitive_columns: Dict[str, List[str]],
        max_rows: int = 10
    ) -> Dict[str, List[Dict]]:
        green_samples = {}

        for item in green_anomalies:
            table_name = item.get('table')
            if not table_name or table_name not in data_dict:
                continue

            df = data_dict[table_name]
            table_sensitive = sensitive_columns.get(table_name, [])

            sample_df = df.head(max_rows)

            for col in table_sensitive:
                if col in sample_df.columns:
                    sample_df = sample_df.with_columns(
                        pl.lit(self.REDACTION_PLACEHOLDER).alias(col)
                    )

            key = f"{table_name}_{item.get('column', 'unknown')}"
            green_samples[key] = {
                'table': table_name,
                'column': item.get('column'),
                'sample_rows': sample_df.to_dicts()
            }

        return green_samples

    def generate_summary(
        self,
        data_dict: Dict[str, pl.DataFrame],
        sensitive_columns: Dict[str, List[str]],
        traffic_light_report: Dict[str, List[Dict]]
    ) -> Dict[str, int]:
        total_columns = sum(len(df.columns) for df in data_dict.values())
        redacted_columns = sum(len(cols) for cols in sensitive_columns.values())
        safe_columns = total_columns - redacted_columns

        red_count = sum(len(item.get('data', [])) for item in traffic_light_report.get('red', []))
        yellow_count = sum(len(item.get('data', [])) for item in traffic_light_report.get('yellow', []))
        green_count = sum(len(item.get('data', [])) for item in traffic_light_report.get('green', []))

        return {
            'total_tables': len(data_dict),
            'total_columns': total_columns,
            'safe_columns': safe_columns,
            'redacted_columns': redacted_columns,
            'sample_rows_per_table': 10,
            'red_anomalies': red_count,
            'yellow_anomalies': yellow_count,
            'green_anomalies': green_count,
            'total_anomalies': red_count + yellow_count + green_count
        }
