import re
import time
from datetime import date, datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import polars as pl

from .quality_audit_helpers import (
    DOMAIN_RULES,
    FORMAT_PATTERNS,
    MAX_SAMPLES_PER_ANOMALY,
    PLACEHOLDER_NULL_TOKENS,
    detect_inconsistent_date_formats,
    infer_domain_rule,
    infer_format_pattern,
    is_ancient_date,
    is_future_date,
    parse_date_safely,
)


_NUMERIC_DTYPE_TOKENS = (
    "int", "float", "double", "uint",
    "int8", "int16", "int32", "int64",
    "float32", "float64",
)
_STRING_DTYPES = {"utf8", "str", "string"}
_DATE_DTYPE_TOKENS = ("date", "datetime")


def _is_string_dtype(dtype) -> bool:
    return str(dtype).lower() in _STRING_DTYPES


def _is_numeric_dtype(dtype) -> bool:
    s = str(dtype).lower()
    return any(t in s for t in _NUMERIC_DTYPE_TOKENS)


def _is_date_dtype(dtype) -> bool:
    s = str(dtype).lower()
    return any(t in s for t in _DATE_DTYPE_TOKENS)


def _to_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


class DiscrepancyDetector:
    def __init__(
        self,
        enable_format_check: bool = True,
        enable_duplicate_check: bool = True,
        enable_type_mismatch_check: bool = True,
        enable_constant_check: bool = True,
        enable_date_anomaly_check: bool = True,
        enable_cardinality_check: bool = True,
        enable_domain_check: bool = True,
        enable_placeholder_null_check: bool = True,
        future_date_threshold_days: int = 0,
        min_cardinality_ratio_id: float = 0.9,
        max_unique_for_format: int = 200,
        sample_size: Optional[int] = None,
        sample_fraction: Optional[float] = None,
        sample_seed: int = 42,
    ):
        self.enable_format_check = enable_format_check
        self.enable_duplicate_check = enable_duplicate_check
        self.enable_type_mismatch_check = enable_type_mismatch_check
        self.enable_constant_check = enable_constant_check
        self.enable_date_anomaly_check = enable_date_anomaly_check
        self.enable_cardinality_check = enable_cardinality_check
        self.enable_domain_check = enable_domain_check
        self.enable_placeholder_null_check = enable_placeholder_null_check
        self.future_date_threshold_days = future_date_threshold_days
        self.min_cardinality_ratio_id = min_cardinality_ratio_id
        self.max_unique_for_format = max_unique_for_format
        self.sample_size = sample_size
        self.sample_fraction = sample_fraction
        self.sample_seed = sample_seed
        self.last_timings_ms: Dict[str, float] = {}
        self.was_sampled: bool = False
        self.actual_sample_size: int = 0

    def _maybe_sample(self, df: pl.DataFrame) -> pl.DataFrame:
        original_len = len(df)
        if self.sample_size and original_len > self.sample_size:
            self.was_sampled = True
            self.actual_sample_size = self.sample_size
            return df.sample(n=self.sample_size, seed=self.sample_seed)
        if self.sample_fraction and 0 < self.sample_fraction < 1.0:
            if original_len > 1000:
                self.was_sampled = True
                self.actual_sample_size = int(original_len * self.sample_fraction)
                return df.sample(fraction=self.sample_fraction, seed=self.sample_seed)
        self.actual_sample_size = original_len
        return df

    def _time(self, key: str, fn: Callable[[], List[Dict]]) -> List[Dict]:
        start = time.perf_counter()
        try:
            return fn()
        finally:
            self.last_timings_ms[key] = round(
                (time.perf_counter() - start) * 1000, 2
            )

    def detect_placeholder_nulls(self, series: pl.Series) -> List[Dict]:
        if not _is_string_dtype(series.dtype):
            return []
        col_name = series.name or "value"
        stripped = series.str.strip_chars().str.to_lowercase()
        mask = stripped.is_in(list(PLACEHOLDER_NULL_TOKENS)) & series.is_not_null()
        count = int(mask.sum())
        if count == 0:
            return []
        return [
            {
                "column": col_name,
                "violation_count": count,
                "matched_tokens": sorted(PLACEHOLDER_NULL_TOKENS),
                "issue_type": "Placeholder Null",
                "severity": "yellow",
            }
        ]

    def detect_format_violations(
        self, series: pl.Series, inferred_format: Optional[str] = None
    ) -> List[Dict]:
        if not _is_string_dtype(series.dtype):
            return []

        col_name = series.name or "value"
        non_null = series.drop_nulls()
        if non_null.is_empty():
            return []

        if inferred_format is None:
            unique_vals = (
                non_null.unique().to_list()
                if non_null.n_unique() <= self.max_unique_for_format
                else []
            )
            if unique_vals:
                inferred_format = infer_format_pattern(col_name, unique_vals)

        if not inferred_format or inferred_format not in FORMAT_PATTERNS:
            return []

        pattern = FORMAT_PATTERNS[inferred_format]
        stripped = non_null.str.strip_chars()
        match_expr = stripped.str.contains(f"^(?:{pattern.pattern})$")
        non_match_mask = ~match_expr
        non_match_count = int(non_match_mask.sum())
        if non_match_count == 0:
            return []

        sample_values = (
            non_null.filter(non_match_mask).head(MAX_SAMPLES_PER_ANOMALY).to_list()
        )
        return [
            {
                "column": col_name,
                "expected_format": inferred_format,
                "violation_count": non_match_count,
                "sample_violations": sample_values,
                "issue_type": "Format Violation",
                "severity": "red",
            }
        ]

    def detect_inconsistent_date_formats(self, series: pl.Series) -> List[Dict]:
        if not _is_string_dtype(series.dtype):
            return []
        col_name = series.name or "value"
        non_null = series.drop_nulls()
        if non_null.is_empty():
            return []

        stripped = non_null.str.strip_chars()
        distribution: Dict[str, int] = {}
        for fmt_name, pattern in FORMAT_PATTERNS.items():
            if "date" not in fmt_name and fmt_name != "datetime_iso":
                continue
            try:
                count = int(stripped.str.contains(f"^(?:{pattern.pattern})$").sum())
            except Exception:
                continue
            if count > 0:
                distribution[fmt_name] = count

        recognized = {k: v for k, v in distribution.items()}
        if len(recognized) <= 1:
            return []

        return [
            {
                "column": col_name,
                "format_distribution": distribution,
                "issue_type": "Inconsistent Date Format",
                "severity": "red",
            }
        ]

    def detect_duplicate_rows(
        self, df: pl.DataFrame, subset: Optional[List[str]] = None
    ) -> List[Dict]:
        if df.is_empty():
            return []
        cols = subset if subset else df.columns
        try:
            dup_mask = df.select(cols).is_duplicated()
        except Exception:
            return []
        dup_count = int(dup_mask.sum())
        if dup_count == 0:
            return []
        dup_indices = dup_mask.to_list()
        first_dup_idx = dup_indices.index(True)
        row_tuple = tuple(str(df[c][first_dup_idx]) for c in cols)
        return [
            {
                "subset": cols,
                "duplicate_count": dup_count,
                "sample": [
                    {
                        "index": first_dup_idx,
                        "row_sample": dict(zip(cols, row_tuple)),
                    }
                ],
                "issue_type": "Duplicate Rows",
                "severity": "red",
            }
        ]

    def detect_type_mismatch(self, series: pl.Series) -> List[Dict]:
        col_name = series.name or "value"
        if _is_numeric_dtype(series.dtype):
            return self._detect_numeric_type_mismatch(series, col_name)
        if _is_date_dtype(series.dtype):
            return self._detect_date_type_mismatch(series, col_name)
        return []

    def _detect_numeric_type_mismatch(
        self, series: pl.Series, col_name: str
    ) -> List[Dict]:
        stringified = series.cast(pl.Utf8)
        non_null = stringified.filter(stringified.is_not_null() & (stringified != ""))
        if non_null.is_empty():
            return []

        placeholder_lc = {t.lower() for t in PLACEHOLDER_NULL_TOKENS if t}
        lowered = non_null.str.to_lowercase()
        not_placeholder = ~lowered.is_in(list(placeholder_lc))
        candidates = non_null.filter(not_placeholder)
        if candidates.is_empty():
            return []

        float_parseable = candidates.cast(pl.Float64, strict=False).is_not_null()
        bad_mask = ~float_parseable
        bad_count = int(bad_mask.sum())
        if bad_count == 0:
            return []

        sample = candidates.filter(bad_mask).head(MAX_SAMPLES_PER_ANOMALY).to_list()
        return [
            {
                "column": col_name,
                "expected_dtype": "numeric",
                "violation_count": bad_count,
                "sample": sample,
                "issue_type": "Type Mismatch",
                "severity": "red",
            }
        ]

    def _detect_date_type_mismatch(
        self, series: pl.Series, col_name: str
    ) -> List[Dict]:
        stringified = series.cast(pl.Utf8)
        non_null = stringified.filter(stringified.is_not_null() & (stringified != ""))
        if non_null.is_empty():
            return []

        placeholder_lc = {t.lower() for t in PLACEHOLDER_NULL_TOKENS if t}
        lowered = non_null.str.to_lowercase()
        not_placeholder = ~lowered.is_in(list(placeholder_lc))
        candidates = non_null.filter(not_placeholder)
        if candidates.is_empty():
            return []

        date_formats = [
            "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d",
            "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%m-%d-%Y", "%d.%m.%Y",
            "%Y%m%d", "%b %d, %Y", "%d %b %Y",
        ]
        parsed_mask: Optional[pl.Series] = None
        for fmt in date_formats:
            try:
                parsed = candidates.str.strptime(pl.Date, fmt, strict=False)
            except Exception:
                continue
            local_mask = parsed.is_not_null()
            parsed_mask = local_mask if parsed_mask is None else (parsed_mask | local_mask)

        if parsed_mask is None:
            return []
        bad_count = int((~parsed_mask).sum())
        if bad_count == 0:
            return []

        sample = candidates.filter(~parsed_mask).head(5).to_list()
        return [
            {
                "column": col_name,
                "expected_dtype": "date",
                "violation_count": bad_count,
                "sample": sample,
                "issue_type": "Type Mismatch",
                "severity": "red",
            }
        ]

    def detect_constant_or_low_variance(self, series: pl.Series) -> List[Dict]:
        col_name = series.name or "value"
        non_null = series.drop_nulls()
        total = len(non_null)
        if total == 0:
            return []
        unique_count = non_null.n_unique()

        if unique_count == 1:
            only_value = str(non_null.to_list()[0])
            return [
                {
                    "column": col_name,
                    "unique_count": 1,
                    "unique_ratio": 1.0,
                    "only_value": only_value,
                    "issue_type": "Constant Column",
                    "severity": "green",
                }
            ]

        anomalies: List[Dict] = []
        if _is_numeric_dtype(series.dtype):
            stats = non_null.cast(pl.Float64).describe()
            stats_dict = {row[0]: row[1] for row in stats.rows()}
            min_v = stats_dict.get("min")
            max_v = stats_dict.get("max")
            std = stats_dict.get("std")
            if min_v is not None and max_v is not None:
                span = max_v - min_v
                if span > 0 and std is not None:
                    cv = std / span
                    if cv < 0.05:
                        unique_ratio = unique_count / total
                        anomalies.append(
                            {
                                "column": col_name,
                                "unique_count": unique_count,
                                "unique_ratio": round(unique_ratio, 4),
                                "coefficient_of_variation": round(cv, 4),
                                "issue_type": "Low Variance",
                                "severity": "green",
                            }
                        )
        return anomalies

    def detect_date_anomalies(
        self, series: pl.Series, threshold_days: int = 0
    ) -> List[Dict]:
        col_name = series.name or "value"
        result: List[Dict] = []
        today = date.today()
        future_cutoff = today + timedelta_days(threshold_days)

        if _is_date_dtype(series.dtype):
            non_null = series.drop_nulls()
            if non_null.is_empty():
                return []
            casted = non_null.cast(pl.Date) if not isinstance(non_null.dtype, pl.Date) else non_null
            future_cutoff_series = pl.Series("cutoff", [future_cutoff]).cast(pl.Date)
            ancient_cutoff_series = pl.Series("cutoff", [date(1900, 1, 1)]).cast(pl.Date)
            future_mask = casted > future_cutoff_series
            ancient_mask = casted < ancient_cutoff_series
            future_count = int(future_mask.sum())
            ancient_count = int(ancient_mask.sum())
            if future_count == 0 and ancient_count == 0:
                return []
            if future_count > 0:
                future_samples = casted.filter(future_mask).head(MAX_SAMPLES_PER_ANOMALY).to_list()
                result.append(
                    {
                        "column": col_name,
                        "anomaly_subtype": "Future Date",
                        "count": future_count,
                        "sample": [
                            {"date": d.isoformat()} for d in future_samples
                        ],
                        "issue_type": "Date Anomaly",
                        "severity": "red",
                    }
                )
            if ancient_count > 0:
                ancient_samples = casted.filter(ancient_mask).head(MAX_SAMPLES_PER_ANOMALY).to_list()
                result.append(
                    {
                        "column": col_name,
                        "anomaly_subtype": "Ancient Date",
                        "count": ancient_count,
                        "sample": [
                            {"date": d.isoformat()} for d in ancient_samples
                        ],
                        "issue_type": "Date Anomaly",
                        "severity": "yellow",
                    }
                )
            return result

        if _is_string_dtype(series.dtype):
            non_null = series.drop_nulls()
            if non_null.is_empty():
                return []
            date_formats = [
                "%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d",
                "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%m-%d-%Y", "%d.%m.%Y",
                "%Y%m%d", "%b %d, %Y", "%d %b %Y",
            ]
            parsed_series: Optional[pl.Series] = None
            for fmt in date_formats:
                try:
                    parsed = non_null.str.strptime(pl.Date, fmt, strict=False)
                except Exception:
                    continue
                if parsed_series is None:
                    parsed_series = parsed
                else:
                    parsed_series = parsed_series.fill_null(parsed)

            if parsed_series is None or parsed_series.null_count() == len(non_null):
                return []

            valid_mask = parsed_series.is_not_null()
            valid_dates = parsed_series.filter(valid_mask)
            valid_values = non_null.filter(valid_mask)
            future_cutoff_series = pl.Series("cutoff", [future_cutoff]).cast(pl.Date)
            ancient_cutoff_series = pl.Series("cutoff", [date(1900, 1, 1)]).cast(pl.Date)
            future_mask = valid_dates > future_cutoff_series
            ancient_mask = valid_dates < ancient_cutoff_series

            future_count = int(future_mask.sum())
            ancient_count = int(ancient_mask.sum())

            if future_count > 0:
                fv = valid_values.filter(future_mask).head(MAX_SAMPLES_PER_ANOMALY).to_list()
                fd = valid_dates.filter(future_mask).head(MAX_SAMPLES_PER_ANOMALY).to_list()
                result.append(
                    {
                        "column": col_name,
                        "anomaly_subtype": "Future Date",
                        "count": future_count,
                        "sample": [
                            {"value": v, "date": d.isoformat()}
                            for v, d in zip(fv, fd)
                        ],
                        "issue_type": "Date Anomaly",
                        "severity": "red",
                    }
                )
            if ancient_count > 0:
                av = valid_values.filter(ancient_mask).head(MAX_SAMPLES_PER_ANOMALY).to_list()
                ad = valid_dates.filter(ancient_mask).head(MAX_SAMPLES_PER_ANOMALY).to_list()
                result.append(
                    {
                        "column": col_name,
                        "anomaly_subtype": "Ancient Date",
                        "count": ancient_count,
                        "sample": [
                            {"value": v, "date": d.isoformat()}
                            for v, d in zip(av, ad)
                        ],
                        "issue_type": "Date Anomaly",
                        "severity": "yellow",
                    }
                )
        return result

    def detect_cardinality_anomalies(
        self, series: pl.Series, id_ratio_threshold: float = 0.9
    ) -> List[Dict]:
        col_name = series.name or "value"
        non_null = series.drop_nulls()
        total = len(non_null)
        if total == 0:
            return []
        unique_count = non_null.n_unique()
        unique_ratio = unique_count / total

        if unique_ratio < 0.5 and unique_count > 1:
            return []
        if unique_ratio >= id_ratio_threshold:
            return [
                {
                    "column": col_name,
                    "unique_count": unique_count,
                    "unique_ratio": round(unique_ratio, 4),
                    "is_likely_id": True,
                    "is_likely_pii": self._looks_like_pii(col_name),
                    "issue_type": "High Cardinality",
                    "severity": "yellow",
                }
            ]
        return []

    @staticmethod
    @staticmethod
    def _looks_like_pii(col_name: str) -> bool:
        if not col_name:
            return False
        c = col_name.lower()
        return any(
            token in c
            for token in [
                "email", "phone", "ssn", "curp", "rfc", "name", "nombre",
                "address", "direccion", "dob", "birth", "nacimiento",
                "id", "uuid", "ip",
            ]
        )

    def detect_domain_violations(self, series: pl.Series) -> List[Dict]:
        col_name = series.name or "value"
        rule_name = infer_domain_rule(col_name)
        if not rule_name or rule_name not in DOMAIN_RULES:
            return []
        rule = DOMAIN_RULES[rule_name]
        if not _is_numeric_dtype(series.dtype):
            return []

        try:
            numeric = series.cast(pl.Float64)
        except Exception:
            return []

        non_null = numeric.drop_nulls()
        if non_null.is_empty():
            return []

        rule_check = _apply_domain_rule_vectorized(non_null, rule_name)
        if rule_check is None:
            violation_mask = self._domain_violation_mask_fallback(non_null, rule)
        else:
            violation_mask = rule_check
        violation_count = int(violation_mask.sum())
        if violation_count == 0:
            return []

        violating_values = non_null.filter(violation_mask).head(MAX_SAMPLES_PER_ANOMALY).to_list()
        sample = [{"value": v, "violation": rule_name} for v in violating_values]
        return [
            {
                "column": col_name,
                "rule": rule_name,
                "violation_count": violation_count,
                "sample": sample,
                "issue_type": "Domain Violation",
                "severity": "red",
            }
        ]

    @staticmethod
    def _domain_violation_mask_fallback(
        series: pl.Series, rule: Callable[[object], Optional[str]]
    ) -> pl.Series:
        flags = [bool(rule(v)) for v in series.to_list()]
        return pl.Series(flags)

    def _safe_run(self, key: str, fn: Callable[[], List[Dict]], col: str) -> List[Dict]:
        try:
            return self._time(key, fn)
        except Exception as e:
            return [
                {
                    "column": col,
                    "issue_type": "Detector Error",
                    "severity": "yellow",
                    "detector": key,
                    "error": str(e)[:200],
                }
            ]

    def detect_all_columns(
        self, df: pl.DataFrame, subset: Optional[List[str]] = None
    ) -> Dict[str, List[Dict]]:
        self.last_timings_ms = {}
        self.was_sampled = False
        self.actual_sample_size = 0

        df = self._maybe_sample(df)

        results: Dict[str, List[Dict]] = {}
        for col in df.columns:
            series = df[col]
            col_anomalies: List[Dict] = []

            if self.enable_placeholder_null_check:
                col_anomalies.extend(
                    self._safe_run("placeholder_nulls", lambda: self.detect_placeholder_nulls(series), col)
                )

            if self.enable_format_check:
                col_anomalies.extend(
                    self._safe_run("format_violations", lambda: self.detect_format_violations(series), col)
                )
                col_anomalies.extend(
                    self._safe_run("inconsistent_date_formats", lambda: self.detect_inconsistent_date_formats(series), col)
                )

            if self.enable_type_mismatch_check:
                col_anomalies.extend(
                    self._safe_run("type_mismatch", lambda: self.detect_type_mismatch(series), col)
                )

            if self.enable_constant_check:
                col_anomalies.extend(
                    self._safe_run("low_variance", lambda: self.detect_constant_or_low_variance(series), col)
                )

            if self.enable_date_anomaly_check:
                col_anomalies.extend(
                    self._safe_run("date_anomalies", lambda: self.detect_date_anomalies(series, self.future_date_threshold_days), col)
                )

            if self.enable_cardinality_check:
                col_anomalies.extend(
                    self._safe_run("cardinality", lambda: self.detect_cardinality_anomalies(series, self.min_cardinality_ratio_id), col)
                )

            if self.enable_domain_check:
                col_anomalies.extend(
                    self._safe_run("domain", lambda: self.detect_domain_violations(series), col)
                )

            if col_anomalies:
                results[col] = col_anomalies
        return results

    def detect_table_level(
        self, df: pl.DataFrame, duplicate_subset: Optional[List[str]] = None
    ) -> List[Dict]:
        results: List[Dict] = []
        if self.enable_duplicate_check:
            try:
                results.extend(
                    self._time("duplicates", lambda: self.detect_duplicate_rows(df, subset=duplicate_subset))
                )
            except Exception as e:
                results.append(
                    {
                        "issue_type": "Detector Error",
                        "severity": "yellow",
                        "detector": "duplicates",
                        "error": str(e)[:200],
                    }
                )
        return results


