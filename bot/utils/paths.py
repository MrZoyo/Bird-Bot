"""Repository-relative runtime path helpers.

Config files intentionally keep operator-facing paths short (for example
``./data/bot.db``). Runtime code should resolve those paths against the
repository root, not whatever directory happened to launch ``python``.
"""
from __future__ import annotations

from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def project_path(*parts: str | Path) -> Path:
    """Return a path under the repository root."""
    return PROJECT_ROOT.joinpath(*parts)


def resolve_project_path(path: str | Path) -> Path:
    """Resolve relative paths from the repository root.

    Absolute paths and ``~``-prefixed operator paths are preserved as
    deployment-specific overrides.
    """
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate
    return project_path(candidate)


def resolve_project_path_string(path: str | Path) -> str:
    return str(resolve_project_path(path))


def ensure_parent_dir(path: str | Path) -> Path:
    target = resolve_project_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    return target
