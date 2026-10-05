"""
The provider registry must resolve whatever name the OAuth flow stored.

Regression test for connected Outlook mailboxes being invisible to the agents:
connections are stored as "microsoft", the registry looked for "outlook".
"""
from datetime import datetime, timedelta, timezone

from paai.db import get_or_create_user, upsert_oauth_connection
from paai.providers import get_calendar_provider, get_email_provider


def _connect(user_id, provider):
    upsert_oauth_connection(
        user_id=user_id,
        provider=provider,
        access_token="fake-access",
        refresh_token="fake-refresh",
        # Far enough ahead that no refresh call is attempted.
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        account_email="someone@example.com",
    )


def test_microsoft_connection_resolves_outlook():
    from paai.outlook import OutlookCalendarProvider, OutlookProvider

    user = get_or_create_user("outlook-registry@test.local")
    _connect(user, "microsoft")

    assert isinstance(get_email_provider(user), OutlookProvider)
    assert isinstance(get_calendar_provider(user), OutlookCalendarProvider)