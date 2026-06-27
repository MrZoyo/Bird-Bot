import re
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = [
    PROJECT_ROOT / "bot",
    PROJECT_ROOT / "tools",
    PROJECT_ROOT / "run.py",
]

BAD_LOGGING_PATTERNS = [
    re.compile(
        r"\b(?:logging|logger)\.(?:debug|info|warning|error|exception|critical)"
        r"\(f[\"'][^\"'\n]*\{[^}\n]*\.(?:id|name|display_name)\}"
    ),
    re.compile(
        r"\b(?:logging|logger)\.(?:debug|info|warning|error|exception|critical)"
        r"\(f[\"'][^\"'\n]*(?:user|channel|guild|role) \{[^}\n]*(?:user|channel|guild|role)_id\}"
    ),
]


def _python_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        if root.is_file():
            files.append(root)
            continue
        files.extend(root.rglob("*.py"))
    return sorted(files)


def test_logging_callsite_avoids_raw_discord_identifiers():
    offenders: list[str] = []
    for path in _python_files():
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if any(pattern.search(line) for pattern in BAD_LOGGING_PATTERNS):
                relative_path = path.relative_to(PROJECT_ROOT)
                offenders.append(f"{relative_path}:{line_number}: {line.strip()}")

    assert offenders == []
