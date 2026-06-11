import re
from datetime import date, datetime, timedelta
from typing import Callable, Dict, List, Optional, Union

DateLike = Union[date, datetime, str, None]

FORMAT_PATTERNS: Dict[str, re.Pattern] = {
    "email": re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$"),
    "url": re.compile(r"^https?://[^\s]+$", re.IGNORECASE),
    "uuid": re.compile(
        r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
    ),
    "ipv4": re.compile(r"^(?:\d{1,3}\.){3}\d{1,3}$"),
    "phone_intl": re.compile(r"^\+?[1-9]\d{6,14}$"),
    "phone_us": re.compile(r"^\+?1?[\s.-]?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}$"),
    "iso_date": re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    "us_date": re.compile(r"^\d{1,2}/\d{1,2}/\d{2,4}$"),
    "eu_date": re.compile(r"^\d{1,2}-\d{1,2}-\d{2,4}$"),
    "datetime_iso": re.compile(r"^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}"),
}

DATE_FORMATS: List[str] = [
    "%Y-%m-%d",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%m-%d-%Y",
    "%d.%m.%Y",
    "%Y%m%d",
    "%b %d, %Y",
    "%d %b %Y",
]

COLUMN_NAME_HINTS: Dict[str, str] = {
    "email": "email",
    "url": "url",
    "uuid": "uuid",
    "phone": "phone",
    "ip": "ip",
    "date": "date",
    "datetime": "date",
    "timestamp": "date",
    "fecha": "date",
    "nacimiento": "date",
    "dob": "date",
    "birth": "date",
    "created": "date",
    "updated": "date",
    "age": "non_negative",
    "edad": "non_negative",
    "precio": "non_negative",
    "price": "non_negative",
    "cost": "non_negative",
    "amount": "non_negative",
    "total": "non_negative",
    "quantity": "non_negative",
    "qty": "non_negative",
    "stock": "non_negative",
    "count": "non_negative",
    "percentage": "percentage",
    "porcentaje": "percentage",
    "pct": "percentage",
    "ratio": "ratio",
    "rate": "ratio",
}

DOMAIN_RULES: Dict[str, Callable[[object], Optional[str]]] = {
    "non_negative": lambda v: ("negative" if isinstance(v, (int, float)) and v < 0 else None),
    "percentage": lambda v: (
        "out_of_range"
        if isinstance(v, (int, float)) and (v < 0 or v > 100)
        else None
    ),
    "ratio": lambda v: (
        "out_of_range"
        if isinstance(v, (int, float)) and (v < 0 or v > 1)
        else None
    ),
    "non_negative_int": lambda v: (
        "negative"
        if isinstance(v, int) and not isinstance(v, bool) and v < 0
        else None
    ),
}

PLACEHOLDER_NULL_TOKENS = {
    "",
    "na",
    "n/a",
    "null",
    "none",
    "nan",
    "-",
    "--",
    "?",
    "unknown",
    "sin valor",
    "s/n",
    "s/d",
}

MAX_SAMPLES_PER_ANOMALY: int = 5


def infer_format_pattern(column_name: str, sample_values: List[str]) -> Optional[str]:
    if not column_name or not sample_values:
        return None

    col_lower = column_name.lower().strip()

    for hint_key, pattern_name in COLUMN_NAME_HINTS.items():
        if hint_key in col_lower and pattern_name in FORMAT_PATTERNS:
            return pattern_name

    non_empty = [v.strip() for v in sample_values if v and str(v).strip()]
    if not non_empty:
        return None

    sample = non_empty[: min(200, len(non_empty))]

    format_scores: Dict[str, float] = {}
    for fmt_name, pattern in FORMAT_PATTERNS.items():
        matches = sum(1 for v in sample if pattern.match(v))
        if matches > 0:
            format_scores[fmt_name] = matches / len(sample)

    if not format_scores:
        return None

    best = max(format_scores.items(), key=lambda x: x[1])
    if best[1] >= 0.8:
        return best[0]
    return None


def is_placeholder_null(value: object) -> bool:
    if value is None:
        return True
    if not isinstance(value, str):
        return False
    return value.strip().lower() in PLACEHOLDER_NULL_TOKENS


def parse_date_safely(value: str) -> Optional[date]:
    if not value or not isinstance(value, str):
        return None
    s = value.strip()
    if not s:
        return None
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _to_date(value: DateLike) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def is_future_date(value: DateLike, threshold_days: int = 0) -> bool:
    d = _to_date(value)
    if d is None:
        return False
    today = date.today()
    return d > today + timedelta(days=threshold_days)


def is_ancient_date(value: DateLike, min_year: int = 1900) -> bool:
    d = _to_date(value)
    if d is None:
        return False
    return d.year < min_year


def infer_domain_rule(column_name: str) -> Optional[str]:
    if not column_name:
        return None
    col_lower = column_name.lower().strip()
    for hint_key, rule in COLUMN_NAME_HINTS.items():
        if hint_key in col_lower and rule in DOMAIN_RULES:
            return rule
    return None


def detect_inconsistent_date_formats(values: List[str]) -> Dict[str, int]:
    format_counts: Dict[str, int] = {}
    for v in values:
        if not v or not isinstance(v, str):
            continue
        s = v.strip()
        matched = False
        for fmt_name, pattern in FORMAT_PATTERNS.items():
            if "date" in fmt_name and pattern.match(s):
                format_counts[fmt_name] = format_counts.get(fmt_name, 0) + 1
                matched = True
                break
        if not matched:
            format_counts["unrecognized"] = format_counts.get("unrecognized", 0) + 1

    recognized = {k: v for k, v in format_counts.items() if k != "unrecognized"}
    return recognized if len(recognized) > 1 else {}
