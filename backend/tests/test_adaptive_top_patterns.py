"""Verify the IA payload adaptively bumps top_patterns when the column has high cardinality."""
import polars as pl
import pytest

from core.ai_enricher import AIPayloadBuilder


def _low_diversity_df():
    """All 50 malformed rows share the same value; valid rows reuse 9 user ids -> 10 unique total."""
    valid_pool = [f"user{i}@example.com" for i in range(9)]
    rows = []
    for i in range(200):
        if i < 50:
            rows.append({"email": "broken@x,com"})
        else:
            rows.append({"email": valid_pool[(i - 50) % len(valid_pool)]})
    return pl.DataFrame(rows)


def _high_diversity_df():
    """50 malformed rows, each with a unique value -> high unique count."""
    rows = [{"email": f"user{i}@example{i % 5},com" if i < 50 else f"user{i}@example.com"} for i in range(500)]
    return pl.DataFrame(rows)


def _anomaly_payload(df, table="t.csv", column="email", violation_count=50):
    return {
        "metadata": {},
        "schemas": {table: {"columns": [column]}},
        "anomalies": {
            "red": [
                {
                    "table": table,
                    "column": column,
                    "data": [{"value": "user0@example,com"}],
                    "violation_count": violation_count,
                }
            ],
            "yellow": [],
            "green": [],
        },
        "column_profiles": {table: {column: {"column": column}}},
        "relationships": [],
    }


def test_low_diversity_keeps_default_3_patterns():
    """When the column has <=30 unique values, top_patterns stays at 3."""
    df = _low_diversity_df()
    builder = AIPayloadBuilder()
    payload = builder.build_ia_payload(
        data_dict={"t.csv": df},
        traffic_light_report={
            "red": [{
                "table": "t.csv",
                "column": "email",
                "data": [{"value": "user0@example,com"}],
                "violation_count": 50,
            }],
            "yellow": [],
            "green": [],
        },
        sensitive_columns={},
        relationships=[],
        max_top_patterns=3,
    )
    item = payload["anomalies"]["red"][0]
    assert "top_patterns" in item
    assert len(item["top_patterns"]) <= 3
    assert "top_patterns_adaptive" not in item


def test_high_diversity_bumps_top_patterns_above_default():
    """When the column has >30 unique values, top_patterns is adaptively bumped."""
    df = _high_diversity_df()
    builder = AIPayloadBuilder()
    payload = builder.build_ia_payload(
        data_dict={"t.csv": df},
        traffic_light_report={
            "red": [{
                "table": "t.csv",
                "column": "email",
                "data": [{"value": "user0@example0,com"}],
                "violation_count": 50,
            }],
            "yellow": [],
            "green": [],
        },
        sensitive_columns={},
        relationships=[],
        max_top_patterns=3,
        adaptive_patterns_threshold=30,
        adaptive_patterns_hard_cap=10,
    )
    item = payload["anomalies"]["red"][0]
    assert "top_patterns" in item
    assert len(item["top_patterns"]) > 3
    assert item.get("top_patterns_adaptive") is not None
    assert item["top_patterns_adaptive"] <= 10
    assert item["top_patterns_adaptive"] >= 3


def test_adaptive_hard_cap_is_respected():
    """No matter how diverse, top_patterns must never exceed the hard cap."""
    rows = [{"v": f"unique-{i}"} for i in range(5000)]
    df = pl.DataFrame(rows)
    builder = AIPayloadBuilder()
    payload = builder.build_ia_payload(
        data_dict={"t.csv": df},
        traffic_light_report={
            "red": [{
                "table": "t.csv",
                "column": "v",
                "data": [{"value": "unique-0"}],
                "violation_count": 100,
            }],
            "yellow": [],
            "green": [],
        },
        sensitive_columns={},
        relationships=[],
        max_top_patterns=3,
        adaptive_patterns_threshold=30,
        adaptive_patterns_hard_cap=10,
    )
    item = payload["anomalies"]["red"][0]
    assert len(item["top_patterns"]) <= 10


def test_zero_top_patterns_keeps_list_empty():
    """If max_top_patterns=0, no top_patterns are computed (and no adaptive bump)."""
    df = _high_diversity_df()
    builder = AIPayloadBuilder()
    payload = builder.build_ia_payload(
        data_dict={"t.csv": df},
        traffic_light_report={
            "red": [{
                "table": "t.csv",
                "column": "email",
                "data": [{"value": "user0@example0,com"}],
                "violation_count": 50,
            }],
            "yellow": [],
            "green": [],
        },
        sensitive_columns={},
        relationships=[],
        max_top_patterns=0,
    )
    item = payload["anomalies"]["red"][0]
    assert "top_patterns" not in item
    assert "top_patterns_adaptive" not in item


def test_adaptive_does_not_trigger_below_threshold():
    """A column with 25 unique values (<=30 threshold) keeps the default cap."""
    rows = [{"v": f"v-{i}"} for i in range(25)]
    df = pl.DataFrame(rows)
    builder = AIPayloadBuilder()
    payload = builder.build_ia_payload(
        data_dict={"t.csv": df},
        traffic_light_report={
            "red": [{
                "table": "t.csv",
                "column": "v",
                "data": [{"value": "v-0"}],
                "violation_count": 10,
            }],
            "yellow": [],
            "green": [],
        },
        sensitive_columns={},
        relationships=[],
        max_top_patterns=3,
    )
    item = payload["anomalies"]["red"][0]
    assert "top_patterns_adaptive" not in item
    assert len(item["top_patterns"]) <= 3
