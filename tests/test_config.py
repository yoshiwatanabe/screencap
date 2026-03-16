"""Tests for config.py — written BEFORE implementation (TDD)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

_BASE_CONFIG = {
    "watch_dir":        "C:\\Users\\test\\Screenshots",
    "output_dir":       "C:\\Users\\test\\Organized",
    "max_age_minutes":  5,
    "image_extensions": [".png", ".jpg"],
    "copilot_loader":   None,   # filled in per-test from a real tmp file
    "copilot_model":    "gpt-5.4",
    "copilot_timeout":  60,
    "metadata_dir":     "REPO_DIR\\metadata",
    "log_file":         "REPO_DIR\\logs\\screencap.log",
    "state_file":       "REPO_DIR\\state.json",
}

# Keys used in assertions that need a stable reference
VALID_CONFIG = _BASE_CONFIG


def write_config(path: Path, overrides: dict | None = None, loader: Path | None = None) -> None:
    cfg = {**_BASE_CONFIG, **(overrides or {})}
    if loader is not None:
        cfg["copilot_loader"] = str(loader)
    path.write_text(json.dumps(cfg), encoding="utf-8")


class TestLoadConfig(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cfg_path = self.tmp / "config.json"
        # Create a real .js file so copilot_loader validation passes by default
        self.loader = self.tmp / "loader.js"
        self.loader.write_text("// dummy")

    def _write(self, overrides: dict | None = None) -> None:
        """Write config.json using the test's real loader file."""
        write_config(self.cfg_path, overrides, loader=self.loader)

    # ── happy path ────────────────────────────────────────────────────────────

    def test_returns_dict_with_all_keys(self):
        self._write()
        from config import load_config
        result = load_config(self.cfg_path)
        self.assertIsInstance(result, dict)
        for key in VALID_CONFIG:
            self.assertIn(key, result)

    def test_non_repo_dir_values_are_unchanged(self):
        self._write()
        from config import load_config
        result = load_config(self.cfg_path)
        self.assertEqual(result["watch_dir"], "C:\\Users\\test\\Screenshots")
        self.assertEqual(result["copilot_model"], "gpt-5.4")
        self.assertEqual(result["max_age_minutes"], 5)

    # ── REPO_DIR token resolution ─────────────────────────────────────────────

    def test_resolves_repo_dir_in_metadata_dir(self):
        self._write()
        from config import load_config
        result = load_config(self.cfg_path)
        self.assertNotIn("REPO_DIR", result["metadata_dir"])
        self.assertIn(str(self.tmp), result["metadata_dir"])

    def test_resolves_repo_dir_in_log_file(self):
        self._write()
        from config import load_config
        result = load_config(self.cfg_path)
        self.assertNotIn("REPO_DIR", result["log_file"])
        self.assertIn(str(self.tmp), result["log_file"])

    def test_resolves_repo_dir_in_state_file(self):
        self._write()
        from config import load_config
        result = load_config(self.cfg_path)
        self.assertNotIn("REPO_DIR", result["state_file"])
        self.assertIn(str(self.tmp), result["state_file"])

    # ── validation ────────────────────────────────────────────────────────────

    def test_raises_value_error_when_key_missing(self):
        self.cfg_path.write_text(json.dumps({"watch_dir": "C:\\test"}), encoding="utf-8")
        from config import load_config
        with self.assertRaises(ValueError):
            load_config(self.cfg_path)

    def test_error_message_names_a_missing_key(self):
        self.cfg_path.write_text(json.dumps({"watch_dir": "C:\\test"}), encoding="utf-8")
        from config import load_config
        with self.assertRaises(ValueError) as ctx:
            load_config(self.cfg_path)
        # At least one missing key should be named in the message
        self.assertTrue(
            any(k in str(ctx.exception) for k in VALID_CONFIG if k != "watch_dir"),
            f"Expected a missing key name in error: {ctx.exception}",
        )

    def test_raises_on_file_not_found(self):
        from config import load_config
        with self.assertRaises(FileNotFoundError):
            load_config(self.tmp / "nonexistent.json")

    def test_raises_on_malformed_json(self):
        self.cfg_path.write_text("{not valid json", encoding="utf-8")
        from config import load_config
        with self.assertRaises(ValueError):
            load_config(self.cfg_path)

    # ── directory creation ────────────────────────────────────────────────────

    def test_creates_metadata_dir_if_absent(self):
        meta = self.tmp / "meta_new"
        self.assertFalse(meta.exists())
        self._write({"metadata_dir": str(meta)})
        from config import load_config
        load_config(self.cfg_path)
        self.assertTrue(meta.is_dir())

    def test_creates_log_parent_dir_if_absent(self):
        log_dir = self.tmp / "logs_new"
        self.assertFalse(log_dir.exists())
        self._write({"log_file": str(log_dir / "screencap.log")})
        from config import load_config
        load_config(self.cfg_path)
        self.assertTrue(log_dir.is_dir())

    def test_does_not_fail_if_dirs_already_exist(self):
        meta = self.tmp / "meta_exists"
        meta.mkdir()
        self._write({"metadata_dir": str(meta)})
        from config import load_config
        load_config(self.cfg_path)   # should not raise
        self.assertTrue(meta.is_dir())

    # ── explicit vs auto-discovered path ─────────────────────────────────────

    def test_explicit_path_is_used_when_provided(self):
        other_cfg = self.tmp / "other.json"
        write_config(other_cfg, {"copilot_model": "gemini-3-pro-preview"}, loader=self.loader)
        from config import load_config
        result = load_config(other_cfg)
        self.assertEqual(result["copilot_model"], "gemini-3-pro-preview")

    # ── copilot_loader validation ─────────────────────────────────────────────

    def test_raises_when_copilot_loader_not_js(self):
        fake_ps1 = self.tmp / "loader.ps1"
        fake_ps1.write_text("dummy")
        write_config(self.cfg_path, {"copilot_loader": str(fake_ps1)})
        from config import load_config
        with self.assertRaises(ValueError) as ctx:
            load_config(self.cfg_path)
        self.assertIn("copilot_loader", str(ctx.exception))

    def test_raises_when_copilot_loader_does_not_exist(self):
        write_config(self.cfg_path, {"copilot_loader": str(self.tmp / "missing.js")})
        from config import load_config
        with self.assertRaises(ValueError) as ctx:
            load_config(self.cfg_path)
        self.assertIn("copilot_loader", str(ctx.exception))

    def test_accepts_valid_js_loader(self):
        js_file = self.tmp / "loader.js"
        js_file.write_text("dummy")
        write_config(self.cfg_path, {"copilot_loader": str(js_file)})
        from config import load_config
        result = load_config(self.cfg_path)
        self.assertEqual(result["copilot_loader"], str(js_file))

    # ── copilot_model allowlist ───────────────────────────────────────────────

    def test_raises_when_model_not_in_allowlist(self):
        self._write({"copilot_model": "gpt-4-turbo-evil"})
        from config import load_config
        with self.assertRaises(ValueError) as ctx:
            load_config(self.cfg_path)
        self.assertIn("copilot_model", str(ctx.exception))

    def test_accepts_all_allowed_models(self):
        from config import ALLOWED_MODELS, load_config
        js_file = self.tmp / "loader.js"
        js_file.write_text("dummy")
        for model in ALLOWED_MODELS:
            with self.subTest(model=model):
                write_config(self.cfg_path, {
                    "copilot_model": model,
                    "copilot_loader": str(js_file),
                })
                result = load_config(self.cfg_path)
                self.assertEqual(result["copilot_model"], model)

    # ── REPO_RELATIVE_KEYS confinement ────────────────────────────────────────

    def test_raises_when_metadata_dir_outside_repo(self):
        import tempfile as tf
        outside = Path(tf.mkdtemp()) / "metadata"
        self._write({"metadata_dir": str(outside)})
        from config import load_config
        with self.assertRaises(ValueError) as ctx:
            load_config(self.cfg_path)
        self.assertIn("metadata_dir", str(ctx.exception))

    def test_raises_when_state_file_outside_repo(self):
        import tempfile as tf
        outside = Path(tf.mkdtemp()) / "state.json"
        self._write({"state_file": str(outside)})
        from config import load_config
        with self.assertRaises(ValueError) as ctx:
            load_config(self.cfg_path)
        self.assertIn("state_file", str(ctx.exception))

    def test_raises_when_log_file_outside_repo(self):
        import tempfile as tf
        outside = Path(tf.mkdtemp()) / "logs" / "screencap.log"
        self._write({"log_file": str(outside)})
        from config import load_config
        with self.assertRaises(ValueError) as ctx:
            load_config(self.cfg_path)
        self.assertIn("log_file", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
