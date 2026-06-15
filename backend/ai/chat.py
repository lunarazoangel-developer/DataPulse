import json
import re
from typing import Any, Dict, List, Optional, Tuple

import httpx

import config
from ai.actions import (
    ACTION_LABELS,
    SUPPORTED_ACTIONS,
    coerce_proposal,
    normalize_summary,
)


class AIAvailabilityError(Exception):
    pass


class AIRuntimeError(Exception):
    pass


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)


def build_system_prompt(payload: Dict[str, Any]) -> str:
    metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
    schema_count = metadata.get("total_tables", "?")
    red_count = metadata.get("red_anomalies_count", 0)
    yellow_count = metadata.get("yellow_anomalies_count", 0)
    green_count = metadata.get("green_anomalies_count", 0)
    redacted = metadata.get("total_redacted_columns", 0)

    actions_doc = "\n".join(
        f"- `{name}` — {ACTION_LABELS.get(name, name)}"
        for name in SUPPORTED_ACTIONS
    )

    return (
        "You are DataPulse AI, a senior data-quality analyst. "
        "You are reviewing an AI-ready data quality report produced by the DataPulse "
        "pipeline. Your job is to read the JSON report the user provides and propose "
        "concrete, safe cleanup actions that will be applied to the underlying tables.\n\n"
        f"Report overview: {schema_count} table(s), {red_count} red anomalies, "
        f"{yellow_count} yellow anomalies, {green_count} green anomalies, {redacted} "
        "redacted sensitive column(s).\n\n"
        "You MUST respond with a single JSON object (no prose, no markdown fences) with "
        "this exact shape:\n"
        "{\n"
        '  "summary": "Short natural-language overview of what you propose and why",\n'
        '  "proposals": [\n'
        "    {\n"
        '      "id": "p1",\n'
        '      "risk": "low" | "medium" | "high",\n'
        '      "title": "Short title shown to the user",\n'
        '      "description": "Why this change is needed and what it does",\n'
        '      "table": "exact table name as in the report",\n'
        '      "column": "exact column name (or empty for table-level actions)",\n'
        '      "action": "one of the supported actions below",\n'
        '      "params": { ... action-specific parameters ... }\n'
        "    }\n"
        "  ]\n"
        "}\n\n"
        f"Supported actions and their parameters:\n{actions_doc}\n\n"
        "Action parameter schemas:\n"
        "- replace_regex: { pattern: string, replacement: string }\n"
        "- fill_null: { value: any, also_fill_placeholders?: bool }\n"
        "- cast_type: { target_type: 'Int64'|'Float64'|'String'|'Boolean'|'Date'|'Datetime'|... }\n"
        "- drop_duplicates: { subset?: string | string[] } (omit subset for full-row dedup)\n"
        "- normalize_case: { case: 'lower'|'upper'|'title' }\n"
        "- strip_whitespace: {}\n"
        "- standardize_date: { target_format: '%Y-%m-%d', input_formats: string[] }\n"
        "- clip_values: { lower?: number, upper?: number }\n"
        "- drop_rows: { column: string, operator: 'is_null'|'not_null'|'equals'|'not_equals'|'matches'|'between', value?: any }\n\n"
        "Guidelines:\n"
        "1. Order proposals from most impactful (high risk / data loss) to least.\n"
        "2. Only propose destructive actions (drop_rows, drop_duplicates, cast_type) when "
        "you can justify them with concrete evidence from the report.\n"
        "3. Never propose to modify redacted/sensitive columns.\n"
        "4. If the report has no actionable issues, return an empty `proposals` array and "
        "explain in `summary`.\n"
        "5. Keep `summary` under 400 characters; keep `title` under 80."
    )


def build_user_message(payload: Dict[str, Any], user_message: Optional[str] = None) -> str:
    intro = (
        "Here is the AI-ready data quality report produced by DataPulse. "
        "Return your plan as a single JSON object that follows the schema in the system "
        "prompt. Do not include any other text.\n\n"
    )
    body = json.dumps(payload, indent=2, default=str, ensure_ascii=False)
    if user_message:
        return f"{intro}{body}\n\n---\nAdditional user question: {user_message}"
    return f"{intro}{body}"


