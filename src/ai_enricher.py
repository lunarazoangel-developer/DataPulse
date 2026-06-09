"""
AI Enricher Module

This module provides classes for building AI payloads with security constraints.
It ensures that sensitive columns are properly redacted before sending data to the LLM.

All code, variables, and inline documentation are written in English.
"""

from typing import Dict, List, Any
import pandas as pd
from datetime import datetime


class AIPayloadBuilder:
    """
    A class responsible for building and sanitizing AI payloads.

    This builder ensures that:
    1. Sensitive columns are purged from schema metadata
    2. Sample data has sensitive values replaced with [REDACTED]
    3. The payload structure is optimized for LLM consumption

    Attributes:
        REDACTION_PLACEHOLDER: The string used to replace sensitive data
    """

    REDACTION_PLACEHOLDER = "[REDACTED]"

    def __init__(self):
        """Initialize the AIPayloadBuilder."""
        pass

    def sanitize_schema(
        self,
        data_dict: Dict[str, pd.DataFrame],
        sensitive_columns: Dict[str, List[str]]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Sanitize schema metadata by removing sensitive columns.

        Args:
            data_dict: Dictionary mapping table names to DataFrames
            sensitive_columns: Dictionary mapping table names to list of sensitive column names

        Returns:
            Dict: Sanitized schema metadata
        """
        schemas = {}

        for table_name, df in data_dict.items():
            table_sensitive = sensitive_columns.get(table_name, [])

            # Get safe columns (non-sensitive)
            safe_columns = [col for col in df.columns if col not in table_sensitive]

            # Build sanitized schema
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
        data_dict: Dict[str, pd.DataFrame],
        sensitive_columns: Dict[str, List[str]],
        max_rows: int = 10
    ) -> Dict[str, List[Dict]]:
        """
        Sanitize sample data by redacting sensitive columns.

        Args:
            data_dict: Dictionary mapping table names to DataFrames
            sensitive_columns: Dictionary mapping table names to list of sensitive column names
            max_rows: Maximum number of rows to include per table (default: 10)

        Returns:
            Dict: Sanitized sample data
        """
        samples = {}

        for table_name, df in data_dict.items():
            table_sensitive = sensitive_columns.get(table_name, [])

            # Get first N rows
            sample_df = df.head(max_rows).copy()

            # Redact sensitive columns
            for col in table_sensitive:
                if col in sample_df.columns:
                    sample_df[col] = self.REDACTION_PLACEHOLDER

            # Convert to list of dicts
            samples[table_name] = sample_df.to_dict(orient='records')

        return samples

    def generate_preview_payload(
        self,
        data_dict: Dict[str, pd.DataFrame],
        traffic_light_report: Dict[str, List[Dict]],
        sensitive_columns: Dict[str, List[str]],
        relationships: List[Dict] = None,
        max_sample_rows: int = 10,
        include_green: bool = True
    ) -> Dict[str, Any]:
        """
        Generate the complete AI payload with security constraints.

        This method compiles the exact JSON object meant for the LLM while
        strictly enforcing security constraints:
        - Sensitive columns are purged from schema metadata
        - Sample values in sensitive columns are replaced with [REDACTED]

        The payload includes:
        - RED: High-confidence issues for AI to fix
        - YELLOW: Moderate issues for AI to analyze with context
        - GREEN: Issues for human review (included with sample context for AI to review)

        Args:
            data_dict: Dictionary mapping table names to DataFrames
            traffic_light_report: Dictionary with 'red', 'yellow', and 'green' anomaly lists
            sensitive_columns: Dictionary mapping table names to list of sensitive column names
            relationships: List of relationship dictionaries (optional)
            max_sample_rows: Maximum rows per table in samples (default: 10)
            include_green: Whether to include GREEN anomalies (default: True)

        Returns:
            Dict: Complete payload ready for AI processing
        """
        # Get sanitized schemas
        schemas = self.sanitize_schema(data_dict, sensitive_columns)

        # Get sanitized samples
        samples = self.sanitize_samples(data_dict, sensitive_columns, max_sample_rows)

        # Get green samples (context for AI to determine if changes are needed)
        green_samples = self._generate_green_samples(
            traffic_light_report.get('green', []),
            data_dict,
            sensitive_columns,
            max_sample_rows
        )

        # Calculate totals
        total_columns = sum(schema['column_count'] for schema in schemas.values())
        total_redacted = sum(schema['redacted_count'] for schema in schemas.values())
        total_tables = len(data_dict)

        # Count anomalies
        red_count = sum(len(item.get('data', [])) for item in traffic_light_report.get('red', []))
        yellow_count = sum(len(item.get('data', [])) for item in traffic_light_report.get('yellow', []))
        green_count = sum(len(item.get('data', [])) for item in traffic_light_report.get('green', []))

        # Build metadata
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

        # Sanitize relationships (remove sensitive columns from relationship info)
        sanitized_relationships = self._sanitize_relationships(relationships, sensitive_columns) if relationships else []

        # Build the final payload
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
        """
        Sanitize relationships by removing any sensitive column references.

        Args:
            relationships: List of relationship dictionaries
            sensitive_columns: Dictionary mapping table names to list of sensitive column names

        Returns:
            List: Sanitized relationships
        """
        if not relationships:
            return []

        sanitized = []
        for rel in relationships:
            source = rel.get('source', '')
            target = rel.get('target', '')
            column = rel.get('column', '')

            # Check if the relationship column is sensitive in either table
            source_sensitive = sensitive_columns.get(source, [])
            target_sensitive = sensitive_columns.get(target, [])

            # Only include relationship if column is not sensitive
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
        data_dict: Dict[str, pd.DataFrame],
        sensitive_columns: Dict[str, List[str]],
        max_rows: int = 10
    ) -> Dict[str, List[Dict]]:
        """
        Generate sample context for GREEN anomalies.

        GREEN anomalies are included with sample data so the AI can determine
        if they should be changed or kept within the context.

        Args:
            green_anomalies: List of GREEN anomaly items
            data_dict: Dictionary mapping table names to DataFrames
            sensitive_columns: Dictionary mapping table names to list of sensitive column names
            max_rows: Maximum rows per table (default: 10)

        Returns:
            Dict: Sample data for GREEN anomalies
        """
        green_samples = {}

        for item in green_anomalies:
            table_name = item.get('table')
            if not table_name or table_name not in data_dict:
                continue

            df = data_dict[table_name]
            table_sensitive = sensitive_columns.get(table_name, [])

            # Get sample rows
            sample_df = df.head(max_rows).copy()

            # Redact sensitive columns
            for col in table_sensitive:
                if col in sample_df.columns:
                    sample_df[col] = self.REDACTION_PLACEHOLDER

            # Store with key
            key = f"{table_name}_{item.get('column', 'unknown')}"
            green_samples[key] = {
                'table': table_name,
                'column': item.get('column'),
                'sample_rows': sample_df.to_dict(orient='records')
            }

        return green_samples

    def generate_summary(
        self,
        data_dict: Dict[str, pd.DataFrame],
        sensitive_columns: Dict[str, List[str]],
        traffic_light_report: Dict[str, List[Dict]]
    ) -> Dict[str, int]:
        """
        Generate a summary of the payload for UI display.

        Args:
            data_dict: Dictionary mapping table names to DataFrames
            sensitive_columns: Dictionary mapping table names to list of sensitive column names
            traffic_light_report: Dictionary with 'red', 'yellow', and 'green' anomaly lists

        Returns:
            Dict: Summary metrics
        """
        total_columns = sum(len(df.columns) for df in data_dict.values())
        redacted_columns = sum(len(cols) for cols in sensitive_columns.values())
        safe_columns = total_columns - redacted_columns

        # Count anomalies
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
