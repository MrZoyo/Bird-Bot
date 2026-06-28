from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath
from typing import MutableMapping


DB_KEY_FILE_ENV = "DCGSH_DB_KEY_FILE"


def load_env_file(
    env_path: str | Path,
    *,
    override: bool = False,
    environ: MutableMapping[str, str] | None = None,
) -> None:
    """Load simple KEY=VALUE pairs from a local env file.

    Existing process environment wins by default so production launchers can
    inject secrets without the repository-local test env overriding them.
    """
    path = Path(env_path)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return

    target_environ = os.environ if environ is None else environ

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line.removeprefix("export ").lstrip()

        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue

        if not override and key in target_environ:
            continue

        value = _strip_matching_quotes(value.strip())
        if key == DB_KEY_FILE_ENV and value and not _is_absolute_path(value):
            value = str((path.parent / value).resolve())
        target_environ[key] = value


def _strip_matching_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        return value[1:-1]
    return value


def _is_absolute_path(value: str) -> bool:
    return Path(value).is_absolute() or PureWindowsPath(value).is_absolute()
