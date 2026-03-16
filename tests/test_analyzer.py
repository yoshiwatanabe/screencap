"""Tests for analyzer.py — written BEFORE implementation (TDD)."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))


def _mock_result(stdout="", returncode=0, stderr=""):
    r = MagicMock()
    r.stdout = stdout
    r.returncode = returncode
    r.stderr = stderr
    return r


def _good_response(main="development", sub="python",
                   desc="VS Code editor open with a Python file."):
    return json.dumps({
        "main_category": main,
        "sub_category": sub,
        "description": desc,
    })


def _make_config(output_dir: Path) -> dict:
    return {
        "output_dir":      str(output_dir),
        "copilot_loader":  "C:\\npm\\loader.js",
        "copilot_model":   "gpt-5.4",
        "copilot_timeout": 30,
    }


class TestProcessImageSuccess(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.watch = self.tmp / "watch"
        self.watch.mkdir()
        self.output = self.tmp / "output"
        self.output.mkdir()
        self.image = self.watch / "shot.png"
        self.image.write_bytes(b"fake-png")
        self.config = _make_config(self.output)
        self.cats = {}

    def _run(self, stdout):
        import logging
        log = logging.getLogger("test")
        with patch("subprocess.run", return_value=_mock_result(stdout=stdout)):
            from analyzer import process_image
            return process_image(self.image, self.config, self.cats, log)

    def test_returns_dict_on_success(self):
        result = self._run(_good_response())
        self.assertIsInstance(result, dict)

    def test_result_has_required_keys(self):
        result = self._run(_good_response())
        for key in ("main_category", "sub_category", "dest_image", "dest_sidecar"):
            self.assertIn(key, result)

    def test_image_moved_to_category_dir(self):
        result = self._run(_good_response("development", "python"))
        dest = Path(result["dest_image"])
        self.assertTrue(dest.exists(), f"Expected image at {dest}")
        self.assertFalse(self.image.exists(), "Original should be moved")
        self.assertIn("development", dest.parts)
        self.assertIn("python", dest.parts)

    def test_sidecar_created_in_same_dir_as_image(self):
        result = self._run(_good_response("development", "python"))
        dest_img = Path(result["dest_image"])
        dest_md = Path(result["dest_sidecar"])
        self.assertTrue(dest_md.exists())
        self.assertEqual(dest_img.parent, dest_md.parent)

    def test_sidecar_has_relative_image_link(self):
        result = self._run(_good_response("development", "python"))
        content = Path(result["dest_sidecar"]).read_text(encoding="utf-8")
        # Relative link: ![stem](filename.png) — no directory component
        self.assertIn("![shot](shot.png)", content)

    def test_sidecar_has_frontmatter(self):
        result = self._run(_good_response("development", "python"))
        content = Path(result["dest_sidecar"]).read_text(encoding="utf-8")
        self.assertTrue(content.startswith("---"))
        self.assertIn('main_category: "development"', content)
        self.assertIn('sub_category: "python"', content)
        self.assertIn('source: "shot.png"', content)
        self.assertIn('model: "gpt-5.4"', content)

    def test_sidecar_has_description(self):
        desc = "The user is editing a Python script."
        result = self._run(_good_response(desc=desc))
        content = Path(result["dest_sidecar"]).read_text(encoding="utf-8")
        self.assertIn(desc, content)

    def test_others_main_goes_to_others_dir(self):
        result = self._run(_good_response("others", None))
        dest = Path(result["dest_image"])
        self.assertIn("others", dest.parts)

    def test_no_sub_dir_when_sub_is_none(self):
        result = self._run(_good_response("communication", None))
        dest = Path(result["dest_image"])
        # Path should be output/communication/shot.png — no extra subdir
        self.assertEqual(dest.parent.name, "communication")

    def test_sub_category_dir_created(self):
        result = self._run(_good_response("development", "vscode"))
        dest = Path(result["dest_image"])
        self.assertEqual(dest.parent.name, "vscode")
        self.assertEqual(dest.parent.parent.name, "development")


class TestProcessImageFailures(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.watch = self.tmp / "watch"
        self.watch.mkdir()
        self.output = self.tmp / "output"
        self.output.mkdir()
        self.image = self.watch / "shot.png"
        self.image.write_bytes(b"fake-png")
        self.config = _make_config(self.output)
        import logging
        self.log = logging.getLogger("test")

    def _run(self, mock_result=None, side_effect=None):
        with patch("subprocess.run",
                   return_value=mock_result,
                   side_effect=side_effect) as _:
            from analyzer import process_image
            return process_image(self.image, self.config, {}, self.log)

    def test_returns_none_on_nonzero_returncode(self):
        result = self._run(_mock_result(returncode=1, stderr="error"))
        self.assertIsNone(result)

    def test_returns_none_on_timeout(self):
        result = self._run(
            side_effect=subprocess.TimeoutExpired(cmd="copilot", timeout=30)
        )
        self.assertIsNone(result)

    def test_returns_none_when_json_unparseable(self):
        result = self._run(_mock_result(stdout="Sorry, I cannot analyze this."))
        self.assertIsNone(result)

    def test_image_not_moved_on_failure(self):
        self._run(_mock_result(returncode=1, stderr="error"))
        self.assertTrue(self.image.exists(), "Image should stay in watch_dir on failure")


class TestJsonExtraction(unittest.TestCase):
    """Test that _extract_json handles all LLM output variations."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.output = self.tmp / "output"
        self.output.mkdir()
        self.image = self.tmp / "shot.png"
        self.image.write_bytes(b"fake-png")
        self.config = _make_config(self.output)
        import logging
        self.log = logging.getLogger("test")

    def _run_with_stdout(self, stdout):
        with patch("subprocess.run", return_value=_mock_result(stdout=stdout)):
            from analyzer import process_image
            return process_image(self.image, self.config, {}, self.log)

    def test_parses_clean_single_line_json(self):
        result = self._run_with_stdout(_good_response())
        self.assertIsNotNone(result)
        self.assertEqual(result["main_category"], "development")

    def test_parses_json_with_surrounding_text(self):
        stdout = 'Here is my analysis:\n' + _good_response() + '\nLet me know if helpful.'
        result = self._run_with_stdout(stdout)
        self.assertIsNotNone(result)

    def test_parses_json_in_markdown_code_fence(self):
        stdout = "```json\n" + _good_response() + "\n```"
        result = self._run_with_stdout(stdout)
        self.assertIsNotNone(result)

    def test_parses_json_in_plain_code_fence(self):
        stdout = "```\n" + _good_response() + "\n```"
        result = self._run_with_stdout(stdout)
        self.assertIsNotNone(result)

    def test_returns_none_for_completely_garbled_output(self):
        result = self._run_with_stdout("申し訳ありませんが、画像を分析できません。")
        self.assertIsNone(result)

    def test_handles_null_sub_category(self):
        stdout = json.dumps({"main_category": "others", "sub_category": None,
                             "description": "Unclear image."})
        result = self._run_with_stdout(stdout)
        self.assertIsNotNone(result)
        self.assertIsNone(result["sub_category"])


