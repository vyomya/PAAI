"""
Email provider interface — the Phase 6 hook.

Gmail is the only implementation today. Outlook arrives in Phase 6 via
Microsoft Graph. Defining the interface now costs nothing and means Gmail gets
written against it rather than retrofitted into it later.

The agents never import GmailProvider directly. They call get_provider(user_id),
which looks up the user's oauth_connections row and returns whichever provider
they actually connected. That is the whole point: adding Outlook becomes a new
class plus one line in the registry, not a rewrite of summarizer_agent.
"""
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class EmailMessage:
    """
    Provider-neutral email. Gmail and Graph return wildly different shapes;
    normalising here keeps provider details out of the agents.
    """
    id: str
    thread_id: str | None
    subject: str
    sender: str
    recipients: list[str]
    date: datetime
    snippet: str
    body: str
    is_unread: bool = False
    labels: list[str] = field(default_factory=list)

    # Set by the provider, read by the guardrail layer. Email bodies are
    # attacker-controlled text; anything derived from this content must not be
    # allowed to write persistent state (preferences, history).
    is_untrusted: bool = True


@dataclass
class CalendarEvent:
    id: str
    title: str
    start: datetime
    end: datetime
    location: str | None = None
    attendees: list[str] = field(default_factory=list)
    link: str | None = None


class EmailProvider(ABC):
    """One implementation per provider. Constructed with a user's tokens."""

    name: str

    @abstractmethod
    def list_messages(
        self,
        max_results: int = 10,
        after: datetime | None = None,
        before: datetime | None = None,
        query: str | None = None,
    ) -> list[EmailMessage]:
        ...

    @abstractmethod
    def get_message(self, message_id: str) -> EmailMessage:
        ...

    @abstractmethod
    def create_draft(
        self, to: list[str], subject: str, body: str, reply_to_id: str | None = None
    ) -> str:
        """Returns the draft id. Drafts are reversible — sending is not."""
        ...

    @abstractmethod
    def send_message(
        self, to: list[str], subject: str, body: str, reply_to_id: str | None = None
    ) -> str:
        """
        Irreversible and outbound. Per the guardrail plan this must never be
        reachable without explicit user confirmation — the model does not get
        to approve its own send.
        """
        ...


class CalendarProvider(ABC):
    name: str

    @abstractmethod
    def list_events(self, start: datetime, end: datetime) -> list[CalendarEvent]:
        ...

    @abstractmethod
    def create_event(
        self,
        title: str,
        start: datetime,
        end: datetime,
        attendees: list[str] | None = None,
        location: str | None = None,
    ) -> str:
        ...


# ── Registry ──────────────────────────────────────────────────────────────────
def get_email_provider(user_id: uuid.UUID) -> EmailProvider:
    """
    Returns whichever provider this user connected.

    Phase 6 adds one branch here and nothing else changes upstream.
    """
    from paai.db import get_oauth_connection

    conn = get_oauth_connection(user_id, "gmail")
    if conn:
        from paai.gmail import GmailProvider
        return GmailProvider(conn)

    # Phase 6:
    # conn = get_oauth_connection(user_id, "outlook")
    # if conn:
    #     from paai.outlook import OutlookProvider
    #     return OutlookProvider(conn)

    raise RuntimeError(
        f"No email provider connected for user {user_id}. "
        "The user needs to connect a mailbox first."
    )


def get_calendar_provider(user_id: uuid.UUID) -> CalendarProvider:
    from paai.db import get_oauth_connection

    conn = get_oauth_connection(user_id, "gmail")  # Google grants both in one consent
    if conn:
        from paai.calendar import GoogleCalendarProvider
        return GoogleCalendarProvider(conn)

    raise RuntimeError(f"No calendar provider connected for user {user_id}.")
