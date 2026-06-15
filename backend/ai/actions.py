"""Action catalog and risk hints for AI-generated proposals.

The AI emits a `proposal` describing a change it wants to apply to a table.
Each proposal must include an `action` from SUPPORTED_ACTIONS. We expose
metadata about every action (human label, parameter schema, default risk)
so the frontend can render proposals consistently and the backend can
validate and dispatch them.
"""

from __future__ import annotations

from typing import Any, Dict, List


SUPPORTED_ACTIONS: List[str] = [
    "replace_regex",
    "fill_null",
    "cast_type",
    "drop_duplicates",
    "normalize_case",
    "strip_whitespace",
    "standardize_date",
    "clip_values",
    "drop_rows",
]


# Higher number = more destructive. Used as a fallback when the AI does
# not declare a `risk` for a proposal.
ACTION_BASE_RISK: Dict[str, str] = {
    "strip_whitespace": "low",
    "normalize_case": "low",
    "fill_null": "low",
    "replace_regex": "medium",
    "standardize_date": "medium",
    "clip_values": "medium",
    "cast_type": "high",
    "drop_duplicates": "high",
    "drop_rows": "high",
}


ACTION_LABELS: Dict[str, str] = {
    "replace_regex": "Replace by regex",
    "fill_null": "Fill nulls / placeholders",
    "cast_type": "Cast column type",
    "drop_duplicates": "Drop duplicate rows",
    "normalize_case": "Normalize case",
    "strip_whitespace": "Strip whitespace",
    "standardize_date": "Standardize date format",
    "clip_values": "Clip numeric values",
    "drop_rows": "Drop rows",
}


# Whitelist of parameter names we accept per action. Anything else is dropped
# before validation, which keeps us safe from prompt-injection-style payloads.
ACTION_PARAMS_SCHEMA: Dict[str, List[str]] = {
    "replace_regex": ["pattern", "replacement"],
    "fill_null": ["value", "also_fill_placeholders"],
    "cast_type": ["target_type"],
    "drop_duplicates": ["subset"],
    "normalize_case": ["case"],
    "strip_whitespace": [],
    "standardize_date": ["target_format", "input_formats"],
    "clip_values": ["lower", "upper"],
    "drop_rows": ["operator", "value", "column"],
}


ALLOWED_TYPES = {"Int8", "Int16", "Int32", "Int64", "UInt8", "UInt16",
                 "UInt32", "UInt64", "Float32", "Float64", "String",
                 "Boolean", "Date", "Datetime"}


ALLOWED_CASES = {"lower", "upper", "title"}

ALLOWED_DROP_OPERATORS = {"is_null", "not_null", "equals", "not_equals",
                          "matches", "between"}


def coerce_proposal(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a raw proposal dict from the AI into our internal shape.

    - Trims unknown params per action.
    - Falls back `risk` to ACTION_BASE_RISK[action] when missing.
    - Ensures required scalar fields exist with safe defaults.
    """
    if not isinstance(raw, dict):
        return {}

    action = raw.get("action")
    if action not in SUPPORTED_ACTIONS:
        return {}

    allowed = ACTION_PARAMS_SCHEMA.get(action, [])
    params = raw.get("params") or {}
    if not isinstance(params, dict):
        params = {}
    clean_params = {k: params[k] for k in allowed if k in params}

    risk = raw.get("risk")
    if risk not in ("low", "medium", "high"):
        risk = ACTION_BASE_RISK.get(action, "medium")

    proposal_id = raw.get("id")
    if not isinstance(proposal_id, str) or not proposal_id.strip():
        proposal_id = f"p_{action}_{abs(hash((raw.get('table', ''), raw.get('column', ''), action))) % 10_000}"

    return {
        "id": proposal_id,
        "risk": risk,
        "title": str(raw.get("title", "")).strip() or ACTION_LABELS.get(action, action),
        "description": str(raw.get("description", "")).strip(),
        "table": str(raw.get("table", "")).strip(),
        "column": str(raw.get("column", "")).strip(),
        "action": action,
        "params": clean_params,
    }


def normalize_summary(raw: Any) -> str:
    if isinstance(raw, str):
        return raw.strip()
    if raw is None:
        return ""
    return str(raw).strip()
