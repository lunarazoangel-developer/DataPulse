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
    "standardize_format",
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
    "standardize_format": "medium",
    "cast_type": "high",
    "drop_duplicates": "high",
    "drop_rows": "high",
}


ACTION_LABELS: Dict[str, str] = {
    "replace_regex": "Replace by regex (cover the whole class, not just samples)",
    "fill_null": "Fill nulls / placeholders",
    "cast_type": "Cast column type",
    "drop_duplicates": "Drop duplicate rows",
    "normalize_case": "Normalize case",
    "strip_whitespace": "Strip whitespace",
    "standardize_date": "Standardize date format",
    "clip_values": "Clip numeric values",
    "drop_rows": "Drop rows (prefer matches/in over equals for full-table scope)",
    "standardize_format": "Reformat string column via strptime/strftime",
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
    "standardize_format": ["input_format", "target_format", "keep_unmatched"],
}


ALLOWED_TYPES = {"Int8", "Int16", "Int32", "Int64", "UInt8", "UInt16",
                 "UInt32", "UInt64", "Float32", "Float64", "String",
                 "Boolean", "Date", "Datetime"}


ALLOWED_CASES = {"lower", "upper", "title"}

ALLOWED_DROP_OPERATORS = {"is_null", "not_null", "equals", "not_equals",
                          "in", "matches", "between"}


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


_PARAMS_DOC = {
    "replace_regex": "  { pattern: string, replacement: string }",
    "fill_null": "  { value: any, also_fill_placeholders?: bool (default true) }",
    "cast_type": "  { target_type: 'Int64'|'Float64'|'String'|'Boolean'|'Date'|'Datetime'|... }",
    "drop_duplicates": "  { subset?: string | string[] } (omit subset for full-row dedup)",
    "normalize_case": "  { case: 'lower'|'upper'|'title' }",
    "strip_whitespace": "  {}",
    "standardize_date": "  { target_format: '%Y-%m-%d', input_formats: string[] }",
    "clip_values": "  { lower?: number, upper?: number }",
    "drop_rows": "  { column: string, operator: 'is_null'|'not_null'|'equals'|'not_equals'|'in'|'matches'|'between', value?: any }",
    "standardize_format": "  { input_format: string, target_format: string, keep_unmatched?: bool (default false) }",
}


def render_action_catalog() -> str:
    """Render the supported action catalog as a markdown-style block.

    The text is injected into the system prompt loaded from
    ``backend/ai/instructions.md`` so the AI knows what actions it may emit
    and the parameter shape for each.
    """
    lines: List[str] = ["## Catálogo de acciones soportadas", ""]
    for name in SUPPORTED_ACTIONS:
        label = ACTION_LABELS.get(name, name)
        risk = ACTION_BASE_RISK.get(name, "medium")
        lines.append(f"- `{name}` (riesgo base: {risk}) — {label}")
        params = _PARAMS_DOC.get(name)
        if params:
            lines.append(params)
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"
