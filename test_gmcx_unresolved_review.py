import unittest
from gmcx_unresolved_review import judge, report


def cue(t):
    return {
        "king_entry_seconds": t,
        "caption_onset_seconds": t + 2,
        "delay_seconds": 2,
        "king_warm_before": 0.02,
        "king_warm_entry": 0.22,
        "caption_dark_before": 0.07,
        "caption_dark_onset": 0.55,
        "caption_bright_onset": 0.05,
    }


class CandidateReviewTests(unittest.TestCase):
    def test_single_visual_hit_is_never_confirmed(self):
        hit = judge(3480, 100, [cue(3487)])
        self.assertEqual(hit["status"], "strong_visual_candidate_requires_audio_and_playback")
        self.assertEqual(hit["proposed_seconds"], 3487)
        self.assertNotIn("confirmed", hit)

    def test_multiple_distinct_openings_are_ambiguous(self):
        self.assertEqual(judge(3480, 100, [cue(3486), cue(3510)])["status"], "multiple_strong_visual_intros")

    def test_far_or_missing_cues_not_published(self):
        self.assertEqual(judge(3480, 100, [cue(3999)])["status"], "no_visual_opening_cue")
        self.assertEqual(judge(3480, 100, [])["status"], "no_visual_opening_cue")

    def test_weak_eyecatch_is_rejected(self):
        weak = cue(3414.5)
        weak["king_warm_before"] = 0.1915
        weak["king_warm_entry"] = 0.2231
        self.assertEqual(judge(3480, 130, [weak])["status"], "no_strong_visual_intro")

    def test_unavailable_sources_are_skipped(self):
        result = report(
            [{"vod_id": "5847ae05-893e-4ae8-986e-bf0abf888ecf",
              "tvg_id": "kick.gccx2", "playable": False,
              "source_url": "https://example.com/not-live.m3u8",
              "duration_seconds": 131723, "ready_for_publish": False}],
            targets=[("5847ae05", 3480, 100, "test")],
            detector=lambda *_: self.fail("must not call remote scanner")
        )
        self.assertEqual(result["results"][0]["status"], "source_unavailable")


if __name__ == "__main__":
    unittest.main()
