"""
Google Calendar provider: registry resolution and event parsing.

Regression test for providers.get_calendar_provider() importing a
GoogleCalendarProvider class that did not exist, which made every calendar
request from a Gmail user fail.
"""
from datetime import datetime, timedelta, timezone

from paai.calendar import GoogleCalendarProvider
from paai.db import get_or_create_user, upsert_oauth_connection
from paai.providers import get_calendar_provider


class _FakeEvents:
    def __init__(self, items):
        self._items = items

    def list(self, **kwargs):
        self.kwargs = kwargs
        return self

    def execute(self):
        return {"items": self._items}


class _FakeService:
    def __init__(self, items):
        self._events = _FakeEvents(items)

    def events(self):
        return self._events


def test_google_connection_resolves_calendar_provider():
    user = get_or_create_user("gcal-registry@test.local")
    upsert_oauth_connection(
        user_id=user,
        provider="google",
        access_token="fake-access",
        refresh_token="fake-refresh",
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    assert isinstance(get_calendar_provider(user), GoogleCalendarProvider)


def test_list_events_parses_timed_and_all_day_events():
    provider = GoogleCalendarProvider({"access_token": "fake"})
    provider._svc = _FakeService([
        {
            "id": "a",
            "summary": "Standup",
            "start": {"dateTime": "2026-10-05T09:00:00-04:00"},
            "end": {"dateTime": "2026-10-05T09:15:00-04:00"},
            "attendees": [{"email": "x@example.com"}],
            "htmlLink": "https://calendar.google.com/a",
        },
        {
            "id": "b",
            "start": {"date": "2026-10-06"},
            "end": {"date": "2026-10-07"},
        },
        {"id": "c", "status": "cancelled", "start": {}, "end": {}},
    ])

    start = datetime(2026, 10, 5, tzinfo=timezone.utc)
    events = provider.list_events(start, start + timedelta(days=7))

    assert [e.id for e in events] == ["a", "b"]
    assert events[0].start == datetime(2026, 10, 5, 13, 0, tzinfo=timezone.utc)
    assert events[0].attendees == ["x@example.com"]
    assert events[1].title == "(no title)"
    assert events[1].start == datetime(2026, 10, 6, tzinfo=timezone.utc)