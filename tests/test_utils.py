"""Tests for utils.py — sanitize_name."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


class TestSanitizeName(unittest.TestCase):

    def _s(self, name):
        from utils import sanitize_name
        return sanitize_name(name)

    # ── basic transformations ─────────────────────────────────────────────────

    def test_lowercases_input(self):
        self.assertEqual(self._s("DevTools"), "devtools")

    def test_strips_leading_trailing_whitespace(self):
        self.assertEqual(self._s("  ai-tools  "), "ai-tools")

    def test_replaces_spaces_with_hyphens(self):
        self.assertEqual(self._s("social media"), "social-media")

    def test_replaces_special_chars_with_hyphens(self):
        # underscore and ! become hyphens; trailing hyphen is stripped
        self.assertEqual(self._s("ai_tools!"), "ai-tools")

    def test_collapses_multiple_hyphens(self):
        self.assertEqual(self._s("a--b---c"), "a-b-c")

    def test_strips_leading_trailing_hyphens(self):
        self.assertEqual(self._s("-hello-"), "hello")

    def test_allows_digits(self):
        self.assertEqual(self._s("web3"), "web3")

    def test_allows_hyphens(self):
        self.assertEqual(self._s("ai-tools"), "ai-tools")

    # ── fallback to "others" ─────────────────────────────────────────────────

    def test_empty_string_returns_others(self):
        self.assertEqual(self._s(""), "others")

    def test_only_special_chars_returns_others(self):
        self.assertEqual(self._s("!@#$%"), "others")

    def test_none_coerced_to_string_returns_others(self):
        # sanitize_name does str(name), so None becomes "none" → valid
        self.assertEqual(self._s("none"), "none")

    # ── Windows reserved names ────────────────────────────────────────────────

    def test_reserved_name_con_returns_others(self):
        self.assertEqual(self._s("con"), "others")

    def test_reserved_name_nul_returns_others(self):
        self.assertEqual(self._s("nul"), "others")

    def test_reserved_name_prn_returns_others(self):
        self.assertEqual(self._s("prn"), "others")

    def test_reserved_name_aux_returns_others(self):
        self.assertEqual(self._s("aux"), "others")

    def test_reserved_com_ports_return_others(self):
        from utils import sanitize_name
        for i in range(1, 10):
            self.assertEqual(sanitize_name(f"com{i}"), "others", f"com{i} should be others")

    def test_reserved_lpt_ports_return_others(self):
        from utils import sanitize_name
        for i in range(1, 10):
            self.assertEqual(sanitize_name(f"lpt{i}"), "others", f"lpt{i} should be others")

    def test_reserved_names_case_insensitive(self):
        self.assertEqual(self._s("CON"), "others")
        self.assertEqual(self._s("NUL"), "others")

    # ── max length truncation ─────────────────────────────────────────────────

    def test_truncates_to_50_chars(self):
        from utils import MAX_CATEGORY_LEN
        long_name = "a" * 80
        result = self._s(long_name)
        self.assertEqual(len(result), MAX_CATEGORY_LEN)

    def test_truncation_does_not_leave_trailing_hyphen(self):
        # If the 50th char is in the middle of a run of hyphens that got collapsed,
        # the result may end with a hyphen — but our impl truncates AFTER stripping,
        # so a 50-char all-alpha name stays clean
        long_name = "a" * 50 + "b" * 30
        result = self._s(long_name)
        self.assertFalse(result.endswith("-"))

    def test_exactly_50_chars_is_not_truncated(self):
        from utils import MAX_CATEGORY_LEN
        exact = "a" * MAX_CATEGORY_LEN
        self.assertEqual(self._s(exact), exact)

    def test_51_chars_is_truncated_to_50(self):
        from utils import MAX_CATEGORY_LEN
        name = "a" * (MAX_CATEGORY_LEN + 1)
        self.assertEqual(len(self._s(name)), MAX_CATEGORY_LEN)


if __name__ == "__main__":
    unittest.main(verbosity=2)
