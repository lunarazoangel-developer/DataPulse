"""Verify the external system prompt is loaded and contains the key sections."""
import re
from pathlib import Path

import pytest


def test_instructions_file_exists():
    path = Path(__file__).resolve().parent.parent / "ai" / "instructions.md"
    assert path.exists(), f"instructions.md missing at {path}"


def test_instructions_file_has_full_table_coverage_section():
    path = Path(__file__).resolve().parent.parent / "ai" / "instructions.md"
    text = path.read_text(encoding="utf-8")
    assert "Cobertura de la tabla completa" in text, (
        "instructions.md must contain the 'Cobertura de la tabla completa' section"
    )


def test_instructions_file_has_durable_rules():
    path = Path(__file__).resolve().parent.parent / "ai" / "instructions.md"
    text = path.read_text(encoding="utf-8")
    assert "Reglas duras" in text
    assert "redactad" in text.lower() or "redacted" in text
    assert "nunca" in text.lower()


def test_build_system_prompt_loads_file():
    from ai.chat import build_system_prompt, _load_instructions_text

    cached = _load_instructions_text()
    assert isinstance(cached, str)
    assert len(cached) > 200
    prompt = build_system_prompt({"metadata": {}})
    assert "Catálogo de acciones" in prompt
    assert "replace_regex" in prompt
    assert "drop_rows" in prompt
    assert "standardize_format" in prompt


def test_build_system_prompt_includes_anomaly_overview():
    from ai.chat import build_system_prompt

    payload = {"metadata": {
        "total_tables": 3,
        "red_anomalies_count": 7,
        "yellow_anomalies_count": 4,
        "green_anomalies_count": 2,
        "total_redacted_columns": 1,
    }}
    prompt = build_system_prompt(payload)
    assert "3 tabla" in prompt
    assert "7" in prompt
    assert "1 columna" in prompt or "1 " in prompt


def test_fallback_when_file_missing(monkeypatch):
    """If instructions.md disappears, the prompt loader falls back gracefully."""
    from ai import chat as chat_module
    from pathlib import Path as RealPath

    fake_path = RealPath("C:/__definitely_does_not_exist__/instructions.md")
    monkeypatch.setattr(chat_module, "_INSTRUCTIONS_PATH", fake_path)
    monkeypatch.setattr(chat_module, "_BUILTIN_FALLBACK_PROMPT", "FALLBACK_OK")
    chat_module._load_instructions_text.cache_clear()
    try:
        text = chat_module._load_instructions_text()
    finally:
        chat_module._load_instructions_text.cache_clear()
    assert text == "FALLBACK_OK"
