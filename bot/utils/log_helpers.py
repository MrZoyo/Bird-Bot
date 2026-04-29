from typing import Any


def _entity_id(entity: Any) -> int | str | None:
    if entity is None:
        return None
    if isinstance(entity, int | str):
        return entity
    return getattr(entity, "id", None)


def _entity_name(entity: Any, attrs: tuple[str, ...]) -> str:
    if entity is None or isinstance(entity, int | str):
        return "unknown"

    for attr in attrs:
        value = getattr(entity, attr, None)
        if value:
            return str(value)

    return "unknown"


def _format_entity(entity: Any, attrs: tuple[str, ...]) -> str:
    entity_id = _entity_id(entity)
    name = _entity_name(entity, attrs)
    if entity_id is None:
        return name
    return f"{name} ({entity_id})"


def _user_label(user: Any) -> str:
    if user is None or isinstance(user, int | str):
        return "unknown"

    display_name = _entity_name(user, ("display_name", "global_name", "name"))
    username = getattr(user, "name", None)

    if username and str(username) != display_name:
        return f"{display_name} / {username}"
    return display_name


def fmt_user(user: Any) -> str:
    """Format a Discord user/member or raw user id for logs."""
    entity_id = _entity_id(user)
    label = _user_label(user)
    if entity_id is None:
        return label
    return f"{label} ({entity_id})"


def fmt_channel(channel: Any) -> str:
    """Format a Discord channel/thread or raw channel id for logs."""
    return _format_entity(channel, ("name",))


def fmt_role(role: Any) -> str:
    """Format a Discord role or raw role id for logs."""
    return _format_entity(role, ("name",))
