from types import SimpleNamespace

from bot.utils.log_helpers import fmt_channel, fmt_role, fmt_user


def test_fmt_user_prefers_display_name_with_id():
    user = SimpleNamespace(id=123, display_name="Alice", name="alice_raw")

    assert fmt_user(user) == "Alice (123)"


def test_fmt_channel_and_role_use_name_with_id():
    channel = SimpleNamespace(id=456, name="general")
    role = SimpleNamespace(id=789, name="Admin")

    assert fmt_channel(channel) == "general (456)"
    assert fmt_role(role) == "Admin (789)"


def test_fmt_raw_ids_are_marked_unknown():
    assert fmt_user(123) == "unknown (123)"
    assert fmt_channel(456) == "unknown (456)"
    assert fmt_role(789) == "unknown (789)"
