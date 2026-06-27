from types import SimpleNamespace

from bot.utils.log_helpers import fmt_channel, fmt_guild, fmt_role, fmt_user


def test_fmt_user_includes_display_name_username_and_id():
    user = SimpleNamespace(id=123, display_name="Alice", name="alice_raw")

    assert fmt_user(user) == "Alice / alice_raw (123)"


def test_fmt_user_omits_duplicate_username():
    user = SimpleNamespace(id=123, display_name="alice", name="alice")

    assert fmt_user(user) == "alice (123)"


def test_fmt_channel_and_role_use_name_with_id():
    channel = SimpleNamespace(id=456, name="general")
    role = SimpleNamespace(id=789, name="Admin")
    guild = SimpleNamespace(id=101, name="Secret Lab")

    assert fmt_channel(channel) == "general (456)"
    assert fmt_role(role) == "Admin (789)"
    assert fmt_guild(guild) == "Secret Lab (101)"


def test_fmt_raw_ids_are_marked_unknown():
    assert fmt_user(123) == "unknown (123)"
    assert fmt_channel(456) == "unknown (456)"
    assert fmt_role(789) == "unknown (789)"
    assert fmt_guild(101) == "unknown (101)"


def test_fmt_ids_use_ascii_parentheses():
    user = SimpleNamespace(id=123, display_name="Alice", name="alice_raw")

    assert "（" not in fmt_user(user)
    assert "）" not in fmt_user(user)
    assert fmt_user(user).endswith("(123)")
