"""
Email and calendar provider interfaces, plus the registry that picks one.

The agents never import GmailProvider or OutlookProvider. They call
get_email_provider(), which looks up the user's oauth_connections row and
returns whichever provider they actually connected. Adding a third provider is
a new class plus one branch here.
"""
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class EmailMessage:
    """
    Provider-neutral email. Gmail and Graph return very different shapes;
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
    # attacker-controlled text: anything derived from this content must not be
    # allowed to write persistent state (preferences, searchable history).
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
        Irreversible and outbound. Must never be reachable without explicit
        user confirmation — the model does not approve its own sends.
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
# Order matters only when a user has connected both, which is possible. Gmail
# first preserves existing behaviour for anyone already set up.
_EMAIL_ORDER = ("google", "outlook")


def _connection(user_id: uuid.UUID, provider: str) -> dict | None:
    from paai.db import get_oauth_connection, get_valid_access_token

    conn = get_oauth_connection(user_id, provider)
    if not conn:
        return None
    # Provider access tokens last about an hour. Refreshing here rather than at
    # each call site is what stops the agents working in testing and breaking
    # the next morning.
    conn["access_token"] = get_valid_access_token(provider, user_id)
    conn["user_id"] = user_id
    return conn


def get_email_provider(user_id: uuid.UUID) -> EmailProvider:
    for provider in _EMAIL_ORDER:
        conn = _connection(user_id, provider)
        if not conn:
            continue
        if provider == "google":
            from paai.gmail import GmailProvider
            return GmailProvider(conn)
        if provider == "outlook":
            from paai.outlook import OutlookProvider
            return OutlookProvider(conn)

    raise RuntimeError(
        "No mailbox connected. Connect one in settings before asking about email."
    )


def get_calendar_provider(user_id: uuid.UUID) -> CalendarProvider:
    # Google grants mail and calendar in one consent, so a google connection
    # implies calendar access. Same for Microsoft.
    for provider in _EMAIL_ORDER:
        conn = _connection(user_id, provider)
        if not conn:
            continue
        if provider == "google":
            from paai.calendar import GoogleCalendarProvider
            return GoogleCalendarProvider(conn)
        if provider == "outlook":
            from paai.outlook import OutlookCalendarProvider
            return OutlookCalendarProvider(conn)

    raise RuntimeError(
        "No calendar connected. Connect a mailbox in settings first."
    )


def connected_providers(user_id: uuid.UUID) -> list[str]:
    """For the settings page and the 'no mailbox' banner."""
    from paai.db import list_oauth_providers
    return list_oauth_providers(user_id)
