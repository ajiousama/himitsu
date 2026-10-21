#!/usr/bin/env python3
"""Offline tests: no network and no modifications to published VOD5."""
import unittest
import numpy as np
from gmcx_auto_cut_audio import (
    SEARCH_BEFORE, candidate_matches, consensus, fingerprint
)

class AudioReviewTests(unittest.TestCase):
    def test_repeating_audio_fingerprint_recovers_shift(self):
        rng = np.random.default_rng(42)
        anchor = rng.normal(size=(500, 32)).astype(np.float32)
        target = rng.normal(size=(1260, 32)).astype(np.float32)
        shift = 9
        start = (SEARCH_BEFORE + shift)*10
        target[start:start+len(anchor)] = anchor
        matches = candidate_matches(anchor, target)
        result = consensus(matches)
        self.assertEqual("candidate", result["status"])
        self.assertAlmostEqual(9.0, result["shift_seconds"], delta=0.15)
        self.assertGreaterEqual(result["strong_matches"], 3)

    def test_unrelated_audio_rejected(self):
        rng = np.random.default_rng(75)
        anchor = rng.normal(size=(500, 32)).astype(np.float32)
        target = rng.normal(size=(1260, 32)).astype(np.float32)
        self.assertNotEqual("candidate", consensus(candidate_matches(anchor,target))["status"])

    def test_ambiguous_single_motif_rejected(self):
        x=[{"template_offset":2,"candidate_shift":7.0,"strong":True,"similarity":0.92},
           {"template_offset":10,"candidate_shift":-15.0,"strong":True,"similarity":0.91},
           {"template_offset":18,"candidate_shift":32.0,"strong":True,"similarity":0.88}]
        self.assertEqual("ambiguous",consensus(x)["status"])

    def test_feature_shape(self):
        signal=np.random.default_rng(2).normal(size=8000*8).astype(np.float32)
        f=fingerprint(signal)
        self.assertEqual(32,f.shape[1])
        self.assertTrue(np.isfinite(f).all())

if __name__=="__main__":
    unittest.main()
