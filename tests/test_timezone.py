"""
Relative dates must resolve in the user's timezone, not the server's (UTC).
"""
import uuid
from datetime import datetime, timezone

from paai.context import get_user_timezone, user_context
from paai.generic_tools import get_time
from paai.tools import _parse_dt


def test_get_time_reports_user_zone():
    with user_context(uuid.uuid4(), timezone="America/New_York"):
        assert "America/New_York" in get_time("")


def test_invalid_or_missing_zone_falls_back_to_utc():
    with user_context(uuid.uuid4(), timezone="Not/AZone"):
        assert get_user_timezone().key == "UTC"
    with user_context(uuid.uuid4()):
        assert get_user_timezone().key == "UTC"


def test_bare_dates_are_read_in_user_zone():
    with user_context(uuid.uuid4(), timezone="America/New_York"):
        start = _parse_dt("2026-10-03")
    # Midnight in New York is 04:00 UTC during daylight time.
    assert start.astimezone(timezone.utc) == datetime(2026, 10, 3, 4, tzinfo=timezone.utc)


def test_explicit_offsets_are_respected():
    with user_context(uuid.uuid4(), timezone="America/New_York"):
        dt = _parse_dt("2026-10-03T12:00:00Z")
    assert dt == datetime(2026, 10, 3, 12, tzinfo=timezone.utc)


def test_zone_does_not_leak_between_contexts():
    with user_context(uuid.uuid4(), timezone="Asia/Kolkata"):
        pass
    with user_context(uuid.uuid4()):
        assert get_user_timezone().key == "UTC"