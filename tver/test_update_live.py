"""Deadline regression tests for ephemeral TVer real-time programmes."""
import unittest
from unittest.mock import patch
from tver.update_live import is_on_air, is_not_finished, normalize


class TVerExpiryTests(unittest.TestCase):
    def test_finished_programme_removed_at_exact_end(self):
        row = {"start_at": 100, "end_at": 200}
        self.assertTrue(is_on_air(row, 199))
        self.assertFalse(is_on_air(row, 200))
        self.assertFalse(is_not_finished(row, 200))

    def test_upcoming_not_published_but_stays_on_schedule(self):
        row = {"start_at": 300, "end_at": 400}
        self.assertFalse(is_on_air(row, 200))
        self.assertTrue(is_not_finished(row, 200))

    def test_always_on_feed_without_end_is_preserved(self):
        self.assertTrue(is_on_air({"start_at": 1, "end_at": None}, 500))

    def test_live_catalog_accepts_prior_cached_entries(self):
        rows = normalize([{"id": "le123abc", "title": "TVer test", "start_at": 100, "end_at": 200}])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["end_at"], 200)
        self.assertFalse(is_on_air(rows[0], 200))


if __name__ == "__main__":
    unittest.main()
