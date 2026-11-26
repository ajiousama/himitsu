"""Regression tests for HARUKA yovi trial frozen-stream protection."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import refresh_yovi_haruka as haruka


class HarukaRefreshSafetyTest(unittest.TestCase):
    def test_frozen_manifest_is_not_advanced(self):
        frozen = (23569086, "http://14.241.72.93:9394/stream/28/23569089.fplsegment.ts")
        self.assertFalse(haruka.has_advanced(frozen, frozen))
        self.assertFalse(haruka.has_advanced(None, frozen))

    def test_sequence_and_segment_must_both_progress(self):
        before = (10, "http://14.241.72.93:9394/stream/28/13.fplsegment.ts")
        after = (11, "http://14.241.72.93:9394/stream/28/14.fplsegment.ts")
        self.assertTrue(haruka.has_advanced(before, after))
        self.assertFalse(haruka.has_advanced(before, (11, before[1])))
        self.assertFalse(haruka.has_advanced(before, (10, after[1])))
        self.assertFalse(haruka.has_advanced(after, before))

    def test_updates_only_the_trial_block(self):
        original = (
            "#EXTM3U\n"
            '#EXTINF:-1 group-title="ABEMA系",Keep ABEMA\n'
            "https://example.net/abema.m3u8\n"
        )
        changed, kept = haruka.update_yovi(original, "http://14.241.72.93:9394", {28})
        self.assertEqual(kept, 0)
        self.assertIn("https://example.net/abema.m3u8", changed)
        self.assertIn("http://14.241.72.93:9394/stream/28.m3u8", changed)
        self.assertNotIn("/stream/4.m3u8", changed)
        later, kept = haruka.update_yovi(changed, "http://14.241.72.94:9394", set())
        self.assertEqual(kept, 1)
        self.assertEqual(later, changed)

    def test_recovered_bs_channels_in_trial_catalog(self):
        expected = {44: "BS日テレ", 40: "WOWOWライブ", 41: "WOWOWシネマ"}
        self.assertEqual(len(haruka.CHANNELS), 20)
        for number, name in expected.items():
            self.assertIn((number, name, {"BS日テレ": "BS日テレ_jp", "WOWOWライブ": "WOWOWライブ_jp", "WOWOWシネマ": "WOWOWシネマ_jp"}[name], "BS"), haruka.CHANNELS)
        sample = "#EXTM3U\\n#EXTINF:-1 group-title=\\\"ABEMA系\\\",KEEP\\nhttps://example.net/abema.m3u8\\n"
        block, _ = haruka.update_yovi(sample, "http://14.241.72.93:9394", set(expected))
        self.assertEqual(block.count('group-title="HARUKA試験 BS"'), 3)
        for number in expected:
            self.assertIn(f"/stream/{number}.m3u8", block)
        self.assertIn("https://example.net/abema.m3u8", block)

    def test_main_frozen_keeps_existing_playlist_unchanged(self):
        original = (
            "#EXTM3U\n"
            '#EXTINF:-1 group-title="ABEMA系",Keep ABEMA\n'
            "https://example.net/abema.m3u8\n"
        )
        initial, _ = haruka.update_yovi(original, "http://14.241.72.93:9394", {28})
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "yovi"
            target.write_text(initial, encoding="utf-8")
            frozen = (100, "http://14.241.72.93:9394/stream/28/100.fplsegment.ts")
            with (
                patch.object(haruka, "PLAYLIST", target),
                patch.object(haruka, "fetch_current_base", return_value="http://14.241.72.93:9394"),
                patch.object(haruka, "manifest_snapshot", return_value=frozen),
                patch.object(haruka.time, "sleep", return_value=None),
                patch("sys.argv", ["refresh_yovi_haruka.py"]),
            ):
                haruka.main()
            self.assertEqual(target.read_text(encoding="utf-8"), initial)


if __name__ == "__main__":
    unittest.main()
