import json
import logging
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

import config
from ai.actions import (
    ACTION_LABELS,
    SUPPORTED_ACTIONS,
    coerce_proposal,
    normalize_summary,
    render_action_catalog,
)


logger = logging.getLogger(__name__)


class AIAvailabilityError(Exception):
    pass


class AIRuntimeError(Exception):
    pass


class PayloadTooLargeError(Exception):
    """Raised when the assembled chat payload exceeds the configured token cap."""

    def __init__(self, estimated_tokens: int, threshold: int):
        self.estimated_tokens = estimated_tokens
        self.threshold = threshold
        super().__init__(
            f"Payload demasiado grande: ~{estimated_tokens} tokens estimados "
            f"(cap: {threshold})."
        )


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\}|\[.*?\])\s*```", re.DOTALL)


_HISTORY_TURN_CAP = 4


_TOKEN_ESTIMATE_DIVISOR = 4


_INSTRUCTIONS_PATH = Path(__file__).resolve().parent / "instructions.md"

_BUILTIN_FALLBACK_PROMPT = (
    "You are DataPulse AI, a senior data-quality analyst. "
    "You are reviewing an AI-ready data quality report produced by the DataPulse "
    "pipeline. Your job is to read the JSON report the user provides and propose "
    "concrete, safe cleanup actions that will be applied to the underlying tables.\n\n"
    "If `violation_count` is N, treat N as the rows affected in the full table, "
    "not just the samples shown. Design proposals that cover the entire class of "
    "the problem.\n\n"
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
    "Supported actions are listed in the catalog injected below."
)


@lru_cache(maxsize=1)
def _load_instructions_text() -> str:
    """Read the external system prompt from disk (cached for process lifetime)."""
    try:
        return _INSTRUCTIONS_PATH.read_text(encoding="utf-8")
    except FileNotFoundError:
        logger.warning(
            "instructions.md not found at %s, falling back to built-in prompt",
            _INSTRUCTIONS_PATH,
        )
        return _BUILTIN_FALLBACK_PROMPT


def build_system_prompt(payload: Dict[str, Any]) -> str:
    metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
    schema_count = metadata.get("total_tables", "?")
    red_count = metadata.get("red_anomalies_count", 0)
    yellow_count = metadata.get("yellow_anomalies_count", 0)
    green_count = metadata.get("green_anomalies_count", 0)
    redacted = metadata.get("total_redacted_columns", 0)

    base = _load_instructions_text()
    overview = (
        f"\n\n---\n\n## Resumen del reporte en turno\n"
        f"{schema_count} tabla(s), {red_count} anomalías rojas, "
        f"{yellow_count} amarillas, {green_count} verdes, "
        f"{redacted} columna(s) redactada(s).\n\n"
        f"## Catálogo de acciones (inyectado automáticamente)\n\n"
        f"{render_action_catalog()}"
    )
    return base + overview


def build_user_message(payload: Dict[str, Any], user_message: Optional[str] = None) -> str:
    intro = (
        "Here is the AI-ready data quality report produced by DataPulse. "
        "Return your plan as a single JSON object that follows the schema in the system "
        "prompt. Do not include any other text.\n\n"
    )
    sanitized = _strip_decorative_metadata(payload)
    body = json.dumps(sanitized, indent=2, default=str, ensure_ascii=False)
    if user_message:
        return f"{intro}{body}\n\n---\nAdditional user question: {user_message}"
    return f"{intro}{body}"


def _strip_decorative_metadata(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Drop fields the model never reads but that pad the token bill."""
    if not isinstance(payload, dict):
        return payload
    meta = payload.get("metadata")
    if isinstance(meta, dict):
        meta.pop("security_note", None)
        meta.pop("generated_at", None)
    return payload


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
    return sanitized[-_HISTORY_TURN_CAP:]


def estimate_tokens(text: str) -> int:
    """Cheap heuristic: ~1 token per 4 characters. Good enough for soft caps."""
    if not text:
        return 0
    return (len(text) + _TOKEN_ESTIMATE_DIVISOR - 1) // _TOKEN_ESTIMATE_DIVISOR


def estimate_payload_tokens(
    payload: Dict[str, Any],
    history: Optional[List[Dict[str, str]]] = None,
    user_message: Optional[str] = None,
) -> int:
    """Estimate the total input tokens for a chat call (system + user + history)."""
    system_text = build_system_prompt(payload)
    user_text = build_user_message(payload, user_message)
    history_text = "".join(m.get("content", "") for m in (history or []))
    return (
        estimate_tokens(system_text)
        + estimate_tokens(user_text)
        + estimate_tokens(history_text)
    )


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

    estimated = estimate_payload_tokens(payload, history, user_message)
    cap = config.get_max_input_tokens()
    if estimated > cap:
        raise PayloadTooLargeError(estimated_tokens=estimated, threshold=cap)

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
