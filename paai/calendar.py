"""
Google Calendar via the Google API client, behind the CalendarProvider interface.

providers.get_calendar_provider() returns this for users with a "google"
connection. Like GmailProvider, it never refreshes tokens itself: the
connection dict it receives already holds a fresh access token.

Scope note: oauth.MAILBOX_SCOPES requests calendar.events. Connections made
before that change only hold calendar.readonly, and create_event reports that
the user needs to reconnect.
"""
from datetime import date, datetime, time, timezone

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from paai.providers import CalendarEvent, CalendarProvider


def _iso(dt: datetime) -> str:
    """RFC3339 in UTC. Naive datetimes are assumed to already be UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _parse_when(when: dict) -> datetime:
    """
    Google returns {"dateTime": "..."} for timed events and {"date": "YYYY-MM-DD"}
    for all-day events. All-day events become midnight UTC on that date.
    """
    if when.get("dateTime"):
        dt = datetime.fromisoformat(when["dateTime"].replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    if when.get("date"):
        return datetime.combine(date.fromisoformat(when["date"]), time.min, timezone.utc)
    return datetime.now(timezone.utc)


class GoogleCalendarProvider(CalendarProvider):
    name = "google"

    def __init__(self, connection: dict):
        creds = Credentials(token=connection["access_token"])
        self._svc = build("calendar", "v3", credentials=creds, cache_discovery=False)

    def list_events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        events: list[CalendarEvent] = []
        page_token = None
        try:
            while True:
                resp = (
                    self._svc.events()
                    .list(
                        calendarId="primary",
                        timeMin=_iso(start),
                        timeMax=_iso(end),
                        singleEvents=True,      # expand recurring events
                        orderBy="startTime",
                        maxResults=100,
                        pageToken=page_token,
                    )
                    .execute()
                )
                for e in resp.get("items", []):
                    if e.get("status") == "cancelled":
                        continue
                    events.append(
                        CalendarEvent(
                            id=e["id"],
                            title=e.get("summary") or "(no title)",
                            start=_parse_when(e.get("start", {})),
                            end=_parse_when(e.get("end", {})),
                            location=e.get("location"),
                            attendees=[
                                a.get("email", "") for a in e.get("attendees", []) or []
                            ],
                            link=e.get("htmlLink"),
                        )
                    )
                page_token = resp.get("nextPageToken")
                if not page_token:
                    break
        except HttpError as exc:
            raise RuntimeError(f"Google Calendar list failed: {exc}") from exc
        return events

    def create_event(
        self,
        title: str,
        start: datetime,
        end: datetime,
        attendees: list[str] | None = None,
        location: str | None = None,
    ) -> str:
        body = {
            "summary": title,
            "start": {"dateTime": _iso(start), "timeZone": "UTC"},
            "end": {"dateTime": _iso(end), "timeZone": "UTC"},
        }
        if location:
            body["location"] = location
        if attendees:
            body["attendees"] = [{"email": a} for a in attendees]
        try:
            created = (
                self._svc.events().insert(calendarId="primary", body=body).execute()
            )
        except HttpError as exc:
            if exc.resp is not None and exc.resp.status == 403:
                raise RuntimeError(
                    "Google refused to create the event: this calendar was "
                    "connected with read-only access. Reconnect Google in "
                    "Settings to allow adding events."
                ) from exc
            raise RuntimeError(f"Google Calendar create failed: {exc}") from exc
        return created["id"]