def _apply_domain_rule_vectorized(
    series: pl.Series, rule_name: str
) -> Optional[pl.Series]:
    try:
        if rule_name == "non_negative" or rule_name == "non_negative_int":
            return series < 0
        if rule_name == "percentage":
            return (series < 0) | (series > 100)
        if rule_name == "ratio":
            return (series < 0) | (series > 1)
    except Exception:
        return None
    return None


def timedelta_days(days: int) -> "datetime.timedelta":
    from datetime import timedelta
    return timedelta(days=days)


class DiscrepancyProfiler:
    def profile_column(self, series: pl.Series) -> Dict:
        col_name = series.name or "value"
        total_count = len(series)
        null_count = int(series.null_count())
        non_null = series.drop_nulls()
        non_null_count = len(non_null)
        unique_count = non_null.n_unique() if non_null_count > 0 else 0
        unique_ratio = (unique_count / non_null_count) if non_null_count > 0 else 0.0
        completeness = (1 - null_count / total_count) if total_count > 0 else 0.0

        is_constant = unique_count == 1 and non_null_count > 0
        is_likely_id = (
            non_null_count > 0 and unique_ratio >= 0.9 and unique_count > 1
        )

        detected_format: Optional[str] = None
        if _is_string_dtype(series.dtype) and 0 < unique_count <= 200:
            try:
                unique_vals = non_null.unique().to_list()
                detected_format = infer_format_pattern(col_name, unique_vals)
            except Exception:
                detected_format = None

        inferred_domain: Optional[str] = None
        if _is_numeric_dtype(series.dtype):
            inferred_domain = infer_domain_rule(col_name)

        null_ratio = (null_count / total_count) if total_count > 0 else 0.0
        if null_ratio > 0.5:
            severity = "red"
        elif null_ratio > 0.1:
            severity = "yellow"
        else:
            severity = "green"

        recommendations: List[str] = []
        if total_count > 0 and null_ratio > 0.1:
            recommendations.append(
                f"High null rate ({round(100 * null_ratio, 1)}%)"
            )
        if is_constant:
            recommendations.append("Column is constant — consider dropping")
        if is_likely_id:
            recommendations.append("High cardinality suggests ID column")
        if detected_format and detected_format in ["email", "phone", "url"]:
            recommendations.append(f"Detected {detected_format} format")
        if inferred_domain:
            recommendations.append(f"Domain rule applies: {inferred_domain}")

        return {
            "column": col_name,
            "dtype": str(series.dtype),
            "total_count": total_count,
            "null_count": null_count,
            "null_pct": round(100 * null_ratio, 2),
            "unique_count": unique_count,
            "unique_ratio": round(unique_ratio, 4),
            "completeness": round(completeness, 4),
            "is_constant": is_constant,
            "is_likely_id": is_likely_id,
            "detected_format": detected_format,
            "inferred_domain_rule": inferred_domain,
            "severity": severity,
            "recommendations": recommendations,
        }

    def profile_dataframe(self, df: pl.DataFrame) -> Dict[str, Dict]:
        return {col: self.profile_column(df[col]) for col in df.columns}
