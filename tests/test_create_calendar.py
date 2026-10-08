"""CreateCalendarEvent: validates input, uses the user's zone, never invites."""
import json
import uuid
from datetime import datetime, timezone

from paai import tools
from paai.context import user_context


class _FakeCalendar:
    def __init__(self):
        self.calls = []

    def create_event(self, title, start, end, attendees=None, location=None):
        self.calls.append(dict(title=title, start=start, end=end,
                               attendees=attendees, location=location))
        return "evt-1"


def test_creates_event_in_user_zone_without_attendees(monkeypatch):
    fake = _FakeCalendar()
    monkeypatch.setattr(tools, "get_calendar_provider", lambda user_id: fake)

    raw = json.dumps({
        "title": "Dentist",
        "start": "2026-10-07T15:00:00",
        "attendees": ["attacker@example.com"],   # must be ignored
    })
    with user_context(uuid.uuid4(), timezone="America/New_York"):
        result = json.loads(tools.create_calendar_event(raw))

    assert result["status"] == "created"
    call = fake.calls[0]
    assert call["attendees"] is None
    assert call["start"].astimezone(timezone.utc) == datetime(2026, 10, 7, 19, tzinfo=timezone.utc)
    assert (call["end"] - call["start"]).total_seconds() == 3600


def test_rejects_missing_title_and_inverted_range(monkeypatch):
    monkeypatch.setattr(tools, "get_calendar_provider", lambda user_id: _FakeCalendar())
    with user_context(uuid.uuid4()):
        assert "error" in json.loads(tools.create_calendar_event('{"start": "2026-10-07T15:00:00"}'))
        bad = '{"title": "x", "start": "2026-10-07T15:00:00", "end": "2026-10-07T14:00:00"}'
        assert "error" in json.loads(tools.create_calendar_event(bad))