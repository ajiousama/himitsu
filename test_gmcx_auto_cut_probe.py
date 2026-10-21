#!/usr/bin/env python3
"""Offline regression tests; no network, no published files modified."""
import unittest
from unittest.mock import patch

from gmcx_auto_cut_probe import find_candidate, review_group


def cue(at):
    return {
        "king_entry_seconds": at,
        "caption_onset_seconds": at + 2,
        "king_warm_before": 0.003,
        "king_warm_entry": 0.02,
        "caption_dark_before": 0.2,
        "caption_dark_onset": 0.6,
        "caption_bright_onset": 0.04,
    }


def bundle(with_anchor=True):
    episodes = [
        {"kind": "episode", "episode": 387, "start_seconds": 0, "method": "user-test-broadcast-order", "confidence": "provisional"},
        {"kind": "episode", "episode": 388, "start_seconds": 3488, "method": "manual-playback-confirmed" if with_anchor else "user-test-broadcast-order", "confidence": "confirmed" if with_anchor else "provisional"},
        {"kind": "episode", "episode": 389, "start_seconds": 6968, "method": "manual-playback-offset-propagated", "confidence": "provisional"},
        {"kind": "episode", "episode": 390, "start_seconds": 10448, "method": "manual-playback-offset-propagated", "confidence": "provisional"},
    ]
    return {
        "episode_start": 387,
        "episode_end": 390,
        "status": "ready",
        "vod_id": "example",
        "chapters": episodes,
    }


class AutoCutTests(unittest.TestCase):
    def test_unique_opening(self):
        with patch("gmcx_auto_cut_probe._scan_unclassified_king_title_sequence", return_value=[cue(3493)]):
            self.assertEqual("unique", find_candidate("example", 3488, 40)["state"])

    def test_ambiguous_openings_are_not_guessed(self):
        with patch("gmcx_auto_cut_probe._scan_unclassified_king_title_sequence", return_value=[cue(3493), cue(3505)]):
            self.assertEqual("ambiguous", find_candidate("example", 3488, 40)["state"])

    def test_anchor_calibrates_independent_episodes_and_remains_locked(self):
        expected = {3488: 3493, 6968: 6978, 10448: 10456}
        def detect(url, center, radius):
            return {"state": "unique", "candidate": cue(expected[center])}
        with patch("gmcx_auto_cut_probe._lowest_hls_variant", return_value="hls"), patch(
            "gmcx_auto_cut_probe.find_candidate", side_effect=detect
        ):
            result = review_group(bundle(), {"playable": True, "source_url": "hls"}, 40, 1)
        self.assertEqual("review_ready", result["status"])
        self.assertEqual(5, result["calibrated_cue_offset_seconds"])
        self.assertEqual({"389": 6973, "390": 10451}, result["recommended_starts"])
        self.assertEqual("manual-locked", result["rows"][0]["confidence"])
        self.assertFalse(result["publication_safe"])

    def test_no_anchor_never_auto_approves(self):
        with patch("gmcx_auto_cut_probe._lowest_hls_variant", return_value="hls"), patch(
            "gmcx_auto_cut_probe.find_candidate", return_value={"state": "unique", "candidate": cue(3493)}
        ):
            result = review_group(bundle(with_anchor=False), {"playable": True, "source_url": "hls"}, 40, 1)
        self.assertEqual("needs_reference", result["status"])
        self.assertEqual({}, result["recommended_starts"])
        self.assertFalse(result["publication_safe"])


if __name__ == "__main__":
    unittest.main()
