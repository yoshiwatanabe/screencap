"""Shared utilities."""
import re

_WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul",
    "com1", "com2", "com3", "com4", "com5", "com6", "com7", "com8", "com9",
    "lpt1", "lpt2", "lpt3", "lpt4", "lpt5", "lpt6", "lpt7", "lpt8", "lpt9",
}

MAX_CATEGORY_LEN = 50


def sanitize_name(name: str) -> str:
    """Make an LLM-generated category name safe as a directory component.

    - Lowercases and strips whitespace
    - Replaces any character outside [a-z0-9-] with a hyphen
    - Collapses runs of hyphens; strips leading/trailing hyphens
    - Truncates to MAX_CATEGORY_LEN characters
    - Falls back to "others" for empty results or Windows reserved names
    """
    name = str(name).lower().strip()
    name = re.sub(r"[^a-z0-9\-]", "-", name)
    name = re.sub(r"-{2,}", "-", name)
    name = name.strip("-")
    name = name[:MAX_CATEGORY_LEN]
    if not name or name in _WINDOWS_RESERVED:
        return "others"
    return name
