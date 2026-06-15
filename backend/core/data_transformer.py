"""Apply an AI proposal to a Polars DataFrame.

Each proposal is dispatched by `action` to a small transformer. The
transformer must return `(new_df, rows_changed)`. All operations are
wrapped in try/except so a single bad proposal never aborts the batch.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

import polars as pl

from ai.actions import (
    ACTION_PARAMS_SCHEMA,
    ALLOWED_CASES,
    ALLOWED_DROP_OPERATORS,
    ALLOWED_TYPES,
    SUPPORTED_ACTIONS,
    coerce_proposal,
)


class TransformError(Exception):
    pass


_PL_DTYPES = {
    "Int8": pl.Int8, "Int16": pl.Int16, "Int32": pl.Int32, "Int64": pl.Int64,
    "UInt8": pl.UInt8, "UInt16": pl.UInt16, "UInt32": pl.UInt32, "UInt64": pl.UInt64,
    "Float32": pl.Float32, "Float64": pl.Float64,
    "String": pl.Utf8, "Boolean": pl.Boolean,
    "Date": pl.Date, "Datetime": pl.Datetime,
}


_PLACEHOLDER_VALUES = {"", "n/a", "na", "null", "none", "nan", "s/d", "--", "-"}


def _validate_columns(df: pl.DataFrame, table: str, column: str) -> None:
    if column and column not in df.columns:
        raise TransformError(f"Column '{column}' not found in table '{table}'")


def _replace_regex(df: pl.DataFrame, table: str, params: Dict[str, Any]) -> Tuple[pl.DataFrame, int]:
    column = params.get("_column", "")
    pattern = params.get("pattern")
    replacement = params.get("replacement", "")
    if not pattern:
        raise TransformError("replace_regex requires 'pattern'")
    _validate_columns(df, table, column)

    try:
        re.compile(pattern)
    except re.error as exc:
        raise TransformError(f"Invalid regex '{pattern}': {exc}") from exc

    if df[column].dtype != pl.Utf8:
        df = df.with_columns(pl.col(column).cast(pl.Utf8))

    before = df[column].fill_null("").to_list()
    after_series = df[column].str.replace_all(pattern, replacement)
    df_new = df.with_columns(after_series.alias(column))
    after = df_new[column].fill_null("").to_list()
    changed = sum(1 for a, b in zip(before, after) if a != b)
    return df_new, changed


def _fill_null(df: pl.DataFrame, table: str, params: Dict[str, Any]) -> Tuple[pl.DataFrame, int]:
    column = params.get("_column", "")
    value = params.get("value", "")
    also_placeholders = bool(params.get("also_fill_placeholders", True))
    _validate_columns(df, table, column)

    changed = 0
    series = df[column]

    if series.is_null().sum() > 0:
        changed += int(series.is_null().sum())
        series = series.fill_null(value)

    if also_placeholders and series.dtype == pl.Utf8:
        lowered = series.str.to_lowercase()
        mask = lowered.is_in(list(_PLACEHOLDER_VALUES))
        if mask.any():
            changed += int(mask.sum())
            series = pl.when(mask).then(pl.lit(value)).otherwise(series)

    if changed == 0:
        return df, 0
    return df.with_columns(series.alias(column)), changed


def _cast_type(df: pl.DataFrame, table: str, params: Dict[str, Any]) -> Tuple[pl.DataFrame, int]:
    column = params.get("_column", "")
    target = params.get("target_type")
    if target not in ALLOWED_TYPES:
        raise TransformError(f"cast_type: target_type must be one of {sorted(ALLOWED_TYPES)}")
    _validate_columns(df, table, column)

    pl_type = _PL_DTYPES[target]
    try:
        new_series = df[column].cast(pl_type, strict=False)
    except Exception as exc:
        raise TransformError(f"cast_type failed for '{column}': {exc}") from exc
    return df.with_columns(new_series.alias(column)), df.height


def _drop_duplicates(df: pl.DataFrame, table: str, params: Dict[str, Any]) -> Tuple[pl.DataFrame, int]:
    subset = params.get("subset")
    if subset is not None:
        if isinstance(subset, str):
            subset = [subset]
        if not isinstance(subset, list) or not subset:
            raise TransformError("drop_duplicates: 'subset' must be a string or list of strings")
        for c in subset:
            _validate_columns(df, table, c)
        before = df.height
        df_new = df.unique(subset=subset, maintain_order=True)
    else:
        before = df.height
        df_new = df.unique(maintain_order=True)
    return df_new, before - df_new.height


def _normalize_case(df: pl.DataFrame, table: str, params: Dict[str, Any]) -> Tuple[pl.DataFrame, int]:
    column = params.get("_column", "")
    case = params.get("case", "lower")
    if case not in ALLOWED_CASES:
        raise TransformError(f"normalize_case: case must be one of {sorted(ALLOWED_CASES)}")
    _validate_columns(df, table, column)

    if df[column].dtype != pl.Utf8:
        return df, 0

    if case == "lower":
        new = df[column].str.to_lowercase()
    elif case == "upper":
        new = df[column].str.to_uppercase()
    else:
        new = df[column].str.to_titlecase()

    before = df[column].fill_null("").to_list()
    df_new = df.with_columns(new.alias(column))
    after = df_new[column].fill_null("").to_list()
    changed = sum(1 for a, b in zip(before, after) if a != b)
    return df_new, changed


def _strip_whitespace(df: pl.DataFrame, table: str, params: Dict[str, Any]) -> Tuple[pl.DataFrame, int]:
    column = params.get("_column", "")
    _validate_columns(df, table, column)
    if df[column].dtype != pl.Utf8:
        return df, 0
    before = df[column].fill_null("").to_list()
    df_new = df.with_columns(df[column].str.strip_chars().alias(column))
    after = df_new[column].fill_null("").to_list()
    changed = sum(1 for a, b in zip(before, after) if a != b)
    return df_new, changed


def _standardize_date(df: pl.DataFrame, table: str, params: Dict[str, Any]) -> Tuple[pl.DataFrame, int]:
    column = params.get("_column", "")
    target_format = params.get("target_format", "%Y-%m-%d")
    input_formats = params.get("input_formats") or [
        "%Y-%m-%d", "%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y",
        "%d-%m-%Y", "%m-%d-%Y", "%Y-%m-%dT%H:%M:%S",
    ]
    if not isinstance(input_formats, list) or not input_formats:
        raise TransformError("standardize_date: input_formats must be a non-empty list")
    _validate_columns(df, table, column)

    if df.height == 0:
        return df, 0

    if df[column].dtype != pl.Utf8:
        df = df.with_columns(df[column].cast(pl.Utf8).alias(column))

    before = [str(v) if v is not None else "" for v in df[column].to_list()]

    parsed_expr: Optional[Any] = None
    for fmt in input_formats:
        attempt = pl.col(column).str.strptime(pl.Datetime, fmt, strict=False)
        parsed_expr = attempt if parsed_expr is None else parsed_expr.fill_null(attempt)

    df_new = df.with_columns(parsed_expr.dt.strftime(target_format).alias(column))

    after = [str(v) if v is not None else "" for v in df_new[column].to_list()]
    changed = sum(1 for a, b in zip(before, after) if a != b)
    return df_new, changed


def _clip_values(df: pl.DataFrame, table: str, params: Dict[str, Any]) -> Tuple[pl.DataFrame, int]:
    column = params.get("_column", "")
    lower = params.get("lower")
    upper = params.get("upper")
    if lower is None and upper is None:
        raise TransformError("clip_values: at least one of 'lower'/'upper' is required")
    _validate_columns(df, table, column)

    if df[column].dtype.is_numeric():
        new_series = df[column].clip(lower, upper)
    else:
        try:
            numeric = df[column].cast(pl.Float64, strict=False)
            new_series = numeric.clip(lower, upper).cast(df[column].dtype)
        except Exception as exc:
            raise TransformError(f"clip_values: column '{column}' is not numeric ({exc})") from exc

    before = df[column].to_list()
    df_new = df.with_columns(new_series.alias(column))
    after = df_new[column].to_list()
    changed = sum(1 for a, b in zip(before, after) if a != b)
    return df_new, changed


def _drop_rows(df: pl.DataFrame, table: str, params: Dict[str, Any]) -> Tuple[pl.DataFrame, int]:
    column = params.get("column") or params.get("_column", "")
    operator = params.get("operator", "is_null")
    value = params.get("value")
    if operator not in ALLOWED_DROP_OPERATORS:
        raise TransformError(f"drop_rows: operator must be one of {sorted(ALLOWED_DROP_OPERATORS)}")
    if operator not in ("is_null", "not_null"):
        _validate_columns(df, table, column)

    if operator == "is_null":
        mask = df[column].is_null() if column else pl.lit(False)
    elif operator == "not_null":
        mask = df[column].is_not_null() if column else pl.lit(False)
    elif operator == "equals":
        mask = df[column] == value
    elif operator == "not_equals":
        mask = df[column] != value
    elif operator == "matches":
        pattern = re.compile(str(value))
        mask = df[column].cast(pl.Utf8).str.contains(pattern)
    else:
        lo, hi = value if isinstance(value, (list, tuple)) and len(value) == 2 else (None, None)
        if lo is None or hi is None:
            raise TransformError("drop_rows: 'between' requires value=[lower, upper]")
        mask = (df[column] >= lo) & (df[column] <= hi)

    before = df.height
    df_new = df.filter(~mask)
    return df_new, before - df_new.height


_DISPATCH = {
    "replace_regex": _replace_regex,
    "fill_null": _fill_null,
    "cast_type": _cast_type,
    "drop_duplicates": _drop_duplicates,
    "normalize_case": _normalize_case,
    "strip_whitespace": _strip_whitespace,
    "standardize_date": _standardize_date,
    "clip_values": _clip_values,
    "drop_rows": _drop_rows,
}


def apply_proposal(
    df: pl.DataFrame,
    proposal: Dict[str, Any],
) -> Tuple[pl.DataFrame, int]:
    """Apply a single proposal to a DataFrame. Returns (new_df, rows_changed)."""
    norm = coerce_proposal(proposal)
    if not norm:
        raise TransformError("Invalid or unsupported proposal")

    action = norm["action"]
    if action not in SUPPORTED_ACTIONS:
        raise TransformError(f"Unsupported action: {action}")

    params = dict(norm.get("params") or {})
    params["_column"] = norm.get("column", "")

    if not params["_column"] and action != "drop_rows":
        if action == "drop_duplicates" and not params.get("subset"):
            pass
        else:
            raise TransformError(f"Action '{action}' requires a 'column'")

    table = norm.get("table") or "(unknown)"
    handler = _DISPATCH[action]
    return handler(df, table, params)


def atomic_write_csv(df: pl.DataFrame, path: str) -> None:
    """Write CSV to a sibling .tmp and rename to keep the file atomic on disk."""
    directory = os.path.dirname(os.path.abspath(path)) or "."
    tmp_path = f"{path}.tmp"
    df.write_csv(tmp_path)
    os.replace(tmp_path, path)
