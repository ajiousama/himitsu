import unittest
from unittest.mock import patch

from gmcx_intro_alignment_probe import inspect_seed


def match(shift, matched=True):
    return {"summary": {
        "status": "common_audio_detected" if matched else "not_confirmed",
        "relative_shift_seconds": shift,
        "coherent_windows": 3 if matched else 0,
        "mean_similarity": 0.82 if matched else None,
    }}


class IntroAlignmentTests(unittest.TestCase):
    def setUp(self):
        self.sources = [("source-a", object()), ("source-b", object())]
        self.target = object()

    def check(self, a, b, veto=None, vod_id="recording-xyz"):
        with patch("gmcx_intro_alignment_probe.match_pair", side_effect=[a, b]):
            return inspect_seed(3480, 3300, self.sources, self.target,
                                veto or [], vod_id)

    def test_independent_matches_are_candidates_not_episodes(self):
        result = self.check(match(180), match(182))
        self.assertEqual(result["status"], "two_source_audio_candidate_needs_video_review")
        self.assertEqual(result["candidate_seconds"], 3481)
        self.assertFalse(result["publish_as_episode"])

    def test_single_audio_match_is_insufficient(self):
        result = self.check(match(180), match(180, matched=False))
        self.assertEqual(result["status"], "insufficient_independent_audio_evidence")
        self.assertFalse(result["publish_as_episode"])

    def test_source_disagreement_is_not_accepted(self):
        result = self.check(match(180), match(195))
        self.assertEqual(result["status"], "audio_references_disagree")
        self.assertFalse(result["publish_as_episode"])

    def test_old_recording_within_veto_is_not_accepted(self):
        result = self.check(match(180), match(181), [
            {"vod_prefix": "recording-", "seconds": 3481,
             "context": "inside unrelated interview"}
        ], "recording-xyz")
        self.assertEqual(result["status"], "video_review_veto")
        self.assertFalse(result["publish_as_episode"])

    def test_outside_seed_guard_is_not_accepted(self):
        result = self.check(match(360), match(359))
        self.assertEqual(result["status"], "insufficient_independent_audio_evidence")
        self.assertFalse(result["publish_as_episode"])


if __name__ == "__main__":
    unittest.main()
