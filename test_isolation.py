# test_isolation.py
import uuid, pytest
from db import get_or_create_user, save_message, search_messages, load_preferences
from user_context import user_context, get_current_user, NoUserContextError

def test_search_is_user_scoped():
    alice = get_or_create_user("alice@test.local")
    bob = get_or_create_user("bob@test.local")
    save_message(alice, "s1", "user", "my bank password reminder")
    assert search_messages(bob, "bank password") == []
    assert load_preferences(bob) == {}

def test_context_required():
    with pytest.raises(NoUserContextError):
        get_current_user()

def test_context_isolates():
    a, b = uuid.uuid4(), uuid.uuid4()
    with user_context(a):
        assert get_current_user() == a
        with user_context(b):
            assert get_current_user() == b
        assert get_current_user() == a