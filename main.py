"""Entry point — invoked by Windows Task Scheduler via pythonw.exe."""
import argparse
import ctypes
import logging
import logging.handlers
import os
import sys
from pathlib import Path

import analyzer
import categories
import processor
from config import load_config


def _pid_alive(pid: int) -> bool:
    """Return True if the process with this PID is currently running (Windows)."""
    if not (1 <= pid <= 0xFFFFFFFF):
        return False
    try:
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return False
        exit_code = ctypes.c_ulong()
        kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code))
        kernel32.CloseHandle(handle)
        return exit_code.value == STILL_ACTIVE
    except Exception:  # broad catch is intentional: conservative fallback on any ctypes/OS error
        return False


def acquire_lock(lock_path: Path) -> bool:
    """Atomically acquire lock file. Returns False if a live process holds it.

    Uses O_CREAT|O_EXCL for atomic creation. If the file already exists,
    reads the PID and checks whether that process is still alive; if stale,
    removes the file and retries once.
    """
    lock_path = Path(lock_path)
    pid_bytes = str(os.getpid()).encode()

    for _ in range(2):  # at most one stale-lock retry
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            try:
                os.write(fd, pid_bytes)
            finally:
                os.close(fd)
            return True
        except FileExistsError:
            # File exists — check whether the owning PID is still alive
            try:
                pid = int(lock_path.read_text().strip())
            except (OSError, ValueError):
                pid = None

            if pid is not None and _pid_alive(pid):
                return False  # live owner — do not steal the lock

            # Stale lock — remove and retry once
            try:
                lock_path.unlink()
            except OSError:
                pass  # lost a race; next O_CREAT|O_EXCL will re-check

    return False  # failed to acquire after retry


def release_lock(lock_path: Path) -> None:
    """Remove lock file if it exists."""
    try:
        Path(lock_path).unlink()
    except FileNotFoundError:
        pass


def _setup_logging(log_file: Path) -> logging.Logger:
    log = logging.getLogger("screencap")
    log.setLevel(logging.DEBUG)
    if not log.handlers:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-8s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        ))
        log.addHandler(handler)
    return log


def run(config: dict, dry_run: bool = False,
        lock_path: Path | None = None) -> int:
    """Execute one monitoring cycle. Returns 0 always (errors are logged)."""
    if lock_path is None:
        lock_path = Path(__file__).parent / "screencap.lock"

    log = _setup_logging(Path(config["log_file"]))
    mode = "[DRY-RUN] " if dry_run else ""
    log.info("%sRun started", mode)

    # ── Guard: watch_dir must exist ───────────────────────────────────────────
    watch_dir = Path(config["watch_dir"])
    if not watch_dir.exists():
        log.warning("watch_dir not found: %s — skipping run", watch_dir)
        return 0

    # ── Guard: acquire lock ───────────────────────────────────────────────────
    if not acquire_lock(lock_path):
        log.warning("Another run is in progress (lock: %s) — skipping", lock_path)
        return 0

    analyzed = 0
    skipped = 0
    try:
        state = processor.load_state(Path(config["state_file"]))
        cats = categories.load_categories(
            Path(config["metadata_dir"]) / "categories.json"
        )

        ready = processor.get_ready(
            watch_dir,
            config["image_extensions"],
            config["max_age_minutes"],
            state,
        )
        log.info("%s%d image(s) ready for processing", mode, len(ready))

        if not dry_run:
            cats_modified = False
            for image in ready:
                result = analyzer.process_image(image, config, cats, log)
                if result:
                    if categories.ensure_category(
                        cats, result["main_category"], result["sub_category"]
                    ):
                        cats_modified = True
                    processor.mark_processed(
                        state,
                        original_name=image.name,
                        hash_val=processor.file_hash(image) if image.exists() else "",
                        main_cat=result["main_category"],
                        sub_cat=result["sub_category"],
                        dest_image=result["dest_image"],
                        dest_sidecar=result["dest_sidecar"],
                    )
                    analyzed += 1
                else:
                    skipped += 1

            if cats_modified:
                categories.save_categories(
                    Path(config["metadata_dir"]) / "categories.json", cats
                )
            processor.prune_state(state)
            processor.save_state(Path(config["state_file"]), state)
        else:
            for image in ready:
                log.info("[DRY-RUN] would process: %s", image.name)

    finally:
        release_lock(lock_path)

    log.info("%sRun complete — analyzed: %d, skipped/failed: %d",
             mode, analyzed, skipped)
    return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="screencap monitor")
    parser.add_argument("--dry-run", action="store_true",
                        help="log intended actions without moving files")
    parser.add_argument("--config", type=Path, default=None,
                        help="path to config.json (default: config.json next to main.py)")
    args = parser.parse_args()

    try:
        config = load_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        print(f"screencap: config error — {exc}", file=sys.stderr)
        sys.exit(1)

    sys.exit(run(config, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
