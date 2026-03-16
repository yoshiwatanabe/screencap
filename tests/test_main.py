"""Tests for main.py — written BEFORE implementation (TDD)."""
import json
import logging
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))


def _make_config(tmp: Path) -> dict:
    watch = tmp / "watch"
    watch.mkdir(exist_ok=True)
    output = tmp / "output"
    output.mkdir(exist_ok=True)
    return {
        "watch_dir":        str(watch),
        "output_dir":       str(output),
        "max_age_minutes":  5,
        "image_extensions": [".png"],
        "copilot_loader":   "C:\\npm\\loader.js",
        "copilot_model":    "gpt-5.4",
        "copilot_timeout":  30,
        "metadata_dir":     str(tmp / "metadata"),
        "log_file":         str(tmp / "logs" / "screencap.log"),
        "state_file":       str(tmp / "state.json"),
    }


# ── _pid_alive ────────────────────────────────────────────────────────────────

class TestPidAlive(unittest.TestCase):

    def test_zero_pid_returns_false(self):
        from main import _pid_alive
        self.assertFalse(_pid_alive(0))

    def test_negative_pid_returns_false(self):
        from main import _pid_alive
        self.assertFalse(_pid_alive(-1))

    def test_overflow_pid_returns_false(self):
        from main import _pid_alive
        self.assertFalse(_pid_alive(0x1_0000_0000))  # 2^32

    def test_own_pid_returns_true(self):
        from main import _pid_alive
        self.assertTrue(_pid_alive(os.getpid()))


# ── Lock file ─────────────────────────────────────────────────────────────────

class TestAcquireLock(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.lock = self.tmp / "screencap.lock"

    def test_acquires_when_no_lock_exists(self):
        from main import acquire_lock
        self.assertTrue(acquire_lock(self.lock))
        self.assertTrue(self.lock.exists())

    def test_lock_file_contains_current_pid(self):
        from main import acquire_lock
        acquire_lock(self.lock)
        self.assertEqual(int(self.lock.read_text()), os.getpid())

    def test_returns_false_when_live_process_holds_lock(self):
        # Write our own PID — we are "the other process"
        self.lock.write_text(str(os.getpid()))
        from main import acquire_lock
        self.assertFalse(acquire_lock(self.lock))

    def test_acquires_over_stale_lock(self):
        # Spawn a process, wait for it to exit, then use its (now-dead) PID
        import subprocess
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        dead_pid = proc.pid
        proc.wait()
        self.lock.write_text(str(dead_pid))
        from main import acquire_lock
        self.assertTrue(acquire_lock(self.lock))

    def test_acquires_over_non_numeric_lock(self):
        self.lock.write_text("garbage")
        from main import acquire_lock
        self.assertTrue(acquire_lock(self.lock))


class TestReleaseLock(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.lock = self.tmp / "screencap.lock"

    def test_removes_lock_file(self):
        self.lock.write_text(str(os.getpid()))
        from main import release_lock
        release_lock(self.lock)
        self.assertFalse(self.lock.exists())

    def test_does_not_raise_if_already_gone(self):
        from main import release_lock
        release_lock(self.lock)   # should not raise


# ── run() orchestration ───────────────────────────────────────────────────────

class TestRunExitsEarly(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_exits_cleanly_when_watch_dir_missing(self):
        cfg = _make_config(self.tmp)
        cfg["watch_dir"] = str(self.tmp / "nonexistent")
        from main import run
        code = run(cfg, dry_run=False, lock_path=self.tmp / "test.lock")
        self.assertEqual(code, 0)

    def test_exits_cleanly_when_lock_held(self):
        cfg = _make_config(self.tmp)
        lock = self.tmp / "test.lock"
        lock.write_text(str(os.getpid()))   # we hold the lock
        from main import run
        code = run(cfg, dry_run=False, lock_path=lock)
        self.assertEqual(code, 0)


class TestRunProcessesImages(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg = _make_config(self.tmp)
        (self.tmp / "metadata").mkdir(exist_ok=True)
        (self.tmp / "logs").mkdir(exist_ok=True)
        self.lock = self.tmp / "test.lock"

    def _run(self, ready_images, process_result, dry_run=False):
        with patch("processor.get_ready", return_value=ready_images), \
             patch("analyzer.process_image", return_value=process_result) as mock_analyze:
            from main import run
            code = run(self.cfg, dry_run=dry_run, lock_path=self.lock)
            return code, mock_analyze

    def test_returns_zero_on_normal_run(self):
        code, _ = self._run([], None)
        self.assertEqual(code, 0)

    def test_calls_process_image_for_each_ready_file(self):
        img = Path(self.cfg["watch_dir"]) / "shot.png"
        img.write_bytes(b"data")
        mock_result = {
            "main_category": "development",
            "sub_category":  "python",
            "dest_image":    Path(self.cfg["output_dir"]) / "development" / "python" / "shot.png",
            "dest_sidecar":  Path(self.cfg["output_dir"]) / "development" / "python" / "shot.md",
        }
        code, mock_analyze = self._run([img], mock_result)
        mock_analyze.assert_called_once()
        self.assertEqual(code, 0)

    def test_state_saved_after_successful_analysis(self):
        img = Path(self.cfg["watch_dir"]) / "shot.png"
        img.write_bytes(b"data")
        dest = Path(self.cfg["output_dir"]) / "development" / "python" / "shot.png"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"data")
        mock_result = {
            "main_category": "development",
            "sub_category":  "python",
            "dest_image":    dest,
            "dest_sidecar":  dest.with_suffix(".md"),
        }
        self._run([img], mock_result)
        state_file = Path(self.cfg["state_file"])
        self.assertTrue(state_file.exists(), "state.json should be written")
        state = json.loads(state_file.read_text())
        self.assertIn("shot.png", state)

    def test_dry_run_does_not_call_process_image(self):
        img = Path(self.cfg["watch_dir"]) / "shot.png"
        img.write_bytes(b"data")
        code, mock_analyze = self._run([img], None, dry_run=True)
        mock_analyze.assert_not_called()
        self.assertEqual(code, 0)

    def test_dry_run_does_not_write_state(self):
        img = Path(self.cfg["watch_dir"]) / "shot.png"
        img.write_bytes(b"data")
        self._run([img], None, dry_run=True)
        self.assertFalse(Path(self.cfg["state_file"]).exists(),
                         "dry-run must not write state.json")

    def test_failed_analysis_does_not_write_state_entry(self):
        img = Path(self.cfg["watch_dir"]) / "shot.png"
        img.write_bytes(b"data")
        self._run([img], None)   # process_image returns None = failure
        state_path = Path(self.cfg["state_file"])
        if state_path.exists():
            state = json.loads(state_path.read_text())
            self.assertNotIn("shot.png", state)

    def test_lock_released_after_run(self):
        self._run([], None)
        self.assertFalse(self.lock.exists(), "lock file should be removed after run")

    def test_lock_released_even_if_analysis_fails(self):
        img = Path(self.cfg["watch_dir"]) / "shot.png"
        img.write_bytes(b"data")
        self._run([img], None)   # None = failure
        self.assertFalse(self.lock.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
