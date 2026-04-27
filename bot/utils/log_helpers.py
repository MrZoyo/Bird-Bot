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


def fmt_user(user: Any) -> str:
    """Format a Discord user/member or raw user id for logs."""
    return _format_entity(user, ("display_name", "global_name", "name"))


def fmt_channel(channel: Any) -> str:
    """Format a Discord channel/thread or raw channel id for logs."""
    return _format_entity(channel, ("name",))


def fmt_role(role: Any) -> str:
    """Format a Discord role or raw role id for logs."""
    return _format_entity(role, ("name",))
