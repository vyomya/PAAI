"""
Tools exposed to the LLM.

Two rules hold everywhere in this file.

1. user_id NEVER comes from tool arguments. It is read from the request
   context. Email bodies are attacker-controlled text, so a user_id the model
   can see is a user_id a prompt injection can change — and that turns one
   poisoned email into a cross-user read.

2. Tools never import gmail or outlook directly. They ask the provider
   registry, which returns whichever mailbox the user connected. Adding a
   provider changes nothing here.
"""
import json
from datetime import datetime, timedelta, timezone

from langchain_core.tools import Tool

from paai import db
from paai.context import get_current_user
from paai.generic_tools import get_time
from paai.providers import get_calendar_provider, get_email_provider


def _parse_dt(value: str | None) -> datetime | None:
    """Accepts ISO8601 with or without Z, or a bare YYYY-MM-DD."""
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            return None


def _args(raw: str) -> dict:
    if not raw or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, dict) else {}
    except json.JSONDecodeError:
        return {}


def _fail(msg: str) -> str:
    return json.dumps({"error": msg})


# ── Email ─────────────────────────────────────────────────────────────────────
def fetch_emails(raw: str) -> str:
    """
    Returns full email content in one call.

    The previous version returned message ids only, so the agent had to make a
    second call per email to read anything — N+1 round trips and a lot of
    wasted tokens on ids the model never used.
    """
    args = _args(raw)
    try:
        provider = get_email_provider(get_current_user())
        messages = provider.list_messages(
            max_results=int(args.get("max_results", 10)),
            after=_parse_dt(args.get("after")),
            before=_parse_dt(args.get("before")),
            query=args.get("query"),
        )
    except Exception as exc:
        return _fail(str(exc))

    return json.dumps([
        {
            "id": m.id,
            "subject": m.subject,
            "from": m.sender,
            "date": m.date.isoformat(),
            "snippet": m.snippet,
            # Body is truncated here on purpose: ten full emails will blow the
            # context window, and the summariser only needs the gist. Use
            # GetEmailDetails when the full text actually matters.
            "body": m.body[:1500],
            "unread": m.is_unread,
        }
        for m in messages
    ], indent=2)


def get_email_details(raw: str) -> str:
    args = _args(raw)
    msg_id = args.get("msg_id") or args.get("id")
    if not msg_id:
        return _fail("msg_id is required")

    try:
        provider = get_email_provider(get_current_user())
        m = provider.get_message(msg_id)
    except Exception as exc:
        return _fail(str(exc))

    return json.dumps({
        "id": m.id,
        "subject": m.subject,
        "from": m.sender,
        "to": m.recipients,
        "date": m.date.isoformat(),
        "body": m.body,
        "snippet": m.snippet,
    }, indent=2)


def draft_email(raw: str) -> str:
    """
    Creates a draft. Deliberately does not send.

    Sending is irreversible and outbound, so it stays behind an explicit human
    confirmation rather than a model decision.
    """
    args = _args(raw)
    to = args.get("to")
    if isinstance(to, str):
        to = [a.strip() for a in to.split(",") if a.strip()]
    if not to:
        return _fail("to is required")

    try:
        provider = get_email_provider(get_current_user())
        draft_id = provider.create_draft(
            to=to,
            subject=args.get("subject", ""),
            body=args.get("body", ""),
            reply_to_id=args.get("reply_to_id"),
        )
    except Exception as exc:
        return _fail(str(exc))

    return json.dumps({
        "status": "draft_created",
        "draft_id": draft_id,
        "note": "Saved as a draft. The user must review and send it themselves.",
    })


# ── Calendar ──────────────────────────────────────────────────────────────────
def fetch_calendar_events(raw: str) -> str:
    args = _args(raw)
    start = _parse_dt(args.get("time_min")) or datetime.now(timezone.utc)
    end = _parse_dt(args.get("time_max")) or (start + timedelta(days=7))

    try:
        provider = get_calendar_provider(get_current_user())
        events = provider.list_events(start, end)
    except Exception as exc:
        return _fail(str(exc))

    return json.dumps([
        {
            "id": e.id,
            "title": e.title,
            "start": e.start.isoformat(),
            "end": e.end.isoformat(),
            "location": e.location,
            "attendees": e.attendees,
            "link": e.link,
        }
        for e in events
    ], indent=2)


