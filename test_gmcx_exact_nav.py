"""GCCX programme boundaries: frame-observed start snaps a nearby navigation cut only."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gmcx_exact_nav import snap_verified_starts, validated_starts
from gmcx_long_nav import time_slices
from gmcx_continuity import grouped_slices


class ExactNavTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.file = Path(self.tmp.name) / "boundaries.json"
        self.vod = {
            "vod_id": "example-long-gccx-vod",
            "source_url": "https://example.invalid/recording/master.m3u8",
            "duration_seconds": 172798,
        }
        self.entry = {
            "source_vod_id": self.vod["vod_id"],
            "source_url": self.vod["source_url"],
            "source_duration_seconds": 172798,
            "start_seconds": 59152,
            "start_uncertainty_seconds": 2,
            "kind": "programme_start",
            "confidence": "video_intro_observed_episode_end_unverified",
        }

    def write(self):
        self.file.write_text(
            json.dumps({"schema_version": 1, "boundaries": [self.entry]}),
            encoding="utf-8",
        )

    def test_observed_start_snaps_exactly(self):
        self.write()
        starts = validated_starts(self.vod, 52213, 172795, self.file)
        self.assertEqual(starts, [59152])
        old = time_slices(52213, 172795)
        new = snap_verified_starts(old, starts)
        self.assertEqual(new[1], (55693, 59152))
        self.assertEqual(new[2], (59152, 62653))
        self.assertEqual(len(new), len(old))
        self.assertEqual(new[0][0], 52213)
        self.assertEqual(new[-1][1], 172795)
        self.assertTrue(all(a[1] == b[0] for a,b in zip(new, new[1:])))

    def test_mismatched_source_ignored(self):
        self.write()
        bad = dict(self.vod, source_url="https://example.invalid/another.m3u8")
        self.assertEqual(validated_starts(bad, 52213, 172795, self.file), [])
        bad = dict(self.vod, duration_seconds=173000)
        self.assertEqual(validated_starts(bad, 52213, 172795, self.file), [])

    def test_never_guess_end_from_three_hour_name(self):
        old = time_slices(52213, 172795)
        new = snap_verified_starts(old, [59152])
        self.assertNotIn(59152 + 10800, [end for _,end in new])
        self.assertEqual(new[-1][1], 172795)

    def test_unsafe_far_boundary_does_not_shift(self):
        old = time_slices(52213, 172795)
        self.assertEqual(snap_verified_starts(old, [60000]), old)

    def test_group_frame_anchor_inside_snapped_clip(self):
        self.write()
        spans = snap_verified_starts(time_slices(52213, 172795), [59152])
        group = {
            "group_id": "special",
            "source_vod_id": self.vod["vod_id"],
            "source_url": self.vod["source_url"],
            "start_seconds": 59152,
            "end_seconds": 90493,
            "title": "GCCX 生放送",
            "confidence": "video_anchored_continuity_estimate",
            "evidence_anchor_starts": [59173, 62653],
        }
        config = Path(self.tmp.name) / "groups.json"
        config.write_text(
            json.dumps({"schema_version": 1, "groups": [group]}),
            encoding="utf-8",
        )
        observed = {
            (self.vod["vod_id"],59173): ("特番冒頭",None),
            (self.vod["vod_id"],62653): ("本編",None),
        }
        got = grouped_slices(self.vod, spans, observed, config)
        self.assertEqual(got[59152]["part"], 1)
        self.assertTrue(got[59152]["anchor"])
        self.assertEqual(got[62653]["part"], 2)


if __name__ == "__main__":
    unittest.main()
