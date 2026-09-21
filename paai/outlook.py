"""
Outlook mail and calendar via Microsoft Graph.

Implements the same EmailProvider / CalendarProvider interfaces as gmail.py, so
the agents never learn which provider a user connected — get_email_provider()
returns whichever one has a row in oauth_connections.

Why this matters beyond "a second provider": Microsoft's Mail.Read and
Calendars.Read are ordinary delegated permissions. There is no equivalent of
Google's CASA assessment, no annual third-party audit and no fee. Gmail scopes
are restricted, so until PAAI clears Google verification, Gmail only works for
listed test users. Outlook works for anyone today.

Graph reference: https://learn.microsoft.com/graph/api/resources/mail-api-overview
"""
import uuid
from datetime import datetime, timezone

import httpx

from paai.providers import (
    CalendarEvent,
    CalendarProvider,
    EmailMessage,
    EmailProvider,
)

GRAPH = "https://graph.microsoft.com/v1.0"


def _iso(dt: datetime) -> str:
    """Graph wants UTC ISO8601. Naive datetimes are assumed UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    # Graph returns e.g. 2026-09-21T14:30:00Z, sometimes with fractional seconds
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _address(entry: dict | None) -> str:
    if not entry:
        return ""
    addr = entry.get("emailAddress", {})
    name, email = addr.get("name"), addr.get("address", "")
    return f"{name} <{email}>" if name and name != email else email


class OutlookProvider(EmailProvider):
    name = "outlook"

    def __init__(self, connection: dict):
        # connection comes from db.get_oauth_connection — tokens already decrypted
        self._user_id = connection.get("user_id")
        self._token = connection["access_token"]

    # ── internals ─────────────────────────────────────────────────────────
    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: dict | None = None) -> dict:
        with httpx.Client(timeout=30) as client:
            resp = client.get(f"{GRAPH}{path}", headers=self._headers(), params=params)
        if resp.status_code == 401:
            # The caller should have refreshed via get_valid_access_token; if we
            # still get 401 the grant was revoked on Microsoft's side.
            raise RuntimeError("Outlook access expired — the user must reconnect.")
        if resp.status_code >= 400:
            raise RuntimeError(f"Graph {path} failed ({resp.status_code}): {resp.text[:300]}")
        return resp.json()

    def _post(self, path: str, body: dict) -> dict:
        with httpx.Client(timeout=30) as client:
            resp = client.post(f"{GRAPH}{path}", headers=self._headers(), json=body)
        if resp.status_code >= 400:
            raise RuntimeError(f"Graph {path} failed ({resp.status_code}): {resp.text[:300]}")
        return resp.json() if resp.content else {}

    def _to_message(self, m: dict, body: str | None = None) -> EmailMessage:
        return EmailMessage(
            id=m["id"],
            thread_id=m.get("conversationId"),
            subject=m.get("subject") or "(no subject)",
            sender=_address(m.get("from") or m.get("sender")),
            recipients=[_address(r) for r in (m.get("toRecipients") or [])],
            date=_parse(m.get("receivedDateTime")),
            snippet=(m.get("bodyPreview") or "")[:400],
            body=body if body is not None else (m.get("body", {}) or {}).get("content", ""),
            is_unread=not m.get("isRead", True),
            labels=[m["parentFolderId"]] if m.get("parentFolderId") else [],
            # Email bodies are attacker-controlled text. The guardrail layer
            # reads this flag to decide what may write persistent state.
            is_untrusted=True,
        )

    # ── EmailProvider ─────────────────────────────────────────────────────
    def list_messages(
        self,
        max_results: int = 10,
        after: datetime | None = None,
        before: datetime | None = None,
        query: str | None = None,
    ) -> list[EmailMessage]:
        params = {
            "$top": min(max_results, 100),
            "$orderby": "receivedDateTime desc",
            "$select": "id,conversationId,subject,from,toRecipients,"
                       "receivedDateTime,bodyPreview,isRead,parentFolderId",
        }

        filters = []
        if after:
            filters.append(f"receivedDateTime ge {_iso(after)}")
        if before:
            filters.append(f"receivedDateTime lt {_iso(before)}")
        if filters:
            params["$filter"] = " and ".join(filters)

        if query:
            # $search and $filter cannot be combined in Graph. Search wins, and
            # date filtering then happens client-side below.
            params.pop("$filter", None)
            params.pop("$orderby", None)   # $search forbids $orderby too
            params["$search"] = f'"{query}"'

        data = self._get("/me/messages", params)
        messages = [self._to_message(m) for m in data.get("value", [])]

        if query and (after or before):
            messages = [
                m for m in messages
                if (not after or m.date >= after) and (not before or m.date < before)
            ]

        return messages

    def get_message(self, message_id: str) -> EmailMessage:
        m = self._get(f"/me/messages/{message_id}")
        return self._to_message(m)

    def create_draft(
        self, to: list[str], subject: str, body: str, reply_to_id: str | None = None
    ) -> str:
        payload = {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": a}} for a in to],
        }

        if reply_to_id:
            # createReply builds a draft already threaded to the original
            draft = self._post(f"/me/messages/{reply_to_id}/createReply", {})
            draft_id = draft["id"]
            with httpx.Client(timeout=30) as client:
                resp = client.patch(
                    f"{GRAPH}/me/messages/{draft_id}",
                    headers=self._headers(),
                    json={"body": {"contentType": "Text", "content": body}},
                )
            if resp.status_code >= 400:
                raise RuntimeError(f"Could not update reply draft: {resp.text[:300]}")
            return draft_id

        return self._post("/me/messages", payload)["id"]

    def send_message(
        self, to: list[str], subject: str, body: str, reply_to_id: str | None = None
    ) -> str:
        """
        Irreversible and outbound.

        Per the guardrail plan this must never be reachable without explicit
        human confirmation — a model that has read an attacker's email must not
        be able to send on the user's behalf on its own say-so. The approval
        gate belongs in the agent layer, above this call.
        """
        draft_id = self.create_draft(to, subject, body, reply_to_id)
        self._post(f"/me/messages/{draft_id}/send", {})
        return draft_id


class OutlookCalendarProvider(CalendarProvider):
    name = "outlook"

    def __init__(self, connection: dict):
        self._token = connection["access_token"]

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._token}",
            "Content-Type": "application/json",
            # Ask Graph to return times in UTC rather than the mailbox timezone,
            # so the agent never has to guess which zone it is reading.
            "Prefer": 'outlook.timezone="UTC"',
        }

    def list_events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        params = {
            "startDateTime": _iso(start),
            "endDateTime": _iso(end),
            "$orderby": "start/dateTime",
            "$top": 100,
            "$select": "id,subject,start,end,location,attendees,webLink",
        }
        with httpx.Client(timeout=30) as client:
            resp = client.get(
                f"{GRAPH}/me/calendarView", headers=self._headers(), params=params
            )
        if resp.status_code >= 400:
            raise RuntimeError(f"Graph calendarView failed: {resp.text[:300]}")

        events = []
        for e in resp.json().get("value", []):
            events.append(
                CalendarEvent(
                    id=e["id"],
                    title=e.get("subject") or "(no title)",
                    start=_parse(e["start"]["dateTime"] + "Z"
                                 if not e["start"]["dateTime"].endswith("Z")
                                 else e["start"]["dateTime"]),
                    end=_parse(e["end"]["dateTime"] + "Z"
                               if not e["end"]["dateTime"].endswith("Z")
                               else e["end"]["dateTime"]),
                    location=(e.get("location") or {}).get("displayName"),
                    attendees=[
                        a.get("emailAddress", {}).get("address", "")
                        for a in (e.get("attendees") or [])
                    ],
                    link=e.get("webLink"),
                )
            )
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
            "subject": title,
            "start": {"dateTime": _iso(start), "timeZone": "UTC"},
            "end": {"dateTime": _iso(end), "timeZone": "UTC"},
        }
        if location:
            body["location"] = {"displayName": location}
        if attendees:
            body["attendees"] = [
                {"emailAddress": {"address": a}, "type": "required"} for a in attendees
            ]

        with httpx.Client(timeout=30) as client:
            resp = client.post(
                f"{GRAPH}/me/events", headers=self._headers(), json=body
            )
        if resp.status_code >= 400:
            raise RuntimeError(f"Graph create event failed: {resp.text[:300]}")
        return resp.json()["id"]
