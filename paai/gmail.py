"""
Gmail via the Google API client, behind the EmailProvider interface.

Converted from the previous module-level tool functions so the agents can be
provider-agnostic: tools now ask providers.get_email_provider() for whatever
mailbox the user actually connected, and never import this module directly.
"""
import base64
import re
from datetime import datetime, timezone
from email.mime.text import MIMEText
from email.utils import parsedate_to_datetime

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from paai.providers import EmailMessage, EmailProvider

# Reading only is not enough once the email agent drafts replies. gmail.compose
# covers drafts without granting send, which is the scope you want: a model that
# has read an attacker's email should be able to prepare a reply, not deliver
# one. Add gmail.send only alongside a human approval gate.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
]


def _header(headers: list[dict], name: str) -> str:
    for h in headers:
        if h.get("name", "").lower() == name:
            return h.get("value", "")
    return ""


def _decode(data: str) -> str:
    if not data:
        return ""
    return base64.urlsafe_b64decode(data.encode()).decode("utf-8", errors="replace")


def _extract_body(payload: dict) -> str:
    """
    Walk the MIME tree for text/plain, falling back to text/html.

    The previous version only looked one level deep at payload["parts"], so any
    multipart/alternative nested inside multipart/mixed — which is most real
    email with an attachment — returned an empty body.
    """
    plain, html = [], []

    def walk(part: dict):
        mime = part.get("mimeType", "")
        body = part.get("body", {})
        if mime == "text/plain" and body.get("data"):
            plain.append(_decode(body["data"]))
        elif mime == "text/html" and body.get("data"):
            html.append(_decode(body["data"]))
        for child in part.get("parts", []) or []:
            walk(child)

    walk(payload)

    if plain:
        return "\n".join(plain)
    if html:
        # Crude, but better than handing the model a wall of markup.
        text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", "\n".join(html), flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()
    return ""


def _parse_date(value: str) -> datetime:
    try:
        dt = parsedate_to_datetime(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except Exception:
        return datetime.now(timezone.utc)


class GmailProvider(EmailProvider):
    name = "google"

    def __init__(self, connection: dict):
        # connection comes from providers._connection(), which has already
        # refreshed the access token if it was near expiry.
        creds = Credentials(token=connection["access_token"])
        self._svc = build("gmail", "v1", credentials=creds, cache_discovery=False)

    # ── internals ─────────────────────────────────────────────────────────
    def _to_message(self, raw: dict) -> EmailMessage:
        payload = raw.get("payload", {})
        headers = payload.get("headers", [])
        to_line = _header(headers, "to")

        return EmailMessage(
            id=raw["id"],
            thread_id=raw.get("threadId"),
            subject=_header(headers, "subject") or "(no subject)",
            sender=_header(headers, "from"),
            recipients=[a.strip() for a in to_line.split(",") if a.strip()],
            date=_parse_date(_header(headers, "date")),
            snippet=(raw.get("snippet") or "")[:400],
            body=_extract_body(payload),
            is_unread="UNREAD" in (raw.get("labelIds") or []),
            labels=raw.get("labelIds") or [],
            # Attacker-controlled text. The guardrail layer reads this to decide
            # what may write persistent state.
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
        parts = []
        if query:
            parts.append(query)
        if after:
            parts.append(f"after:{after.strftime('%Y/%m/%d')}")
        if before:
            parts.append(f"before:{before.strftime('%Y/%m/%d')}")
        q = " ".join(parts)

        listing = self._svc.users().messages().list(
            userId="me",
            q=q or None,
            labelIds=["INBOX"],
            maxResults=min(max_results, 100),
        ).execute()

        ids = [m["id"] for m in listing.get("messages", [])]

        # Gmail's list returns ids only, so full content costs one call each.
        # Acceptable at these sizes; batch requests are the fix if it ever
        # becomes the bottleneck.
        messages = []
        for mid in ids:
            raw = self._svc.users().messages().get(
                userId="me", id=mid, format="full"
            ).execute()
            messages.append(self._to_message(raw))

        return messages

    def get_message(self, message_id: str) -> EmailMessage:
        raw = self._svc.users().messages().get(
            userId="me", id=message_id, format="full"
        ).execute()
        return self._to_message(raw)

    def create_draft(
        self, to: list[str], subject: str, body: str, reply_to_id: str | None = None
    ) -> str:
        mime = MIMEText(body)
        mime["To"] = ", ".join(to)
        mime["Subject"] = subject

        message = {"raw": base64.urlsafe_b64encode(mime.as_bytes()).decode()}

        if reply_to_id:
            original = self._svc.users().messages().get(
                userId="me", id=reply_to_id, format="metadata",
                metadataHeaders=["Message-ID", "Subject"],
            ).execute()
            headers = original.get("payload", {}).get("headers", [])
            msg_id_header = _header(headers, "message-id")
            if msg_id_header:
                mime["In-Reply-To"] = msg_id_header
                mime["References"] = msg_id_header
                message["raw"] = base64.urlsafe_b64encode(mime.as_bytes()).decode()
            message["threadId"] = original.get("threadId")

        draft = self._svc.users().drafts().create(
            userId="me", body={"message": message}
        ).execute()
        return draft["id"]

    def send_message(
        self, to: list[str], subject: str, body: str, reply_to_id: str | None = None
    ) -> str:
        """
        Irreversible and outbound. Requires the gmail.send scope, which is
        deliberately not in SCOPES above — add it only together with a human
        approval gate in the agent layer.
        """
        draft_id = self.create_draft(to, subject, body, reply_to_id)
        sent = self._svc.users().drafts().send(
            userId="me", body={"id": draft_id}
        ).execute()
        return sent["id"]