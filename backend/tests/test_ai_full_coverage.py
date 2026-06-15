"""Verify the IA payload gives the model full-table context, not just 5 samples."""
import random

import polars as pl
import pytest


def _build_email_df(n_rows: int, malformed_fraction: float, seed: int = 0):
    rng = random.Random(seed)
    rows = []
    for i in range(n_rows):
        if rng.random() < malformed_fraction:
            rows.append({
                "id": i,
                "email": rng.choice([
                    f"user{i}@example,com",
                    f"user{i}@example .com",
                    f"user{i}@example,com ",
                ]),
            })
        else:
            rows.append({"id": i, "email": f"user{i}@example.com"})
    return pl.DataFrame(rows)


def test_build_ia_payload_reports_violation_count_and_top_patterns():
    from core.ai_enricher import AIPayloadBuilder

    df = _build_email_df(1000, malformed_fraction=0.05)
    data = {"users.csv": df}
    traffic_light = {
        "red": [
            {
                "table": "users.csv",
                "column": "email",
                "detection_type": "format_violation",
                "data": [{"value": "user0@example,com"}],
                "violation_count": 50,
            }
        ],
        "yellow": [],
        "green": [],
    }
    builder = AIPayloadBuilder()
    payload = builder.build_ia_payload(
        data_dict=data,
        traffic_light_report=traffic_light,
        sensitive_columns={},
        relationships=[],
        max_samples_per_anomaly=2,
        max_top_patterns=5,
    )

    assert payload["metadata"]["payload_mode"] == "ia"
    red_items = payload["anomalies"]["red"]
    assert len(red_items) == 1
    item = red_items[0]
    assert item["violation_count"] == 50
    assert item["affected_ratio"] == pytest.approx(0.05, rel=1e-3)
    assert "top_patterns" in item
    assert len(item["top_patterns"]) > 0
    assert item["sample_count"] == 1
    assert "of ~50 affected rows shown" in item["sample_vs_total_note"]


def test_build_ia_payload_caps_samples_and_keeps_redaction():
    from core.ai_enricher import AIPayloadBuilder

    df = _build_email_df(200, malformed_fraction=0.1)
    data = {"users.csv": df}
    traffic_light = {
        "red": [
            {
                "table": "users.csv",
                "column": "email",
                "data": [{"value": f"u{i}@x,com"} for i in range(10)],
            }
        ],
        "yellow": [],
        "green": [],
    }
    builder = AIPayloadBuilder()
    payload = builder.build_ia_payload(
        data_dict=data,
        traffic_light_report=traffic_light,
        sensitive_columns={"users.csv": ["email"]},
        relationships=[],
        max_samples_per_anomaly=2,
        max_top_patterns=3,
    )
    assert "email" not in payload["schemas"]["users.csv"]["columns"]
    assert "email" in payload["schemas"]["users.csv"]["redacted_columns"]
    item = payload["anomalies"]["red"][0]
    assert len(item["data"]) <= 2


def test_build_ia_payload_stratified_sampling_above_threshold():
    from core.ai_enricher import AIPayloadBuilder

    big = _build_email_df(150_000, malformed_fraction=0.02)
    data = {"huge.csv": big}
    traffic_light = {"red": [], "yellow": [], "green": []}
    builder = AIPayloadBuilder()
    payload = builder.build_ia_payload(
        data_dict=data,
        traffic_light_report=traffic_light,
        sensitive_columns={},
        relationships=[],
        stratified_threshold=100_000,
        stratified_fraction=0.001,
    )
    sampled = payload["schemas"]["huge.csv"]["sampled_rows"]
    total = payload["schemas"]["huge.csv"]["total_rows"]
    assert total == 150_000
    assert sampled == 150


def test_preflight_replace_regex_estimates_full_table_scope():
    from core.data_transformer import preflight_affected_rows

    df = _build_email_df(1000, malformed_fraction=0.05)
    proposal = {
        "id": "p1",
        "action": "replace_regex",
        "table": "users.csv",
        "column": "email",
        "params": {"pattern": r",\s*", "replacement": "."},
    }
    n = preflight_affected_rows(df, proposal)
    assert n is not None
    assert n == pytest.approx(50, rel=0.3)


def test_preflight_drop_rows_in_operator():
    from core.data_transformer import preflight_affected_rows

    df = pl.DataFrame({
        "status": ["ok", "N/A", "ok", "--", "s/d", "ok", None, "ok"],
    })
    proposal = {
        "id": "p1",
        "action": "drop_rows",
        "table": "t",
        "column": "status",
        "params": {"operator": "in", "value": ["N/A", "--", "s/d"]},
    }
    assert preflight_affected_rows(df, proposal) == 3


def test_apply_replace_regex_reaches_full_table():
    from core.data_transformer import apply_proposal

    df = _build_email_df(1000, malformed_fraction=0.05)
    proposal = {
        "id": "p1",
        "action": "replace_regex",
        "table": "users.csv",
        "column": "email",
        "params": {"pattern": r"@example,com\s*", "replacement": "@example.com "},
    }
    new_df, changed = apply_proposal(df, proposal)
    assert changed > 30
    bad_after = new_df.filter(new_df["email"].str.contains(r",")).height
    assert bad_after < 10
