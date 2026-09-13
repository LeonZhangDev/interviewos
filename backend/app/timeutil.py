from datetime import datetime, timezone


def utc_now() -> datetime:
    """Naive UTC timestamp, equivalent to the deprecated datetime.utcnow().
    Stays naive on purpose: every DateTime column in models.py stores naive
    timestamps, so tz-aware values would break comparisons against values
    read back from the database."""
    return datetime.now(timezone.utc).replace(tzinfo=None)
