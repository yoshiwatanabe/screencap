"""Tests for categories.py — written BEFORE implementation (TDD)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestLoadCategories(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cats_path = self.tmp / "categories.json"

    def test_returns_empty_dict_when_file_absent(self):
        from categories import load_categories
        result = load_categories(self.cats_path)
        self.assertEqual(result, {})

    def test_loads_existing_categories(self):
        data = {"development": ["python", "vscode"], "communication": ["email"]}
        self.cats_path.write_text(json.dumps(data), encoding="utf-8")
        from categories import load_categories
        result = load_categories(self.cats_path)
        self.assertEqual(result, data)

    def test_returns_dict_not_other_type(self):
        self.cats_path.write_text(json.dumps({}), encoding="utf-8")
        from categories import load_categories
        self.assertIsInstance(load_categories(self.cats_path), dict)


class TestSaveCategories(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.cats_path = self.tmp / "categories.json"

    def test_saves_and_reloads_correctly(self):
        from categories import save_categories, load_categories
        cats = {"development": ["python"], "social-media": ["facebook"]}
        save_categories(self.cats_path, cats)
        result = load_categories(self.cats_path)
        self.assertEqual(result, cats)

    def test_no_temp_file_left_after_save(self):
        from categories import save_categories
        save_categories(self.cats_path, {"a": ["b"]})
        tmp_files = list(self.tmp.glob("*.tmp"))
        self.assertEqual(tmp_files, [], f"Temp file(s) left: {tmp_files}")

    def test_overwrites_existing_file(self):
        from categories import save_categories, load_categories
        self.cats_path.write_text(json.dumps({"old": ["data"]}), encoding="utf-8")
        save_categories(self.cats_path, {"new": ["data"]})
        self.assertNotIn("old", load_categories(self.cats_path))


class TestFormatTree(unittest.TestCase):

    def test_empty_dict_shows_only_others(self):
        from categories import format_tree
        result = format_tree({})
        self.assertIn("others", result)

    def test_others_always_last(self):
        from categories import format_tree
        result = format_tree({"development": ["python"]})
        lines = result.strip().splitlines()
        self.assertEqual(lines[-1].strip(), "others")

    def test_main_category_at_indent_zero(self):
        from categories import format_tree
        result = format_tree({"development": ["python"]})
        self.assertIn("development", result)
        # main category must not be indented
        for line in result.splitlines():
            if "development" in line:
                self.assertFalse(line.startswith(" "), f"Expected no indent: {line!r}")

    def test_sub_category_indented(self):
        from categories import format_tree
        result = format_tree({"development": ["python", "vscode"]})
        for line in result.splitlines():
            if "python" in line or "vscode" in line:
                self.assertTrue(line.startswith(" "), f"Expected indent: {line!r}")

    def test_multiple_mains_and_subs(self):
        from categories import format_tree
        cats = {
            "development": ["python", "vscode"],
            "communication": ["email", "slack"],
        }
        result = format_tree(cats)
        for name in ["development", "python", "vscode", "communication", "email", "slack", "others"]:
            self.assertIn(name, result)

    def test_main_with_empty_sub_list(self):
        from categories import format_tree
        result = format_tree({"development": []})
        self.assertIn("development", result)

    def test_others_not_duplicated_when_in_input(self):
        """others is implicit — even if passed in cats, it should appear only once."""
        from categories import format_tree
        result = format_tree({"others": ["misc"]})
        self.assertEqual(result.count("others"), 1)


class TestEnsureCategory(unittest.TestCase):

    def test_adds_new_main_and_sub(self):
        from categories import ensure_category
        cats = {}
        modified = ensure_category(cats, "development", "python")
        self.assertTrue(modified)
        self.assertIn("development", cats)
        self.assertIn("python", cats["development"])

    def test_adds_sub_to_existing_main(self):
        from categories import ensure_category
        cats = {"development": ["python"]}
        modified = ensure_category(cats, "development", "vscode")
        self.assertTrue(modified)
        self.assertIn("vscode", cats["development"])
        self.assertIn("python", cats["development"])

    def test_returns_false_when_already_exists(self):
        from categories import ensure_category
        cats = {"development": ["python"]}
        modified = ensure_category(cats, "development", "python")
        self.assertFalse(modified)

    def test_idempotent(self):
        from categories import ensure_category
        cats = {}
        ensure_category(cats, "development", "python")
        ensure_category(cats, "development", "python")
        self.assertEqual(cats["development"].count("python"), 1)

    def test_adds_main_without_sub(self):
        from categories import ensure_category
        cats = {}
        modified = ensure_category(cats, "communication", None)
        self.assertTrue(modified)
        self.assertIn("communication", cats)

    def test_sub_none_on_existing_main_returns_false(self):
        from categories import ensure_category
        cats = {"communication": []}
        modified = ensure_category(cats, "communication", None)
        self.assertFalse(modified)

    def test_others_never_written_to_dict(self):
        from categories import ensure_category
        cats = {}
        ensure_category(cats, "others", None)
        self.assertNotIn("others", cats)

    def test_others_with_sub_never_written(self):
        from categories import ensure_category
        cats = {}
        ensure_category(cats, "others", "misc")
        self.assertNotIn("others", cats)

    def test_new_main_only_returns_true(self):
        from categories import ensure_category
        cats = {"development": ["python"]}
        modified = ensure_category(cats, "social-media", None)
        self.assertTrue(modified)
        self.assertIn("social-media", cats)


if __name__ == "__main__":
    unittest.main(verbosity=2)
