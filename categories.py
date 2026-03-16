"""Category tree — load, save, format, and update the categories dictionary."""
import json
import os
import tempfile
from pathlib import Path

from utils import sanitize_name


def load_categories(path: Path) -> dict:
    """Load categories from JSON file. Returns {} if file does not exist."""
    path = Path(path)
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_categories(path: Path, cats: dict) -> None:
    """Atomically save categories dict to JSON file."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.stem + "_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(cats, indent=2, ensure_ascii=False))
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def format_tree(cats: dict) -> str:
    """Format category dict as an indented tree string for the LLM prompt.

    Sanitizes all names defensively (guards against manually-edited categories.json).
    Always appends 'others' as the last entry (implicit catch-all).
    'others' in the input dict is skipped to avoid duplication.
    """
    lines = []
    for main, subs in cats.items():
        if main == "others":
            continue
        safe_main = sanitize_name(main)
        if safe_main == "others":
            continue
        lines.append(safe_main)
        for sub in subs:
            safe_sub = sanitize_name(sub)
            if safe_sub != "others":
                lines.append(f"  {safe_sub}")
    lines.append("others")
    return "\n".join(lines)


def ensure_category(cats: dict, main: str, sub: str | None) -> bool:
    """Add main/sub to cats if not already present. Returns True if modified.

    'others' is the implicit catch-all and is never written to the dict.
    """
    if main == "others":
        return False

    modified = False

    if main not in cats:
        cats[main] = []
        modified = True

    if sub is not None and sub not in cats[main]:
        cats[main].append(sub)
        modified = True

    return modified
