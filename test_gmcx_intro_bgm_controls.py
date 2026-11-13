import unittest
from gmcx_intro_bgm_controls import SOURCES, judge


def pair_result(positive=True, negative_hit=False):
    out = {"positive_nov09_evening|positive_nov07_morning": {
        "summary": {"status": "common_audio_detected" if positive else "not_confirmed"}
    }}
    for left in ("positive_nov09_evening", "positive_nov07_morning"):
        for right in ("negative_nov11_evening", "negative_nov09_morning"):
            out[f"{left}|{right}"] = {
                "summary": {"status": "common_audio_detected" if negative_hit else "not_confirmed"}
            }
    return out


class IntroControlsTests(unittest.TestCase):
    def test_positive_agrees_negative_controls_disagree_is_still_review_only(self):
        result = judge(pair_result(), set(SOURCES))
        self.assertEqual(result["status"], "candidate_intro_fingerprint_needs_video_onset_verification")
        self.assertFalse(result["usable_for_publication"])
        self.assertTrue(result["negative_controls_complete"])

    def test_false_positive_negative_control_blocks_use(self):
        result = judge(pair_result(negative_hit=True), set(SOURCES))
        self.assertEqual(result["status"], "matched_audio_is_not_specific_to_opening")
        self.assertFalse(result["usable_for_publication"])

    def test_no_two_positive_match_cannot_claim_intro(self):
        result = judge(pair_result(positive=False), set(SOURCES))
        self.assertEqual(result["status"], "no_independently_verified_common_intro")
        self.assertFalse(result["usable_for_publication"])

    def test_missing_negative_control_is_fail_closed(self):
        result = judge(pair_result(), {"positive_nov09_evening", "positive_nov07_morning"})
        self.assertEqual(result["status"], "insufficient_sources")
        self.assertFalse(result["usable_for_publication"])

    def test_missing_comparison_is_not_positive(self):
        result = judge({"positive_nov09_evening|positive_nov07_morning": {
            "summary": {"status": "common_audio_detected"}
        }}, set(SOURCES))
        self.assertEqual(result["status"], "no_independently_verified_common_intro")
        self.assertFalse(result["negative_controls_complete"])
        self.assertFalse(result["usable_for_publication"])


if __name__ == "__main__":
    unittest.main()