class TestSanitizeName(unittest.TestCase):
    """Test path-safety sanitization of LLM-generated category names."""

    def _sanitize(self, name):
        from analyzer import _sanitize_name
        return _sanitize_name(name)

    def test_lowercase_hyphen_passthrough(self):
        self.assertEqual(self._sanitize("ai-tools"), "ai-tools")

    def test_spaces_become_hyphens(self):
        self.assertEqual(self._sanitize("social media"), "social-media")

    def test_uppercase_lowercased(self):
        self.assertEqual(self._sanitize("Development"), "development")

    def test_path_traversal_stripped(self):
        result = self._sanitize("../../etc/passwd")
        self.assertNotIn("..", result)
        self.assertNotIn("/", result)

    def test_backslash_stripped(self):
        result = self._sanitize("foo\\bar")
        self.assertNotIn("\\", result)

    def test_empty_result_falls_back_to_others(self):
        self.assertEqual(self._sanitize("...///"), "others")

    def test_collapses_multiple_hyphens(self):
        result = self._sanitize("a--b---c")
        self.assertNotIn("--", result)


class TestFilenameCollision(unittest.TestCase):
    """When destination file already exists, append _1, _2, etc."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.output = self.tmp / "output"
        self.output.mkdir()
        self.config = _make_config(self.output)
        import logging
        self.log = logging.getLogger("test")

    def test_appends_suffix_on_collision(self):
        watch = self.tmp / "watch"
        watch.mkdir()

        # Pre-create the destination to force collision
        dest_dir = self.output / "development" / "python"
        dest_dir.mkdir(parents=True)
        (dest_dir / "shot.png").write_bytes(b"existing")
        (dest_dir / "shot.md").write_text("existing", encoding="utf-8")

        image = watch / "shot.png"
        image.write_bytes(b"new-data")

        with patch("subprocess.run", return_value=_mock_result(stdout=_good_response())):
            from analyzer import process_image
            result = process_image(image, self.config, {}, self.log)

        self.assertIsNotNone(result)
        dest = Path(result["dest_image"])
        self.assertNotEqual(dest.name, "shot.png", "Should not overwrite existing file")
        self.assertTrue(dest.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