def _coerce_history(history: Any) -> List[Dict[str, str]]:
    if not isinstance(history, list):
        return []
    sanitized: List[Dict[str, str]] = []
    for item in history:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in ("user", "assistant", "system"):
            continue
        if not isinstance(content, str) or not content.strip():
            continue
        sanitized.append({"role": role, "content": content})
    return sanitized


def _extract_json_object(content: str) -> Optional[Dict[str, Any]]:
    """Tolerantly pull a JSON object out of an AI response.

    DeepSeek with `response_format=json_object` usually returns a clean JSON
    document, but in case it wraps it in fences or in a small wrapper we still
    try to find the outermost object.
    """
    if not isinstance(content, str):
        return None
    text = content.strip()
    if not text:
        return None

    fence = _JSON_FENCE_RE.search(text)
    if fence:
        text = fence.group(1)

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                parsed = json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
        else:
            return None

    if isinstance(parsed, list):
        return {"summary": "", "proposals": parsed}
    if isinstance(parsed, dict):
        return parsed
    return None


def parse_plan(content: str) -> Tuple[str, List[Dict[str, Any]]]:
    """Turn an AI message into a (summary, proposals) pair."""
    obj = _extract_json_object(content)
    if obj is None:
        return content.strip(), []

    summary = normalize_summary(obj.get("summary"))
    raw_proposals = obj.get("proposals") or []
    if not isinstance(raw_proposals, list):
        raw_proposals = []

    proposals: List[Dict[str, Any]] = []
    seen_ids = set()
    for raw in raw_proposals:
        norm = coerce_proposal(raw)
        if not norm:
            continue
        base_id = norm["id"]
        candidate = base_id
        i = 2
        while candidate in seen_ids:
            candidate = f"{base_id}_{i}"
            i += 1
        norm["id"] = candidate
        seen_ids.add(candidate)
        proposals.append(norm)

    return summary, proposals


async def call_deepseek(
    payload: Dict[str, Any],
    history: Optional[List[Dict[str, str]]] = None,
    user_message: Optional[str] = None,
) -> str:
    if not config.is_ai_enabled():
        raise AIAvailabilityError(
            "AI service not configured. Set DEEPSEEK_API_KEY in backend/.env"
        )

    messages: List[Dict[str, str]] = [
        {"role": "system", "content": build_system_prompt(payload)},
        {"role": "user", "content": build_user_message(payload, user_message)},
    ]
    messages.extend(_coerce_history(history))

    request_body = {
        "model": config.DEEPSEEK_MODEL,
        "messages": messages,
        "stream": False,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
    }
    headers = {
        "Authorization": f"Bearer {config.DEEPSEEK_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=config.DEEPSEEK_TIMEOUT) as client:
            response = await client.post(
                config.DEEPSEEK_API_URL, headers=headers, json=request_body
            )
    except httpx.HTTPError as exc:
        raise AIRuntimeError(f"Could not reach DeepSeek API: {exc}") from exc

    if response.status_code >= 400:
        detail: str
        try:
            detail = response.text
        except Exception:
            detail = f"HTTP {response.status_code}"

        lower_detail = detail.lower()
        if "model" in lower_detail and (
            "not support" in lower_detail
            or "supported" in lower_detail
            or "invalid_request_error" in lower_detail
        ):
            raise AIRuntimeError(
                f"DeepSeek rejected the model name '{config.DEEPSEEK_MODEL}'. "
                "DeepSeek is case-sensitive — use the exact lowercase id such as "
                "'deepseek-v4-flash' or 'deepseek-v4-pro'. "
                f"Original error: {detail[:300]}"
            )

        raise AIRuntimeError(f"DeepSeek API error ({response.status_code}): {detail[:500]}")

    try:
        data = response.json()
    except json.JSONDecodeError as exc:
        raise AIRuntimeError(f"Invalid JSON from DeepSeek: {exc}") from exc

    choices = data.get("choices") or []
    if not choices:
        raise AIRuntimeError("DeepSeek returned no choices")

    message = choices[0].get("message") or {}
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise AIRuntimeError("DeepSeek returned an empty response")

    return content.strip()
