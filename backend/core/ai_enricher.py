from typing import Any, Dict, List, Optional, Tuple
import polars as pl
from datetime import datetime


_STR_LIKE_DTYPES = {"utf8", "str", "string"}
_NUMERIC_DTYPE_TOKENS = (
    "int", "float", "double", "uint",
    "int8", "int16", "int32", "int64",
    "float32", "float64",
)
_DATE_DTYPE_TOKENS = ("date", "datetime")


def _is_string_dtype(dtype) -> bool:
    return str(dtype).lower() in _STR_LIKE_DTYPES


def _is_numeric_dtype(dtype) -> bool:
    s = str(dtype).lower()
    return any(t in s for t in _NUMERIC_DTYPE_TOKENS)


def _is_date_dtype(dtype) -> bool:
    s = str(dtype).lower()
    return any(t in s for t in _DATE_DTYPE_TOKENS)


def _column_profile(series: pl.Series, total_rows: int) -> Dict[str, Any]:
    """Compact column summary used inside the IA payload."""
    col_name = series.name or "value"
    total = int(total_rows) if total_rows else int(series.len())
    null_count = int(series.null_count())
    non_null = series.drop_nulls()
    non_null_count = int(non_null.len())
    unique_count = int(non_null.n_unique()) if non_null_count > 0 else 0
    unique_ratio = (unique_count / non_null_count) if non_null_count else 0.0
    completeness = (1 - null_count / total) if total else 0.0

    profile: Dict[str, Any] = {
        "column": col_name,
        "dtype": str(series.dtype),
        "total_count": total,
        "null_count": null_count,
        "null_pct": round(100 * (null_count / total), 2) if total else 0.0,
        "unique_count": unique_count,
        "unique_ratio": round(unique_ratio, 4),
        "completeness": round(completeness, 4),
        "is_constant": unique_count == 1 and non_null_count > 0,
        "is_likely_id": non_null_count > 0 and unique_ratio >= 0.9 and unique_count > 1,
    }

    if _is_numeric_dtype(series.dtype) and non_null_count > 0:
        try:
            nums = non_null.cast(pl.Float64)
            stats = nums.describe()
            stats_dict = {row[0]: row[1] for row in stats.rows()}
            profile["numeric_stats"] = {
                "min": stats_dict.get("min"),
                "max": stats_dict.get("max"),
                "mean": stats_dict.get("mean"),
                "std": stats_dict.get("std"),
            }
            try:
                qs = nums.quantile(0.25, "nearest"), nums.quantile(0.5, "nearest"), nums.quantile(0.75, "nearest")
                profile["numeric_stats"]["p25"], profile["numeric_stats"]["p50"], profile["numeric_stats"]["p75"] = (
                    float(qs[0]),
                    float(qs[1]),
                    float(qs[2]),
                )
            except Exception:
                pass
        except Exception:
            pass

    if _is_string_dtype(series.dtype) and 0 < unique_count <= 200:
        try:
            vc = non_null.value_counts().sort("count", descending=True).head(10)
            profile["top_values"] = [
                {"value": str(row[0]), "count": int(row[1])}
                for row in vc.rows()
            ]
        except Exception:
            profile["top_values"] = []

    if _is_date_dtype(series.dtype) and non_null_count > 0:
        try:
            casted = non_null.cast(pl.Date)
            profile["date_stats"] = {
                "min_date": str(casted.min()),
                "max_date": str(casted.max()),
            }
        except Exception:
            pass

    return profile


