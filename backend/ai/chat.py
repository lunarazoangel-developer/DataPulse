import json
from typing import Any, Dict, List, Optional

import httpx

import config


class AIAvailabilityError(Exception):
    pass


class AIRuntimeError(Exception):
    pass


def build_system_prompt(payload: Dict[str, Any]) -> str:
    metadata = payload.get("metadata", {}) if isinstance(payload, dict) else {}
    schema_count = metadata.get("total_tables", "?")
    red_count = metadata.get("red_anomalies_count", 0)
    yellow_count = metadata.get("yellow_anomalies_count", 0)
    green_count = metadata.get("green_anomalies_count", 0)
    redacted = metadata.get("total_redacted_columns", 0)

    return (
        "You are DataPulse AI, a senior data-quality analyst. "
        "You are reviewing an AI-ready data quality report produced by the DataPulse "
        "pipeline. Your job is to read the JSON report the user provides, identify the "
        "most important discrepancies that should be fixed first, and explain them in "
        "clear, actionable language. "
        f"\n\nReport overview: {schema_count} table(s), {red} red anomalies, "
        f"{yellow} yellow anomalies, {green} green anomalies, {redacted} redacted "
        "sensitive column(s). "
        "\n\nWhen you answer:\n"
        "1. Group findings by severity (red first, then yellow, then green).\n"
        "2. For each finding, name the table and column, explain the risk in one "
        "sentence, and suggest a concrete fix (regex, type cast, deduplication, etc.).\n"
        "3. Highlight any sensitive / PII columns that were redacted so the user knows "
        "those exist.\n"
        "4. Keep the response concise and use markdown with short bullet lists."
    )


def build_user_message(payload: Dict[str, Any], user_message: Optional[str] = None) -> str:
    intro = (
        "Here is the AI-ready data quality report produced by DataPulse. "
        "Please analyze it and list the discrepancies that need to be fixed, "
        "ordered by priority:\n\n"
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
