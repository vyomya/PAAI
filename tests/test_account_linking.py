"""
Account linking must never hand an existing account to a different provider.

Regression tests for the Microsoft "nOAuth" takeover: Microsoft emails were
treated as verified and linked onto existing accounts by address, so a tenant
admin who set `mail` to someone else's address could sign in as them — and as
the owner, since owner checks compared emails.
"""
import uuid

import pytest

from paai.access import is_owner_user
from paai.config import settings
from paai.db import (
    AccountConflict,
    get_or_create_user,
    get_or_create_user_from_oauth,
    get_user_by_id,
)


def _email(tag: str) -> str:
    return f"{tag}-{uuid.uuid4().hex[:8]}@test.local"


def test_microsoft_login_cannot_claim_google_account():
    email = _email("victim")
    victim = get_or_create_user_from_oauth("google", "g-" + email, email, True)

    with pytest.raises(AccountConflict) as exc:
        get_or_create_user_from_oauth("microsoft", "m-attacker", email, False)

    assert exc.value.existing_provider == "google"
    # The victim's account is untouched and still resolves for Google.
    assert get_or_create_user_from_oauth("google", "g-" + email, email, True) == victim


def test_verified_email_does_not_cross_providers_either():
    # Even a provider that does verify email must not take over an account
    # that already signs in elsewhere (blocks pre-registration hijacks).
    email = _email("first-ms")
    get_or_create_user_from_oauth("microsoft", "m-" + email, email, False)

    with pytest.raises(AccountConflict):
        get_or_create_user_from_oauth("google", "g-" + email, email, True)


def test_returning_user_matches_on_subject():
    email = _email("returning")
    first = get_or_create_user_from_oauth("microsoft", "m-" + email, email, False)
    again = get_or_create_user_from_oauth("microsoft", "m-" + email, email, False)
    assert first == again


def test_legacy_row_is_claimed_by_verified_login():
    email = _email("legacy")
    legacy = get_or_create_user(email)  # no auth_provider, as seeded pre-OAuth
    claimed = get_or_create_user_from_oauth("google", "g-" + email, email, True)
    assert claimed == legacy
    assert get_user_by_id(legacy).auth_provider == "google"


def test_owner_requires_verified_provider(monkeypatch):
    owner_email = _email("owner")
    monkeypatch.setattr(settings, "owner_email", owner_email)

    real = get_or_create_user_from_oauth("google", "g-" + owner_email, owner_email, True)
    assert is_owner_user(get_user_by_id(real))

    other_email = _email("spoof")
    monkeypatch.setattr(settings, "owner_email", other_email)
    spoof = get_or_create_user_from_oauth("microsoft", "m-" + other_email, other_email, False)
    assert not is_owner_user(get_user_by_id(spoof))