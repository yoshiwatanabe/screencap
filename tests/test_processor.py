"""Tests for processor.py — written BEFORE implementation (TDD)."""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

EXTENSIONS = [".png", ".jpg", ".jpeg", ".bmp"]


def make_image(directory: Path, name: str, content: bytes = b"fake-png-data") -> Path:
    """Write a fake image file and return its path."""
    p = directory / name
    p.write_bytes(content)
    return p


def age_file(path: Path, minutes_ago: float) -> None:
    """Set a file's mtime to N minutes in the past."""
    t = time.time() - (minutes_ago * 60)
    os.utime(path, (t, t))


class TestLoadState(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.state_path = self.tmp / "state.json"

    def test_returns_empty_dict_when_absent(self):
        from processor import load_state
        self.assertEqual(load_state(self.state_path), {})

    def test_loads_existing_state(self):
        data = {"shot.png": {"hash": "abc", "main_category": "development"}}
        self.state_path.write_text(json.dumps(data), encoding="utf-8")
        from processor import load_state
        self.assertEqual(load_state(self.state_path), data)

    def test_returns_dict_type(self):
        from processor import load_state
        self.assertIsInstance(load_state(self.state_path), dict)


class TestSaveState(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.state_path = self.tmp / "state.json"

    def test_saves_and_reloads(self):
        from processor import save_state, load_state
        state = {"shot.png": {"hash": "abc"}}
        save_state(self.state_path, state)
        self.assertEqual(load_state(self.state_path), state)

    def test_no_temp_file_left_after_save(self):
        from processor import save_state
        save_state(self.state_path, {})
        self.assertEqual(list(self.tmp.glob("*.tmp")), [])

    def test_overwrites_existing(self):
        from processor import save_state, load_state
        self.state_path.write_text(json.dumps({"old": {}}), encoding="utf-8")
        save_state(self.state_path, {"new": {}})
        self.assertNotIn("old", load_state(self.state_path))


class TestFileHash(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_returns_64_char_hex_string(self):
        from processor import file_hash
        p = self.tmp / "test.png"
        p.write_bytes(b"content")
        result = file_hash(p)
        self.assertEqual(len(result), 64)
        self.assertTrue(all(c in "0123456789abcdef" for c in result))

    def test_same_content_same_hash(self):
        from processor import file_hash
        a = self.tmp / "a.png"
        b = self.tmp / "b.png"
        a.write_bytes(b"same")
        b.write_bytes(b"same")
        self.assertEqual(file_hash(a), file_hash(b))

    def test_different_content_different_hash(self):
        from processor import file_hash
        a = self.tmp / "a.png"
        b = self.tmp / "b.png"
        a.write_bytes(b"aaa")
        b.write_bytes(b"bbb")
        self.assertNotEqual(file_hash(a), file_hash(b))


class TestGetReady(unittest.TestCase):

    def setUp(self):
        self.watch = Path(tempfile.mkdtemp())

    def test_returns_old_enough_files(self):
        f = make_image(self.watch, "old.png")
        age_file(f, minutes_ago=10)
        from processor import get_ready
        result = get_ready(self.watch, EXTENSIONS, max_age_minutes=5, state={})
        self.assertIn(f, result)

    def test_excludes_too_young_files(self):
        f = make_image(self.watch, "new.png")
        age_file(f, minutes_ago=1)
        from processor import get_ready
        result = get_ready(self.watch, EXTENSIONS, max_age_minutes=5, state={})
        self.assertNotIn(f, result)

    def test_excludes_already_in_state(self):
        f = make_image(self.watch, "done.png")
        age_file(f, minutes_ago=10)
        state = {"done.png": {"hash": "x", "main_category": "development"}}
        from processor import get_ready
        result = get_ready(self.watch, EXTENSIONS, max_age_minutes=5, state=state)
        self.assertNotIn(f, result)

    def test_excludes_wrong_extension(self):
        f = make_image(self.watch, "doc.pdf")
        age_file(f, minutes_ago=10)
        from processor import get_ready
        result = get_ready(self.watch, EXTENSIONS, max_age_minutes=5, state={})
        self.assertNotIn(f, result)

    def test_uppercase_extension_matched_case_insensitively(self):
        f = make_image(self.watch, "shot.PNG")
        age_file(f, minutes_ago=10)
        from processor import get_ready
        result = get_ready(self.watch, [".png"], max_age_minutes=5, state={})
        self.assertIn(f, result)

    def test_includes_all_supported_extensions(self):
        files = []
        for ext in EXTENSIONS:
            f = make_image(self.watch, f"shot{ext}")
            age_file(f, minutes_ago=10)
            files.append(f)
        from processor import get_ready
        result = get_ready(self.watch, EXTENSIONS, max_age_minutes=5, state={})
        for f in files:
            self.assertIn(f, result)

    def test_does_not_recurse_into_subdirs(self):
        subdir = self.watch / "Archive"
        subdir.mkdir()
        f = make_image(subdir, "nested.png")
        age_file(f, minutes_ago=10)
        from processor import get_ready
        result = get_ready(self.watch, EXTENSIONS, max_age_minutes=5, state={})
        self.assertNotIn(f, result)

    def test_returns_oldest_first(self):
        f1 = make_image(self.watch, "newer.png", b"a")
        f2 = make_image(self.watch, "older.png", b"b")
        age_file(f1, minutes_ago=10)
        age_file(f2, minutes_ago=20)
        from processor import get_ready
        result = get_ready(self.watch, EXTENSIONS, max_age_minutes=5, state={})
        self.assertEqual(result[0], f2)
        self.assertEqual(result[1], f1)

    def test_returns_empty_list_for_empty_dir(self):
        from processor import get_ready
        result = get_ready(self.watch, EXTENSIONS, max_age_minutes=5, state={})
        self.assertEqual(result, [])

    def test_exact_boundary_age_is_included(self):
        """File exactly at max_age_minutes threshold is ready."""
        f = make_image(self.watch, "boundary.png")
        age_file(f, minutes_ago=5)
        from processor import get_ready
        result = get_ready(self.watch, EXTENSIONS, max_age_minutes=5, state={})
        self.assertIn(f, result)


class TestMarkProcessed(unittest.TestCase):

    def test_adds_entry_to_state(self):
        from processor import mark_processed
        state = {}
        mark_processed(
            state,
            original_name="shot.png",
            hash_val="abc123",
            main_cat="development",
            sub_cat="python",
            dest_image=Path("C:/out/development/python/shot.png"),
            dest_sidecar=Path("C:/out/development/python/shot.md"),
        )
        self.assertIn("shot.png", state)

    def test_entry_has_required_fields(self):
        from processor import mark_processed
        state = {}
        mark_processed(
            state,
            original_name="shot.png",
            hash_val="abc123",
            main_cat="development",
            sub_cat="python",
            dest_image=Path("C:/out/shot.png"),
            dest_sidecar=Path("C:/out/shot.md"),
        )
        entry = state["shot.png"]
        for field in ("hash", "processed_at", "main_category", "sub_category",
                      "dest_image", "dest_sidecar"):
            self.assertIn(field, entry, f"Missing field: {field}")

    def test_sub_cat_none_stored_as_none(self):
        from processor import mark_processed
        state = {}
        mark_processed(state, "shot.png", "abc", "others", None,
                       Path("C:/out/shot.png"), Path("C:/out/shot.md"))
        self.assertIsNone(state["shot.png"]["sub_category"])


class TestPruneState(unittest.TestCase):

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_removes_entry_for_missing_dest_image(self):
        from processor import prune_state
        state = {
            "gone.png": {"dest_image": str(self.tmp / "nonexistent.png")},
        }
        removed = prune_state(state)
        self.assertNotIn("gone.png", state)
        self.assertEqual(removed, 1)

    def test_keeps_entry_for_existing_dest_image(self):
        existing = self.tmp / "exists.png"
        existing.write_bytes(b"data")
        from processor import prune_state
        state = {"exists.png": {"dest_image": str(existing)}}
        removed = prune_state(state)
        self.assertIn("exists.png", state)
        self.assertEqual(removed, 0)

    def test_returns_count_of_removed(self):
        from processor import prune_state
        state = {
            "a.png": {"dest_image": str(self.tmp / "nope_a.png")},
            "b.png": {"dest_image": str(self.tmp / "nope_b.png")},
        }
        removed = prune_state(state)
        self.assertEqual(removed, 2)

    def test_empty_state_returns_zero(self):
        from processor import prune_state
        self.assertEqual(prune_state({}), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
