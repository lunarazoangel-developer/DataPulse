"""
Quality Audit Module - Anomaly Detection with Traffic Light Triage System

This module provides classes for detecting data quality issues in DataFrames:
- TextAnomalyDetector: Uses fuzzy string matching (rapidfuzz) with case normalization
- NumericAnomalyDetector: Uses IQR and Z-Score methods for statistical outlier detection

Traffic Light Severity Framework:
- RED: High-confidence issues ready for AI auto-fix (nulls, case typos, high-similarity matches)
- YELLOW: Moderate issues needing AI context
- GREEN: Business-sensitive issues for human review only

All code, variables, and inline documentation are written in English.
"""

from typing import Dict, List, Optional
import pandas as pd
import numpy as np
from rapidfuzz import fuzz, process


class TextAnomalyDetector:
    """
    A class for detecting text anomalies using multiple detection methods.

    Detection methods include:
    1. Null/NaN detection - Pre-check for missing critical data (RED severity)
    2. Fuzzy matching (rapidfuzz) - finds similar strings with case normalization
    3. Frequency-based - finds rare values (potential typos)
    4. Case inconsistency - finds case variations (apple vs Apple vs APPLE)
    5. Whitespace issues - finds leading/trailing/double spaces

    Traffic Light Severity:
    - RED (75-90% similarity or nulls): High-confidence issues - ready for AI
    - YELLOW (90-98% similarity): Low-confidence - needs context
    - GREEN: Human review only

    Attributes:
        similarity_threshold: Minimum similarity percentage (0-100) for fuzzy matching
        min_frequency: Minimum count to not be considered rare (default: 5)
    """

    def __init__(self, similarity_threshold: float = 80.0, min_frequency: int = 5):
        """
        Initialize the TextAnomalyDetector.

        Args:
            similarity_threshold: Minimum similarity percentage (default: 80.0)
            min_frequency: Minimum count for value to be considered normal (default: 5)
        """
        self.similarity_threshold = similarity_threshold
        self.min_frequency = min_frequency

    def set_threshold(self, threshold: float) -> None:
        """
        Update the similarity threshold.

        Args:
            threshold: New threshold value (0-100)
        """
        self.similarity_threshold = threshold

    def _classify_text_severity(self, similarity: float, issue_type: str) -> str:
        """
        Classify text anomaly severity using traffic light system.

        Traffic Light Rules:
        - RED: Null values, case variations (exact same lowercase), whitespace issues
        - YELLOW: Fuzzy matches (hidden typos found by rapidfuzz)
        - GREEN: Low frequency values (human review)

        Args:
            similarity: Similarity percentage (0-100)
            issue_type: Type of issue detected

        Returns:
            str: Severity level ('red', 'yellow', or 'green')
        """
        # Null values are always RED
        if issue_type == 'Missing Data':
            return 'red'

        # Case variations (Inconsistent Capitalization) are always RED
        if issue_type == 'Inconsistent Capitalization':
            return 'red'

        # Whitespace issues are always RED
        if issue_type == 'Whitespace':
            return 'red'

        # Fuzzy match: all YELLOW (needs AI context for hidden typos)
        if issue_type == 'Fuzzy Match':
            return 'yellow'  # All fuzzy matches are YELLOW

        # Non-fuzzy issues are always GREEN (human review)
        return 'green'

    def detect_null_values(self, series: pd.Series) -> pd.DataFrame:
        """
        Pre-check method to detect null/NaN/empty values in a column.

        Null values in critical columns (like titles, IDs) are flagged as
        RED severity because they represent missing critical data that requires
        immediate attention.

        Args:
            series: Pandas Series containing text data

        Returns:
            pd.DataFrame: DataFrame with null value anomalies including severity
        """
        anomalies = []

        # Check for null/NaN values
        null_mask = series.isna()
        null_count = null_mask.sum()

        if null_count > 0:
            # Get indices of null values
            null_indices = series[null_mask].index.tolist()

            for idx in null_indices:
                anomalies.append({
                    'index': idx,
                    'value': None,
                    'issue_type': 'Missing Data',
                    'severity': 'red',  # RED - critical missing data
                    'null_type': 'NaN/NULL'
                })

        # Check for empty strings
        if series.dtype == 'object':
            empty_mask = (series == '') | (series.astype(str).str.strip() == '')
            empty_mask = empty_mask & ~series.isna()  # Exclude already counted nulls
            empty_count = empty_mask.sum()

            if empty_count > 0:
                empty_indices = series[empty_mask].index.tolist()

                for idx in empty_indices:
                    anomalies.append({
                        'index': idx,
                        'value': '',
                        'issue_type': 'Missing Data',
                        'severity': 'red',  # RED - critical missing data
                        'null_type': 'Empty String'
                    })

        if not anomalies:
            return pd.DataFrame(columns=['index', 'value', 'issue_type', 'severity', 'null_type'])

        return pd.DataFrame(anomalies)

    def detect_fuzzy(self, series: pd.Series, max_unique: int = 500) -> pd.DataFrame:
        """
        Detect text anomalies using fuzzy string matching with case normalization.

        This method normalizes strings to lowercase and strips whitespace BEFORE
        running the fuzzy matching algorithm. This ensures that case-only differences
        like 'Stranger Things' vs 'stranger things' are correctly identified as
        high-similarity matches and flagged as RED severity.

        Args:
            series: Pandas Series containing text data
            max_unique: Maximum unique values to analyze (prevents timeout)

        Returns:
            pd.DataFrame: DataFrame with fuzzy matching anomalies including severity
        """
        # Drop nulls for fuzzy matching (nulls handled by detect_null_values)
        clean_series = series.dropna().astype(str)

        # Create normalized version for comparison (lowercase + strip)
        normalized_series = clean_series.str.lower().str.strip()

        # Get unique normalized values
        unique_normalized = normalized_series.unique()

        if len(unique_normalized) <= 1:
            return pd.DataFrame(columns=['value', 'similar_to', 'similarity', 'issue_type', 'severity', 'original_value'])

        # Skip columns with too many unique values
        if len(unique_normalized) > max_unique:
            return pd.DataFrame(columns=['value', 'similar_to', 'similarity', 'issue_type', 'severity', 'original_value'])

        anomalies = []
        processed = set()

        # Create mapping from normalized to original values
        normalized_to_originals = {}
        for orig_val, norm_val in zip(clean_series.values, normalized_series.values):
            if norm_val not in normalized_to_originals:
                normalized_to_originals[norm_val] = []
            if orig_val not in normalized_to_originals[norm_val]:
                normalized_to_originals[norm_val].append(orig_val)

        # Use rapidfuzz.process.extract for faster matching on normalized values
        for norm_value in unique_normalized:
            if norm_value in processed:
                continue

            # Find similar normalized values using extract
            results = process.extract(
                norm_value,
                [v for v in unique_normalized if v != norm_value and v not in processed],
                scorer=fuzz.ratio,
                limit=10
            )

            similar_values = []
            for match, score, _ in results:
                if score >= self.similarity_threshold:
                    similar_values.append({
                        'normalized_value': match,
                        'similarity': score
                    })

            if similar_values:
                # Determine severity based on the lowest similarity in group
                min_similarity = min(sv['similarity'] for sv in similar_values)
                severity = self._classify_text_severity(min_similarity, 'Fuzzy Match')

                # Get all original values for this normalized value
                original_values = normalized_to_originals.get(norm_value, [norm_value])

                # Add entries for each original value
                for orig_val in original_values:
                    similar_to_values = []
                    for sv in similar_values:
                        # Get original values for the matched normalized value
                        matched_originals = normalized_to_originals.get(sv['normalized_value'], [sv['normalized_value']])
                        similar_to_values.extend(matched_originals)

                    anomalies.append({
                        'value': norm_value,  # Normalized value as key
                        'original_value': ', '.join(original_values),  # Original case-preserved values
                        'similar_to': ', '.join(similar_to_values),
                        'similarity': 100.0,
                        'issue_type': 'Fuzzy Match',
                        'severity': severity
                    })

                # Add entries for similar values
                for sv in similar_values:
                    matched_originals = normalized_to_originals.get(sv['normalized_value'], [sv['normalized_value']])
                    severity = self._classify_text_severity(sv['similarity'], 'Fuzzy Match')

                    for matched_orig in matched_originals:
                        anomalies.append({
                            'value': sv['normalized_value'],
                            'original_value': matched_orig,
                            'similar_to': norm_value,
                            'similarity': sv['similarity'],
                            'issue_type': 'Fuzzy Match',
                            'severity': severity
                        })
                        processed.add(sv['normalized_value'])

                processed.add(norm_value)

        return pd.DataFrame(anomalies)

    def detect_low_frequency(self, series: pd.Series) -> pd.DataFrame:
        """
        Detect anomalies based on low frequency (rare values).

        Values appearing less than min_frequency times are flagged as GREEN (human review).

        Args:
            series: Pandas Series containing text data

        Returns:
            pd.DataFrame: DataFrame with low frequency anomalies
        """
        # Work with non-null values
        clean_series = series.dropna().astype(str)
        value_counts = clean_series.value_counts()
        anomalies = []

        for value, count in value_counts.items():
            if count < self.min_frequency:
                anomalies.append({
                    'value': value,
                    'count': count,
                    'issue_type': 'Low Frequency',
                    'severity': 'green'  # Always human review
                })

        return pd.DataFrame(anomalies)

    def detect_case_inconsistency(self, series: pd.Series) -> pd.DataFrame:
        """
        Detect case inconsistencies (apple vs Apple vs APPLE).

        These are always GREEN severity (human review required).
        NOTE: For enhanced case detection with RED severity, use detect_case_inconsistency_enhanced().

        Args:
            series: Pandas Series containing text data

        Returns:
            pd.DataFrame: DataFrame with case inconsistency anomalies
        """
        # Work with non-null values
        clean_series = series.dropna().astype(str)
        unique_values = clean_series.unique()
        anomalies = []
        processed = set()

        # Group by normalized (lowercase) value
        case_groups = {}
        for value in unique_values:
            normalized = value.lower()
            if normalized not in case_groups:
                case_groups[normalized] = []
            case_groups[normalized].append(value)

        # Find groups with multiple different case variations
        for normalized, variants in case_groups.items():
            if len(variants) > 1:
                for variant in variants:
                    if variant not in processed:
                        anomalies.append({
                            'value': variant,
                            'variants': ', '.join(variants),
                            'issue_type': 'Case Inconsistency',
                            'severity': 'green'  # Always human review
                        })
                        processed.add(variant)

        return pd.DataFrame(anomalies)

    def detect_case_inconsistency_enhanced(self, series: pd.Series) -> pd.DataFrame:
        """
        Detect case inconsistencies using STRICT lowercase normalization.

        This method implements a 3-step process:
        1. Create a temporary evaluation Series with .astype(str).str.strip().str.lower()
        2. Map original data rows back to normalized keys
        3. Flag any group with multiple unique original representations as RED

        Example:
        - 'Lucifer' and 'lucifer' both normalize to 'lucifer' -> RED "Inconsistent Capitalization"
        - 'Stranger Things' and 'stranger things' -> RED

        This runs BEFORE fuzzy matching to catch exact case variations.

        Args:
            series: Pandas Series containing text data

        Returns:
            pd.DataFrame: DataFrame with case variation anomalies (RED severity)
        """
        # STEP 1: Strict normalization - create temporary evaluation Series
        # Drop nulls first, then apply: astype(str).strip().lower()
        clean_series = series.dropna().astype(str)

        # Apply the strict normalization: strip whitespace AND convert to lowercase
        normalized_series = clean_series.str.strip().str.lower()

        # STEP 2: Cross-variant grouping - map original to normalized
        # Create a mapping: normalized_key -> list of original values
        normalized_to_originals = {}

        for orig_val, norm_val in zip(clean_series.values, normalized_series.values):
            if norm_val not in normalized_to_originals:
                normalized_to_originals[norm_val] = set()
            normalized_to_originals[norm_val].add(orig_val)

        # STEP 3: Traffic Light Assignment
        # Find groups with multiple original representations (case variations)
        anomalies = []

        for norm_key, original_variants in normalized_to_originals.items():
            # If there's more than one original representation for the same lowercase key
            if len(original_variants) > 1:
                # This is an exact case discrepancy - RED severity
                sorted_variants = sorted(original_variants)

                # Add entry for each variant showing all variants in the group
                for variant in sorted_variants:
                    anomalies.append({
                        'normalized_value': norm_key,
                        'original_value': variant,
                        'variants': ', '.join(sorted_variants),
                        'variant_count': len(original_variants),
                        'issue_type': 'Inconsistent Capitalization',
                        'severity': 'red'  # RED - unambiguous case typo
                    })

        return pd.DataFrame(anomalies)

    def detect_whitespace_issues(self, series: pd.Series) -> pd.DataFrame:
        """
        Detect whitespace issues (leading/trailing/double spaces).

        These are always RED severity (data quality issues requiring attention).

        Args:
            series: Pandas Series containing text data

        Returns:
            pd.DataFrame: DataFrame with whitespace anomaly issues
        """
        # Work with non-null values
        clean_series = series.dropna().astype(str)
        unique_values = clean_series.unique()
        anomalies = []

        for value in unique_values:
            issues = []

            # Leading space
            if value != value.lstrip():
                issues.append('Leading Space')

            # Trailing space
            if value != value.rstrip():
                issues.append('Trailing Space')

            # Double spaces
            if '  ' in value:
                issues.append('Double Space')

            # Tab characters
            if '\t' in value:
                issues.append('Tab Character')

            if issues:
                anomalies.append({
                    'value': value,
                    'issues': ', '.join(issues),
                    'issue_type': 'Whitespace',
                    'severity': 'red'  # RED - data quality issue
                })

        return pd.DataFrame(anomalies)

    def get_value_distribution(self, series: pd.Series) -> pd.DataFrame:
        """
        Get the full distribution of values with their counts.

        Args:
            series: Pandas Series containing text data

        Returns:
            pd.DataFrame: DataFrame with value counts
        """
        clean_series = series.dropna().astype(str)
        return clean_series.value_counts().reset_index().rename(
            columns={'index': 'value', 0: 'count'}
        )

    def detect_all(self, series: pd.Series) -> Dict[str, pd.DataFrame]:
        """
        Run all detection methods on a series.

        DETECTION ORDER (critical for proper severity classification):
        1. Null/NaN values -> RED severity
        2. Case inconsistencies (enhanced) -> RED severity
        3. Whitespace issues -> RED severity
        4. Fuzzy string matching -> RED/YELLOW severity
        5. Low frequency values -> GREEN severity

        Args:
            series: Pandas Series containing text data

        Returns:
            Dict[str, pd.DataFrame]: Dictionary with detection results
        """
        results = {}

        # STEP 1: Pre-check for null/NaN values (RED severity)
        null_values = self.detect_null_values(series)
        if not null_values.empty:
            results['null_values'] = null_values

        # STEP 2: Enhanced case inconsistency detection (RED severity)
        # Uses strict .astype(str).str.strip().str.lower() normalization
        # Detects exact case variations like 'Stranger Things' vs 'stranger things'
        case_variants = self.detect_case_inconsistency_enhanced(series)
        if not case_variants.empty:
            results['case_variants'] = case_variants

        # STEP 3: Whitespace detection (RED severity)
        whitespace = self.detect_whitespace_issues(series)
        if not whitespace.empty:
            results['whitespace'] = whitespace

        # STEP 4: Fuzzy matching with case normalization (RED/YELLOW severity)
        # Runs on normalized lowercase values to find hidden typos
        fuzzy = self.detect_fuzzy(series)
        if not fuzzy.empty:
            results['fuzzy'] = fuzzy

        # STEP 5: Low frequency detection (GREEN severity)
        frequency = self.detect_low_frequency(series)
        if not frequency.empty:
            results['low_frequency'] = frequency

        return results

    def detect_all_columns(self, df: pd.DataFrame) -> Dict[str, Dict]:
        """
        Detect text anomalies across all string/object columns in a DataFrame.

        Args:
            df: Input DataFrame

        Returns:
            Dict[str, Dict]: Dictionary mapping column names to detection results
        """
        results = {}

        # Get only object (string) columns
        string_columns = df.select_dtypes(include=['object']).columns

        for col in string_columns:
            col_results = self.detect_all(df[col])
            if col_results:
                # Add value distribution
                col_results['distribution'] = self.get_value_distribution(df[col])
                results[col] = col_results

        return results