def _enrich_anomaly(
    item: Dict[str, Any],
    df: Optional[pl.DataFrame],
    max_samples: int,
    max_top_patterns: int,
    total_rows: int,
    adaptive_patterns_threshold: int = 30,
    adaptive_patterns_hard_cap: int = 10,
) -> Dict[str, Any]:
    """Augment a single anomaly dict with full-table scope info."""
    enriched = dict(item)
    samples = item.get("data", [])
    sample_count = len(samples) if isinstance(samples, list) else 0

    if isinstance(samples, list) and len(samples) > max_samples:
        enriched["data"] = samples[:max_samples]

    violation_count = (
        item.get("violation_count")
        or item.get("count")
        or item.get("duplicate_count")
        or sample_count
    )
    enriched["violation_count"] = int(violation_count) if violation_count is not None else 0
    enriched["affected_ratio"] = (
        round(enriched["violation_count"] / total_rows, 6) if total_rows > 0 else 0.0
    )
    enriched["sample_count"] = sample_count
    enriched["sample_vs_total_note"] = (
        f"{min(sample_count, max_samples)} of ~{enriched['violation_count']:,} affected rows shown"
        if enriched["violation_count"] > 0
        else "0 affected rows"
    )

    if (
        df is not None
        and enriched.get("column")
        and enriched["column"] in df.columns
        and enriched["violation_count"] > 0
        and max_top_patterns > 0
    ):
        col = df[enriched["column"]]
        if _is_string_dtype(col.dtype):
            try:
                non_null = col.drop_nulls()
                unique_n = int(non_null.n_unique()) if non_null.len() > 0 else 0

                actual_top_n = max_top_patterns
                if (
                    unique_n > adaptive_patterns_threshold
                    and max_top_patterns < adaptive_patterns_hard_cap
                ):
                    bump = min(
                        adaptive_patterns_hard_cap,
                        max(max_top_patterns, min(adaptive_patterns_hard_cap, max_top_patterns + (unique_n // 20))),
                    )
                    actual_top_n = bump

                vc = non_null.value_counts().sort("count", descending=True).head(actual_top_n)
                enriched["top_patterns"] = [
                    {"value": str(row[0]), "count": int(row[1])}
                    for row in vc.rows()
                ]
                if actual_top_n != max_top_patterns:
                    enriched["top_patterns_adaptive"] = actual_top_n
            except Exception:
                enriched["top_patterns"] = []

    if "format_distribution" in item and isinstance(item["format_distribution"], dict):
        enriched["format_distribution"] = item["format_distribution"]

    return enriched


def _stratified_sample_indices(
    df: pl.DataFrame,
    fraction: float,
    seed: int,
) -> pl.DataFrame:
    """Return a sample of ``df`` that preserves row count proportions."""
    if not (0 < fraction < 1.0):
        return df
    target = max(int(df.height * fraction), 1)
    if target >= df.height:
        return df
    return df.sample(n=target, seed=seed)


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
        include_green: bool = True,
        summary_only: bool = False,
    ) -> Dict[str, Any]:
        schemas = self.sanitize_schema(data_dict, sensitive_columns)

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
            'security_note': 'Sensitive columns have been redacted from this payload',
            'payload_mode': 'summary' if summary_only else 'full',
        }

        sanitized_relationships = self._sanitize_relationships(relationships, sensitive_columns) if relationships else []

        payload: Dict[str, Any] = {
            'metadata': metadata,
            'schemas': schemas,
            'relationships': sanitized_relationships,
            'anomalies': {
                'red': traffic_light_report.get('red', []),
                'yellow': traffic_light_report.get('yellow', []),
                'green': traffic_light_report.get('green', [])
            }
        }

        if not summary_only:
            payload['samples'] = self.sanitize_samples(
                data_dict, sensitive_columns, max_sample_rows
            )
            payload['green_samples'] = self._generate_green_samples(
                traffic_light_report.get('green', []),
                data_dict,
                sensitive_columns,
                max_sample_rows,
            )

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

    def build_ia_payload(
        self,
        data_dict: Dict[str, pl.DataFrame],
        traffic_light_report: Dict[str, List[Dict]],
        sensitive_columns: Dict[str, List[str]],
        relationships: List[Dict] = None,
        max_samples_per_anomaly: int = 2,
        max_top_patterns: int = 3,
        stratified_threshold: int = 100_000,
        stratified_fraction: float = 0.001,
        sample_seed: int = 42,
        adaptive_patterns_threshold: int = 30,
        adaptive_patterns_hard_cap: int = 10,
    ) -> Dict[str, Any]:
        """Build the compact payload the IA actually receives.

        Compared to the public ``generate_preview_payload`` (which is the
        downloadable summary), this payload:

        - caps per-anomaly samples to ``max_samples_per_anomaly`` (default 2);
        - adds ``violation_count`` and ``affected_ratio`` to every anomaly;
        - adds ``top_patterns`` for the columns referenced by each anomaly
          (default 3, adaptively bumped up to ``adaptive_patterns_hard_cap``
          when the affected column has high cardinality);
        - enriches each schema with a per-column statistical profile;
        - applies stratified sampling to tables above
          ``stratified_threshold`` rows so the IA never sees >100k rows;
        - omits the decorative ``security_note`` and ``generated_at`` fields
          (saved as ``payload_mode='ia'`` so the consumer knows the shape).
        """
        schemas: Dict[str, Dict[str, Any]] = {}
        column_profiles: Dict[str, Dict[str, Dict[str, Any]]] = {}
        sampled_rows: Dict[str, int] = {}

        for table_name, df in data_dict.items():
            table_sensitive = set(sensitive_columns.get(table_name, []))
            safe_columns = [c for c in df.columns if c not in table_sensitive]

            if df.height > stratified_threshold:
                sample_df = _stratified_sample_indices(df, stratified_fraction, sample_seed)
                sampled_rows[table_name] = int(sample_df.height)
            else:
                sample_df = df
                sampled_rows[table_name] = int(df.height)

            schemas[table_name] = {
                "columns": safe_columns,
                "column_count": len(safe_columns),
                "total_columns": len(df.columns),
                "redacted_columns": sorted(table_sensitive),
                "redacted_count": len(table_sensitive),
                "dtypes": {col: str(sample_df[col].dtype) for col in safe_columns},
                "total_rows": int(df.height),
                "sampled_rows": sampled_rows[table_name],
            }

            column_profiles[table_name] = {
                col: _column_profile(sample_df[col], sampled_rows[table_name])
                for col in safe_columns
            }

        total_tables = len(data_dict)
        total_columns = sum(s["column_count"] for s in schemas.values())
        total_redacted = sum(s["redacted_count"] for s in schemas.values())

        def _enrich_list(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            out: List[Dict[str, Any]] = []
            for item in items or []:
                tbl = item.get("table")
                col = item.get("column")
                df = data_dict.get(tbl) if tbl else None
                out.append(
                    _enrich_anomaly(
                        item=item,
                        df=df,
                        max_samples=max_samples_per_anomaly,
                        max_top_patterns=max_top_patterns,
                        total_rows=df.height if df is not None else 0,
                        adaptive_patterns_threshold=adaptive_patterns_threshold,
                        adaptive_patterns_hard_cap=adaptive_patterns_hard_cap,
                    )
                )
            return out

        anomalies = {
            "red": _enrich_list(traffic_light_report.get("red", [])),
            "yellow": _enrich_list(traffic_light_report.get("yellow", [])),
            "green": _enrich_list(traffic_light_report.get("green", [])),
        }

        sanitized_relationships = self._sanitize_relationships(relationships, sensitive_columns) if relationships else []

        metadata = {
            "payload_mode": "ia",
            "total_tables": total_tables,
            "total_columns": total_columns,
            "total_redacted_columns": total_redacted,
            "red_anomalies_count": sum(len(v) for v in anomalies.values()),
            "yellow_anomalies_count": len(anomalies["yellow"]),
            "green_anomalies_count": len(anomalies["green"]),
            "stratified_sampling_threshold": stratified_threshold,
            "stratified_sampling_fraction": stratified_fraction,
        }

        return {
            "metadata": metadata,
            "schemas": schemas,
            "column_profiles": column_profiles,
            "relationships": sanitized_relationships,
            "anomalies": anomalies,
        }
