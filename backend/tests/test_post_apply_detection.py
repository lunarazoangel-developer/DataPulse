"""Verify _post_apply_scan finds remaining anomalies after a partial fix."""
import polars as pl
import pytest

from api.routes.ai import _post_apply_scan
from ai.actions import coerce_proposal


def _email_df():
    rows = []
    for i in range(20):
        rows.append({"email": f"user{i}@example,com"})
    for i in range(80):
        rows.append({"email": f"user{i + 100}@example.com"})
    return pl.DataFrame(rows)


def test_post_apply_scan_returns_zero_when_pattern_is_broad():
    """A broad replace_regex that fixes ALL bad rows should leave 0 remaining."""
    df = _email_df()
    new_df, changed = _apply_broad(df)
    assert changed == 20
    remaining = _post_apply_scan(
        {"users.csv": new_df},
        [_norm_replace_regex(r"@example,com", "@example.com")],
    )
    assert remaining == []


def test_post_apply_scan_returns_remaining_when_pattern_is_narrow():
    """A narrow regex that fixes one literal but leaves the rest triggers remaining."""
    df = _email_df()
    new_df, changed = _apply_narrow(df)
    assert changed == 1
    remaining = _post_apply_scan(
        {"users.csv": new_df},
        [_norm_replace_regex(r"user0@example,com", "user0@example.com")],
    )
    assert len(remaining) >= 1
    entry = remaining[0]
    assert entry["table"] == "users.csv"
    assert entry["column"] == "email"
    assert entry["violation_count"] > 0


def test_post_apply_scan_ignores_clean_tables():
    """A table the proposals didn't touch should not be re-scanned."""
    df = _email_df()
    cleaned_df, _ = _apply_broad(df)
    remaining = _post_apply_scan(
        {"users.csv": cleaned_df, "products.csv": df},
        [_norm_replace_regex(r"@example,com", "@example.com", table="users.csv")],
    )
    assert all(r["table"] != "products.csv" for r in remaining)


def test_post_apply_scan_empty_inputs():
    """Empty dirty_tables or empty proposals must not crash."""
    assert _post_apply_scan({}, []) == []
    assert _post_apply_scan({"t": pl.DataFrame({"a": [1]})}, []) == []
    assert _post_apply_scan({}, [{"action": "replace_regex", "table": "t", "column": "a"}]) == []


def _apply_broad(df):
    from core.data_transformer import apply_proposal
    return apply_proposal(df, coerce_proposal({
        "id": "p1",
        "action": "replace_regex",
        "table": "users.csv",
        "column": "email",
        "params": {"pattern": r"@example,com", "replacement": "@example.com"},
    }))


def _apply_narrow(df):
    from core.data_transformer import apply_proposal
    return apply_proposal(df, coerce_proposal({
        "id": "p1",
        "action": "replace_regex",
        "table": "users.csv",
        "column": "email",
        "params": {"pattern": r"^user0@example,com$", "replacement": "user0@example.com"},
    }))


def _norm_replace_regex(pattern, replacement, table="users.csv"):
    return coerce_proposal({
        "id": "p1",
        "action": "replace_regex",
        "table": table,
        "column": "email",
        "params": {"pattern": pattern, "replacement": replacement},
    })