class NumericAnomalyDetector:
    """
    A class for detecting numeric anomalies using statistical methods.

    Implements two algorithms:
    - IQR (Interquartile Range): Identifies outliers outside Q1 - IQR*mult and Q3 + IQR*mult
    - Z-Score: Identifies values more than N standard deviations from the mean

    Traffic Light Severity:
    - RED: Extreme outliers (Z-Score > 4.0 or IQR < 1.0) - critical
    - YELLOW: Moderate outliers (Z-Score 3.0-4.0 or IQR 1.0-1.5) - needs context
    - GREEN: Edge cases - human decision required

    Attributes:
        iqr_multiplier: Multiplier for IQR method (default: 1.5)
        zscore_threshold: Threshold for Z-Score method (default: 3.0)
    """

    def __init__(self, iqr_multiplier: float = 1.5, zscore_threshold: float = 3.0):
        """
        Initialize the NumericAnomalyDetector.

        Args:
            iqr_multiplier: Multiplier for IQR (default: 1.5)
            zscore_threshold: Z-Score threshold (default: 3.0)
        """
        self.iqr_multiplier = iqr_multiplier
        self.zscore_threshold = zscore_threshold

    def set_parameters(self, iqr_multiplier: float, zscore_threshold: float) -> None:
        """
        Update detection parameters.

        Args:
            iqr_multiplier: New IQR multiplier value
            zscore_threshold: New Z-Score threshold value
        """
        self.iqr_multiplier = iqr_multiplier
        self.zscore_threshold = zscore_threshold

    def detect_null_values(self, series: pd.Series) -> pd.DataFrame:
        """
        Pre-check method to detect null/NaN values in numeric columns.

        Args:
            series: Pandas Series containing numeric data

        Returns:
            pd.DataFrame: DataFrame with null value anomalies
        """
        anomalies = []

        null_mask = series.isna()
        null_count = null_mask.sum()

        if null_count > 0:
            null_indices = series[null_mask].index.tolist()

            for idx in null_indices:
                anomalies.append({
                    'index': idx,
                    'value': None,
                    'issue_type': 'Missing Data',
                    'severity': 'red',
                    'null_type': 'NaN/NULL'
                })

        if not anomalies:
            return pd.DataFrame(columns=['index', 'value', 'issue_type', 'severity', 'null_type'])

        return pd.DataFrame(anomalies)

    def _classify_numeric_severity(self, z_score: float, iqr_outlier: bool) -> str:
        """
        Classify numeric anomaly severity using traffic light system.

        Args:
            z_score: Absolute Z-score value
            iqr_outlier: Whether it's an IQR outlier

        Returns:
            str: Severity level ('red', 'yellow', or 'green')
        """
        # Extreme outliers are RED
        if z_score > 4.0:
            return 'red'

        # Moderate outliers are YELLOW
        if z_score > 3.0:
            return 'yellow'

        # If IQR flagged but not extreme Z-score
        if iqr_outlier:
            return 'yellow'

        # Default to green (edge case)
        return 'green'

    def detect_iqr(self, series: pd.Series) -> pd.Series:
        """
        Detect outliers using the IQR (Interquartile Range) method.

        Values are considered outliers if they fall below Q1 - IQR*multiplier
        or above Q3 + IQR*multiplier.

        Args:
            series: Pandas Series containing numeric data

        Returns:
            pd.Series: Boolean Series where True indicates an outlier
        """
        # Calculate quartiles
        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1

        # Calculate bounds
        lower_bound = q1 - (self.iqr_multiplier * iqr)
        upper_bound = q3 + (self.iqr_multiplier * iqr)

        # Identify outliers
        outliers = (series < lower_bound) | (series > upper_bound)

        return outliers

    def detect_zscore(self, series: pd.Series) -> pd.Series:
        """
        Detect outliers using the Z-Score method.

        Values are considered outliers if their Z-score exceeds the threshold.

        Args:
            series: Pandas Series containing numeric data

        Returns:
            pd.Series: Boolean Series where True indicates an outlier
        """
        mean = series.mean()
        std = series.std()

        # Avoid division by zero
        if std == 0:
            return pd.Series([False] * len(series), index=series.index)

        # Calculate Z-scores
        z_scores = np.abs((series - mean) / std)

        # Identify outliers
        outliers = z_scores > self.zscore_threshold

        return outliers

    def detect(self, series: pd.Series, method: str = 'both') -> pd.DataFrame:
        """
        Detect numeric anomalies using specified method(s).

        Args:
            series: Pandas Series containing numeric data
            method: Detection method - 'iqr', 'zscore', or 'both' (default: 'both')

        Returns:
            pd.DataFrame: DataFrame with anomaly detection results containing:
                - index: Original index of the value
                - value: The numeric value
                - z_score: Z-score value
                - iqr_outlier: Boolean for IQR method
                - zscore_outlier: Boolean for Z-Score method
                - is_anomaly: True if flagged by either method
                - severity: Traffic light severity (red/yellow/green)
        """
        results = []

        # STEP 1: Check for null values first
        null_results = self.detect_null_values(series)
        if not null_results.empty:
            results.extend(null_results.to_dict('records'))

        # STEP 2: Work only with non-null numeric values for outlier detection
        clean_series = series.dropna()

        if len(clean_series) == 0:
            if results:
                return pd.DataFrame(results)
            return pd.DataFrame(columns=['index', 'value', 'z_score', 'iqr_outlier', 'zscore_outlier', 'is_anomaly', 'severity'])

        mean = clean_series.mean()
        std = clean_series.std() if clean_series.std() > 0 else 1

        # Detect using IQR
        if method in ['iqr', 'both']:
            iqr_outliers = self.detect_iqr(clean_series)
        else:
            iqr_outliers = pd.Series([False] * len(clean_series), index=clean_series.index)

        # Detect using Z-Score
        if method in ['zscore', 'both']:
            zscore_outliers = self.detect_zscore(clean_series)
        else:
            zscore_outliers = pd.Series([False] * len(clean_series), index=clean_series.index)

        # Combine results
        for idx in clean_series.index:
            value = clean_series[idx]
            iqr_flag = iqr_outliers.get(idx, False)
            zscore_flag = zscore_outliers.get(idx, False)

            # Calculate actual z_score
            z_score = abs((value - mean) / std) if std > 0 else 0

            # Classify severity
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

        return pd.DataFrame(results)

    def detect_all_columns(self, df: pd.DataFrame, method: str = 'both') -> Dict[str, pd.DataFrame]:
        """
        Detect numeric anomalies across all numeric columns in a DataFrame.

        Args:
            df: Input DataFrame
            method: Detection method - 'iqr', 'zscore', or 'both'

        Returns:
            Dict[str, pd.DataFrame]: Dictionary mapping column names to anomaly DataFrames
        """
        results = {}

        # Get only numeric columns
        numeric_columns = df.select_dtypes(include=[np.number]).columns

        for col in numeric_columns:
            anomalies = self.detect(df[col], method=method)
            # Filter to only actual anomalies (excluding non-anomaly null records)
            anomalies = anomalies[anomalies['is_anomaly'] == True]
            if not anomalies.empty:
                results[col] = anomalies

        return results
