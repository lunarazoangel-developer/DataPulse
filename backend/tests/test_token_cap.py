"""Verify the soft token cap emits a PayloadTooLargeError with the right numbers."""
import pytest

from ai.chat import estimate_payload_tokens, estimate_tokens, build_system_prompt
from ai.actions import coerce_proposal


def test_estimate_tokens_is_roughly_chars_over_4():
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("abcdefgh") == 2
    assert estimate_tokens("a" * 400) == 100


def test_estimate_payload_tokens_includes_system_user_and_history():
    from ai.chat import build_user_message
    import json

    payload = {"metadata": {"total_tables": 1}, "anomalies": {"red": [], "yellow": [], "green": []}}
    history = [
        {"role": "user", "content": "hola"},
        {"role": "assistant", "content": "hola, ¿en qué te ayudo?"},
    ]
    tokens = estimate_payload_tokens(payload, history=history, user_message="limpieza")
    sys_tokens = estimate_tokens(build_system_prompt(payload))
    user_tokens = estimate_tokens(build_user_message(payload, "limpieza"))
    history_tokens = estimate_tokens("".join(m["content"] for m in history))
    assert tokens == sys_tokens + user_tokens + history_tokens


def test_history_capped_to_4_turns():
    from ai.chat import _coerce_history
    history = [{"role": "user", "content": f"msg-{i}"} for i in range(20)]
    out = _coerce_history(history)
    assert len(out) == 4
    assert out[0]["content"] == "msg-16"
    assert out[-1]["content"] == "msg-19"


def test_payload_too_large_error_carries_numbers():
    from ai.chat import PayloadTooLargeError
    err = PayloadTooLargeError(estimated_tokens=40000, threshold=32768)
    assert err.estimated_tokens == 40000
    assert err.threshold == 32768
    assert "40000" in str(err)


def test_call_deepseek_raises_payload_too_large(monkeypatch):
    """When the assembled payload exceeds the cap, call_deepseek must short-circuit."""
    from ai import chat as chat_module

    monkeypatch.setattr(chat_module.config, "is_ai_enabled", lambda: True)
    monkeypatch.setattr(chat_module.config, "get_max_input_tokens", lambda: 100)
    monkeypatch.setattr(chat_module.config, "DEEPSEEK_API_URL", "http://localhost:0/nope")
    monkeypatch.setattr(chat_module.config, "DEEPSEEK_API_KEY", "sk-fake")
    monkeypatch.setattr(chat_module.config, "DEEPSEEK_MODEL", "deepseek-v4-flash")
    monkeypatch.setattr(chat_module.config, "DEEPSEEK_TIMEOUT", 1)

    import asyncio
    payload = {
        "metadata": {"total_tables": 1, "red_anomalies_count": 0, "yellow_anomalies_count": 0, "green_anomalies_count": 0, "total_redacted_columns": 0},
        "schemas": {},
        "anomalies": {"red": [], "yellow": [], "green": []},
    }
    with pytest.raises(chat_module.PayloadTooLargeError) as exc:
        asyncio.run(chat_module.call_deepseek(payload=payload))
    assert exc.value.threshold == 100
    assert exc.value.estimated_tokens > 100
