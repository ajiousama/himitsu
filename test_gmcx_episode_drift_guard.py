"""Long GCCX live programmes suspend guesswork until video re-anchors the broadcast."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from gmcx_long_nav import chronological_title_hints, build_time_navigation_entries


class LongProgrammeGuardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.vod_id = "abcd1234-test-recording-2026"
        self.vod = {
            "vod_id": self.vod_id,
            "source_url": "https://example.invalid/recording/master.m3u8",
            "tvg_id": "kick.gccx2",
            "created_at": "2026-11-13T11:00:00+09:00",
            "duration_seconds": 8 * 3480,
            "ready_for_publish": True,
            "playable": True,
        }
        self.replay = self.root / "kick_replay.json"
        self.chapters = self.root / "kick_gmcx_chapters.json"
        self.rules = self.root / "rules.json"
        self.titles = self.root / "titles.json"
        self.replay.write_text(
            json.dumps({"vods": [self.vod]}), encoding="utf-8",
        )
        self.chapters.write_text(json.dumps({"results": [{
            "vod_id": self.vod_id, "status": "range_unknown", "chapters": []
        }]}), encoding="utf-8")
        self.rules.write_text(json.dumps({"schema_version":1,"rules":[{
            "source_vod_id": self.vod_id,
            "source_url": self.vod["source_url"],
            "nav_start_seconds": 0,
            "first_slot_index": 0,
            "first_episode": 90,
            "last_episode": 140,
            "confidence": "provisional_chronological_inference",
            "disable_episode_sequence_at_or_after_seconds": 10440,
            "post_special_label": "5時間生放送以降・通常回再開位置を確認中",
        }]}), encoding="utf-8")
        self.titles.write_text(json.dumps({
            str(i): f"ゲーム名{i}" for i in range(90,141)
        }), encoding="utf-8")

    def test_guesses_stop_at_special_and_do_not_resume_automatically(self):
        with patch("gmcx_long_nav.SEQUENCE_ESTIMATES", self.rules), \
             patch("gmcx_long_nav.EPISODE_TITLES", self.titles):
            hints = chronological_title_hints({"vods":[self.vod]})
        self.assertEqual(hints[(self.vod_id, 0)],(90,"ゲーム名90"))
        self.assertEqual(hints[(self.vod_id, 6960)],(92,"ゲーム名92"))
        for at in [10440,13920,17400,20880,24360]:
            self.assertEqual(hints[(self.vod_id,at)],
                             (None,"5時間生放送以降・通常回再開位置を確認中"))

    def test_playlist_explains_suspension_instead_of_inventing_numbers(self):
        with patch("gmcx_long_nav.SEQUENCE_ESTIMATES", self.rules), \
             patch("gmcx_long_nav.EPISODE_TITLES", self.titles):
            entries = build_time_navigation_entries(self.replay,self.chapters)
        self.assertEqual(len(entries),8)
        self.assertIn("ゲーム名92",entries[2][0])
        self.assertIn("特番をまたぐ話数推定を停止",entries[3][0])
        for inf,_ in entries[3:]:
            self.assertNotIn("ゲーム名93",inf)
            self.assertNotIn("放送順・位置から仮推定",inf)
        self.assertTrue(all("duration=" in url for _,url in entries))


if __name__ == "__main__":
    unittest.main()
