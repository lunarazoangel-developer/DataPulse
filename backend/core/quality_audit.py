from typing import Dict, List
import polars as pl
import numpy as np
from rapidfuzz import fuzz, process

from .quality_audit_helpers import MAX_SAMPLES_PER_ANOMALY


class TextAnomalyDetector:
    def __init__(self, similarity_threshold: float = 80.0, min_frequency: int = 5):
        self.similarity_threshold = similarity_threshold
        self.min_frequency = min_frequency

    def set_threshold(self, threshold: float) -> None:
        self.similarity_threshold = threshold

    def set_min_frequency(self, min_frequency: int) -> None:
        self.min_frequency = max(1, int(min_frequency))

    def _classify_text_severity(self, similarity: float, issue_type: str) -> str:
        if issue_type == 'Missing Data':
            return 'red'
        if issue_type == 'Inconsistent Capitalization':
            return 'red'
        if issue_type == 'Whitespace':
            return 'red'
        if issue_type == 'Fuzzy Match':
            return 'yellow'
        return 'green'

    def _is_string_dtype(self, dtype) -> bool:
        dtype_str = str(dtype).lower()
        return dtype_str in ['utf8', 'str', 'string']

    def detect_null_values(self, series: pl.Series) -> List[Dict]:
        anomalies = []

        null_count = series.null_count()

        if null_count > 0:
            null_mask = series.is_null()
            null_indices = series.filter(null_mask).to_list()

            for idx in range(len(null_indices)):
                anomalies.append({
                    'index': idx,
                    'value': None,
                    'issue_type': 'Missing Data',
                    'severity': 'red',
                    'null_type': 'NaN/NULL'
                })

        if self._is_string_dtype(series.dtype):
            stripped_series = series.str.strip_chars()
            empty_mask = (series == '') | (stripped_series == '')
            empty_mask = empty_mask & ~series.is_null()
            empty_count = empty_mask.sum()

            if empty_count > 0:
                empty_indices = series.filter(empty_mask).to_list()

                for idx in range(len(empty_indices)):
                    anomalies.append({
                        'index': idx,
                        'value': '',
                        'issue_type': 'Missing Data',
                        'severity': 'red',
                        'null_type': 'Empty String'
                    })

        return anomalies

    def detect_fuzzy(
        self,
        series: pl.Series,
        max_unique: int = 500,
        length_tolerance: int = 2,
    ) -> List[Dict]:
        clean_series = series.drop_nulls().cast(pl.Utf8)
        normalized_series = clean_series.str.to_lowercase().str.strip_chars()

        unique_normalized = normalized_series.unique()

        if len(unique_normalized) <= 1:
            return []

        if len(unique_normalized) > max_unique:
            return []

        anomalies: List[Dict] = []
        processed: set = set()

        normalized_to_originals: Dict[str, List[str]] = {}
        for orig_val, norm_val in zip(clean_series.to_list(), normalized_series.to_list()):
            normalized_to_originals.setdefault(norm_val, [])
            if orig_val not in normalized_to_originals[norm_val]:
                normalized_to_originals[norm_val].append(orig_val)

        unique_list = unique_normalized.to_list()

        def _build_blocks(values: List[str]) -> Dict[str, List[str]]:
            blocks: Dict[str, List[str]] = {}
            for v in values:
                key = (len(v) // max(1, length_tolerance), v[:1].lower())
                blocks.setdefault(key, []).append(v)
            return blocks

        blocks = _build_blocks(unique_list)

        for block_key, block_values in blocks.items():
            if len(block_values) < 2:
                continue

            for norm_value in block_values:
                if norm_value in processed:
                    continue

                choices = [v for v in block_values if v != norm_value and v not in processed]
                if not choices:
                    continue

                results = process.extract(
                    norm_value,
                    choices,
                    scorer=fuzz.ratio,
                    limit=10,
                    score_cutoff=self.similarity_threshold,
                )

                similar_values = [
                    {"normalized_value": match, "similarity": score}
                    for match, score, _ in results
                ]

                if not similar_values:
                    continue

                min_similarity = min(sv["similarity"] for sv in similar_values)
                severity = self._classify_text_severity(min_similarity, "Fuzzy Match")

                original_values = normalized_to_originals.get(norm_value, [norm_value])

                for orig_val in original_values:
                    similar_to_values: List[str] = []
                    for sv in similar_values:
                        similar_to_values.extend(
                            normalized_to_originals.get(
                                sv["normalized_value"], [sv["normalized_value"]]
                            )
                        )
                    anomalies.append(
                        {
                            "value": norm_value,
                            "original_value": ", ".join(original_values),
                            "similar_to": ", ".join(similar_to_values),
                            "similarity": 100.0,
                            "issue_type": "Fuzzy Match",
                            "severity": severity,
                        }
                    )

                for sv in similar_values:
                    matched_originals = normalized_to_originals.get(
                        sv["normalized_value"], [sv["normalized_value"]]
                    )
                    severity = self._classify_text_severity(sv["similarity"], "Fuzzy Match")
                    for matched_orig in matched_originals:
                        anomalies.append(
                            {
                                "value": sv["normalized_value"],
                                "original_value": matched_orig,
                                "similar_to": norm_value,
                                "similarity": sv["similarity"],
                                "issue_type": "Fuzzy Match",
                                "severity": severity,
                            }
                        )
                        processed.add(sv["normalized_value"])

                processed.add(norm_value)

        return anomalies

    def detect_low_frequency(self, series: pl.Series) -> List[Dict]:
        clean_series = series.drop_nulls().cast(pl.Utf8)
        value_counts_df = clean_series.value_counts()

        col_name = series.name if series.name else 'value'
        low_freq_rows: List[Dict] = []
        for row in value_counts_df.to_dicts():
            value = row.get(col_name, row.get('value', ''))
            count = row.get('counts', 0)
            if count < self.min_frequency:
                low_freq_rows.append({'value': str(value), 'count': count})

        if not low_freq_rows:
            return []

        return [
            {
                'column': col_name,
                'total_count': len(low_freq_rows),
                'min_frequency': self.min_frequency,
                'examples': low_freq_rows[:MAX_SAMPLES_PER_ANOMALY],
                'issue_type': 'Low Frequency',
                'severity': 'green',
            }
        ]

    def detect_case_inconsistency_enhanced(self, series: pl.Series) -> List[Dict]:
        clean_series = series.drop_nulls().cast(pl.Utf8)
        normalized_series = clean_series.str.to_lowercase().str.strip_chars()

        normalized_to_originals: Dict[str, set] = {}

        for orig_val, norm_val in zip(clean_series.to_list(), normalized_series.to_list()):
            normalized_to_originals.setdefault(norm_val, set()).add(orig_val)

        anomalies: List[Dict] = []
        col_name = series.name if series.name else 'value'

        for norm_key, original_variants in normalized_to_originals.items():
            if len(original_variants) > 1:
                sorted_variants = sorted(original_variants)
                anomalies.append({
                    'column': col_name,
                    'normalized_value': norm_key,
                    'variants': sorted_variants,
                    'variant_count': len(original_variants),
                    'examples': sorted_variants[:MAX_SAMPLES_PER_ANOMALY],
                    'issue_type': 'Inconsistent Capitalization',
                    'severity': 'red'
                })

        return anomalies

    def detect_whitespace_issues(self, series: pl.Series) -> List[Dict]:
        clean_series = series.drop_nulls().cast(pl.Utf8)
        unique_values = clean_series.unique().to_list()
        anomalies = []

        for value in unique_values:
            issues = []

            if value != value.lstrip():
                issues.append('Leading Space')
            if value != value.rstrip():
                issues.append('Trailing Space')
            if '  ' in value:
                issues.append('Double Space')
            if '\t' in value:
                issues.append('Tab Character')

            if issues:
                anomalies.append({
                    'value': value,
                    'issues': ', '.join(issues),
                    'issue_type': 'Whitespace',
                    'severity': 'red'
                })

        return anomalies

    def get_value_distribution(self, series: pl.Series) -> List[Dict]:
        clean_series = series.drop_nulls().cast(pl.Utf8)
        return clean_series.value_counts().to_dicts()

    def detect_all(self, series: pl.Series) -> Dict[str, List]:
        results = {}

        null_values = self.detect_null_values(series)
        if null_values:
            results['null_values'] = null_values

        case_variants = self.detect_case_inconsistency_enhanced(series)
        if case_variants:
            results['case_variants'] = case_variants

        whitespace = self.detect_whitespace_issues(series)
        if whitespace:
            results['whitespace'] = whitespace

        fuzzy = self.detect_fuzzy(series)
        if fuzzy:
            results['fuzzy'] = fuzzy

        frequency = self.detect_low_frequency(series)
        if frequency:
            results['low_frequency'] = frequency

        return results

    def detect_all_columns(self, df: pl.DataFrame) -> Dict[str, Dict]:
        results = {}

        string_columns = [col for col in df.columns if self._is_string_dtype(df[col].dtype)]

        for col in string_columns:
            col_results = self.detect_all(df[col])
            if col_results:
                col_results['distribution'] = self.get_value_distribution(df[col])
                results[col] = col_results

        return results


class NumericAnomalyDetector:
    def __init__(self, iqr_multiplier: float = 1.5, zscore_threshold: float = 3.0):
        self.iqr_multiplier = iqr_multiplier
        self.zscore_threshold = zscore_threshold

    def set_parameters(self, iqr_multiplier: float, zscore_threshold: float) -> None:
        self.iqr_multiplier = iqr_multiplier
        self.zscore_threshold = zscore_threshold

    def detect_null_values(self, series: pl.Series) -> List[Dict]:
        anomalies = []

        null_count = series.null_count()

        if null_count > 0:
            null_mask = series.is_null()

            for idx in range(len(series)):
                if null_mask[idx]:
                    anomalies.append({
                        'index': idx,
                        'value': None,
                        'issue_type': 'Missing Data',
                        'severity': 'red',
                        'null_type': 'NaN/NULL'
                    })

        return anomalies

    def _classify_numeric_severity(self, z_score: float, iqr_outlier: bool) -> str:
        if z_score > 4.0:
            return 'red'
        if z_score > 3.0:
            return 'yellow'
        if iqr_outlier:
            return 'yellow'
        return 'green'

    def _is_numeric_dtype(self, dtype) -> bool:
        dtype_str = str(dtype).lower()
        numeric_types = ['int', 'float', 'double', 'uint', 'int8', 'int16', 'int32', 'int64', 'float32', 'float64']
        return any(t in dtype_str for t in numeric_types)

    def detect_iqr(self, series: pl.Series) -> pl.Series:
        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1

        lower_bound = q1 - (self.iqr_multiplier * iqr)
        upper_bound = q3 + (self.iqr_multiplier * iqr)

        outliers = (series < lower_bound) | (series > upper_bound)

        return outliers

    def detect_zscore(self, series: pl.Series) -> pl.Series:
        mean = series.mean()
        std = series.std()

        if std == 0:
            return pl.Series([False] * len(series))

        z_scores = (series - mean).abs() / std

        outliers = z_scores > self.zscore_threshold

        return outliers

    def detect(self, series: pl.Series, method: str = 'both') -> List[Dict]:
        results = []

        null_results = self.detect_null_values(series)
        results.extend(null_results)

        clean_series = series.drop_nulls()

        if len(clean_series) == 0:
            return results

        mean = clean_series.mean()
        std = clean_series.std() if clean_series.std() > 0 else 1

        if method in ['iqr', 'both']:
            iqr_outliers = self.detect_iqr(clean_series)
        else:
            iqr_outliers = pl.Series([False] * len(clean_series))

        if method in ['zscore', 'both']:
            zscore_outliers = self.detect_zscore(clean_series)
        else:
            zscore_outliers = pl.Series([False] * len(clean_series))

        for idx in range(len(clean_series)):
            value = clean_series[idx]
            iqr_flag = iqr_outliers[idx]
            zscore_flag = zscore_outliers[idx]

            z_score = abs((value - mean) / std) if std > 0 else 0

            severity = self._classify_numeric_severity(z_score, iqr_flag)

            results.append({
                'index': idx,
                'value': value,
                'z_score': round(z_score, 4),
                'iqr_outlier': iqr_flag,
                'zscore_outlier': zscore_flag,
                'is_anomaly': iqr_flag or zscore_flag,
                'severity': severity
            })

        return results

    def detect_all_columns(self, df: pl.DataFrame, method: str = 'both') -> Dict[str, List]:
        results = {}

        numeric_columns = [col for col in df.columns if self._is_numeric_dtype(df[col].dtype)]

        for col in numeric_columns:
            anomalies = self.detect(df[col], method=method)
            filtered = [a for a in anomalies if a.get('is_anomaly')]
            if filtered:
                results[col] = filtered

        return results
