"""Scan watch_dir, track processed files, manage state."""
import hashlib
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path


def load_state(path: Path) -> dict:
    """Load state.json. Returns {} if file does not exist."""
    path = Path(path)
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def save_state(path: Path, state: dict) -> None:
    """Atomically save state dict to JSON file."""
    path = Path(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=path.stem + "_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(state, indent=2, ensure_ascii=False))
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def file_hash(path: Path) -> str:
    """Return SHA-256 hex digest of file contents."""
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def get_ready(
    watch_dir: Path,
    extensions: list[str],
    max_age_minutes: float,
    state: dict,
) -> list[Path]:
    """Return image files that are old enough and not yet processed.

    Scans watch_dir top-level only (no recursion).
    Excludes files younger than max_age_minutes.
    Excludes files whose name is already a key in state.
    Returns files sorted oldest-first by mtime.
    """
    watch_dir = Path(watch_dir)
    ext_set = {e.lower() for e in extensions}
    threshold = max_age_minutes * 60
    now = time.time()

    candidates = []
    for p in watch_dir.iterdir():
        if not p.is_file():
            continue
        if p.suffix.lower() not in ext_set:
            continue
        if p.name in state:
            continue
        mtime = p.stat().st_mtime
        if now - mtime >= threshold:
            candidates.append((p, mtime))

    candidates.sort(key=lambda t: t[1])
    return [p for p, _ in candidates]


def mark_processed(
    state: dict,
    original_name: str,
    hash_val: str,
    main_cat: str,
    sub_cat: str | None,
    dest_image: Path,
    dest_sidecar: Path,
) -> None:
    """Record a processed file in the state dict."""
    state[original_name] = {
        "hash":          hash_val,
        "processed_at":  datetime.now(timezone.utc).isoformat(),
        "main_category": main_cat,
        "sub_category":  sub_cat,
        "dest_image":    str(dest_image),
        "dest_sidecar":  str(dest_sidecar),
    }


def prune_state(state: dict) -> int:
    """Remove state entries whose dest_image no longer exists.

    Returns count of removed entries.
    """
    to_remove = [
        name for name, entry in state.items()
        if not Path(entry.get("dest_image", "")).exists()
    ]
    for name in to_remove:
        del state[name]
    return len(to_remove)
