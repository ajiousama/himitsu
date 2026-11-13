#!/usr/bin/env python3
"""Regression tests: provisional GCCX time navigation must not invent episodes."""
import json
import tempfile
import unittest
from pathlib import Path

from gmcx_long_nav import build_time_navigation_entries, time_slices


def vod(vod_id, title="ゲームセンターCX", duration=131723, **kwargs):
    return {
        "vod_id": vod_id,
        "title": title,
        "tvg_id": "kick.gccx2",
        "created_at": "2026-11-11T18:09:00+09:00",
        "duration_seconds": duration,
        "playable": True,
        "ready_for_publish": True,
        **kwargs,
    }


class LongNavTests(unittest.TestCase):
    def test_slices_cover_source_without_gaps(self):
        for begin, stop in [(0, 131723), (0, 29908), (0, 172799), (52213, 172795)]:
            parts = time_slices(begin, stop)
            self.assertGreater(len(parts), 1)
            self.assertEqual(parts[0][0], begin)
            self.assertEqual(parts[-1][1], stop)
            self.assertTrue(all(a < b for a, b in parts))
            self.assertTrue(all(parts[i][1] == parts[i + 1][0] for i in range(len(parts) - 1)))

    def test_short_and_tiny_tail(self):
        self.assertEqual(time_slices(0, 3500), [])
        self.assertEqual(time_slices(0, 2 * 3600)[-1][1], 7200)
        parts = time_slices(0, 2 * 3480 + 120)
        self.assertEqual(len(parts), 2)
        self.assertEqual(parts[-1], (3480, 7080))

    def test_unknown_is_navigation_only_and_source_safe(self):
        with tempfile.TemporaryDirectory() as d:
            replay, chapters = Path(d) / "r.json", Path(d) / "c.json"
            ident = "5847ae05-893e-4ae8-986e-bf0abf888ecf"
            replay.write_text(json.dumps({"vods": [
                vod(ident),
                vod("de35f5fe-ef68-477c-b44e-d591632facf8", tvg_id="kick.nogizaka"),
                vod("deadbeef-ef68-477c-b44e-d591632facf8", ready_for_publish=False),
            ]}), encoding="utf-8")
            chapters.write_text(json.dumps({"results": [
                {"vod_id": ident, "status": "range_unknown", "chapters": []},
            ]}), encoding="utf-8")
            entries = build_time_navigation_entries(replay, chapters)
            self.assertEqual(len(entries), 38)
            self.assertTrue(all("話数未確認" in inf for inf, _ in entries))
            self.assertTrue(all("kick.gmcx.nav." in inf for inf, _ in entries))
            self.assertTrue(all("vod=" + ident in url for _, url in entries))
            self.assertTrue(all("duration=" in url and "&start=" in url for _, url in entries))
            self.assertEqual(len({url for _, url in entries}), len(entries))

    def test_only_unclassified_tail_is_split(self):
        with tempfile.TemporaryDirectory() as d:
            replay, chapters = Path(d) / "r.json", Path(d) / "c.json"
            ident = "df1386fd-4bd1-41ae-ac64-743ff49a838f"
            replay.write_text(json.dumps({"vods": [vod(ident, duration=172798)]}), encoding="utf-8")
            chapters.write_text(json.dumps({"results": [{
                "vod_id": ident, "status": "ready", "partial": True,
                "chapters": [
                    {"kind": "episode", "start_seconds": 0, "stop_seconds": 52213},
                    {"kind": "special", "title": "長時間特別編以降（未分割・確認待ち）",
                     "confidence": "unconfirmed", "start_seconds": 52213, "stop_seconds": 172795},
                ],
            }]}), encoding="utf-8")
            entries = build_time_navigation_entries(replay, chapters)
            self.assertEqual(len(entries), 35)
            self.assertIn("&start=52213&duration=3480", entries[0][1])
            self.assertTrue(all("後半未分類" in inf for inf, _ in entries))

    def test_confirmed_chapters_are_never_reprocessed(self):
        with tempfile.TemporaryDirectory() as d:
            replay, chapters = Path(d) / "r.json", Path(d) / "c.json"
            ident = "df1386fd-4bd1-41ae-ac64-743ff49a838f"
            replay.write_text(json.dumps({"vods": [vod(ident, duration=172798)]}), encoding="utf-8")
            chapters.write_text(json.dumps({"results": [{
                "vod_id": ident, "status": "ready", "partial": False,
                "chapters": [{"kind": "episode", "start_seconds": 0, "stop_seconds": 172798}],
            }]}), encoding="utf-8")
            self.assertEqual(build_time_navigation_entries(replay, chapters), [])


if __name__ == "__main__":
    unittest.main()