# ── Conversation history ──────────────────────────────────────────────────────
def get_recent_messages(raw: str) -> str:
    """
    BUGFIX: the previous version called db.get_recent_messages(limit=limit)
    with no user_id, which raised TypeError every time the History Agent used
    it — the tool has never actually worked.
    """
    args = _args(raw)
    try:
        messages = db.get_recent_messages(
            get_current_user(), limit=int(args.get("limit", 10))
        )
    except Exception as exc:
        return _fail(str(exc))

    if not messages:
        return "No conversation history found."
    return json.dumps(messages, indent=2)


def search_messages(raw: str) -> str:
    """
    Semantic search over this user's past conversations.

    Uses the scored variant with a distance threshold. Plain top-k always
    returns k rows however unrelated they are, which is how the History Agent
    ends up "recalling" a conversation that never happened.
    """
    args = _args(raw)
    query = args.get("query", "")
    if not query:
        return _fail("query is required")

    try:
        hits = db.search_messages_scored(
            get_current_user(),
            query=query,
            limit=int(args.get("limit", 5)),
            max_distance=0.35,
        )
    except Exception as exc:
        return _fail(str(exc))

    if not hits:
        return "No relevant messages found."
    return json.dumps(hits, indent=2)


def web_search(query: str) -> str:
    return "Web search is not configured yet."


# ── Registry ──────────────────────────────────────────────────────────────────
tools = [
    Tool(
        name="GetTime",
        func=get_time,
        description=(
            "Gets the current date and time. Call this before any date-relative "
            "request ('today', 'next week') so you resolve dates correctly. "
            "Input: {}"
        ),
    ),
    Tool(
        name="FetchEmails",
        func=fetch_emails,
        description="""Fetches emails with full content in one call.
Input JSON, all fields optional:
{"max_results": 10, "after": "2026-09-01", "before": "2026-09-21", "query": "from:someone@example.com"}
- after / before: ISO date or datetime. Use GetTime first to resolve relative dates.
- query: provider search syntax, e.g. "from:x@y.com" or "subject:meeting".
Returns id, subject, from, date, snippet and body (truncated) per email.
Use GetEmailDetails only when you need the untruncated body of one email.""",
    ),
    Tool(
        name="GetEmailDetails",
        func=get_email_details,
        description="""Gets the full, untruncated content of one email.
Input JSON: {"msg_id": "..."}
Only needed when FetchEmails truncated something you must read in full.""",
    ),
    Tool(
        name="DraftEmail",
        func=draft_email,
        description="""Creates a draft email. Does NOT send it.
Input JSON: {"to": ["a@b.com"], "subject": "...", "body": "...", "reply_to_id": "optional message id"}
Sending is never automatic — the user reviews and sends the draft themselves.""",
    ),
    Tool(
        name="FetchCalendarEvents",
        func=fetch_calendar_events,
        description="""Fetches calendar events in a time range.
Input JSON: {"time_min": "2026-09-21T00:00:00Z", "time_max": "2026-09-28T00:00:00Z"}
Defaults to the next 7 days from now. Use GetTime first for relative ranges.
Returns title, start, end, location, attendees and link per event.""",
    ),
    Tool(
        name="SearchMessages",
        func=search_messages,
        description="""Semantically searches this user's past conversations.
Input JSON: {"query": "interview discussion", "limit": 5}
Use when the user references an earlier session ("what we said about X last week").
Returns only genuinely similar messages — an empty result means it was not discussed.""",
    ),
    Tool(
        name="GetRecentMessages",
        func=get_recent_messages,
        description="""Returns the most recent conversation messages, oldest first.
Input JSON: {"limit": 10}
Use when the user references the immediately preceding turn ("point 8", "that email").""",
    ),
    Tool(
        name="WebSearch",
        func=web_search,
        description="Not configured. Do not use.",
    ),
]