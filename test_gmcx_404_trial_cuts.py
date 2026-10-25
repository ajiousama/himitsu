#!/usr/bin/env python3
"""GCCX #404-416 listening review: #409 56:51 and a year-end insert after #411."""
import unittest
from kick_gmcx_chapters import make_fixed_test_chapters

VOD = {"vod_id": "4b6ff754-ab2f-43b3-bc30-ec3e9f0d8208", "duration_seconds": 57956}
STARTS = {404:10,405:3505,406:7000,407:10495,408:13990,409:17485,
          410:20896,411:24391,412:28748,413:32243,414:35738,
          415:39233,416:42728}
SPECIAL_KEY = "404-416-yearend-15min-after-411"

class TrialCuts(unittest.TestCase):
    def setUp(self):
        self.rows = make_fixed_test_chapters(VOD,404,416,{})
        self.episodes = {c["episode"]:c for c in self.rows if c["kind"]=="episode"}
    def test_episode_starts_and_lengths(self):
        self.assertEqual(len(self.episodes),13)
        for ep,start in STARTS.items():
            c = self.episodes[ep]
            length = 3411 if ep==409 else 3457 if ep==411 else 3495
            self.assertEqual((c["start_seconds"],c["stop_seconds"],c["duration_seconds"]),
                             (start,start+length,length))
            self.assertIn(f"start={start}&duration={length}",c["replay_url"])
            self.assertEqual(c["confidence"],"provisional")
        self.assertEqual(self.episodes[408]["duration_seconds"],3495)
        self.assertEqual(self.episodes[409]["duration_seconds"],56*60+51)
    def test_15_minute_special_is_independent_from_412(self):
        self.assertEqual(len(self.rows),15)
        extra = [c for c in self.rows if c.get("special_key")==SPECIAL_KEY]
        self.assertEqual(len(extra),1)
        x = extra[0]
        self.assertEqual((x["start_seconds"],x["stop_seconds"],x["duration_seconds"]),
                         (27848,28748,900))
        self.assertEqual(self.episodes[411]["stop_seconds"],x["start_seconds"])
        self.assertEqual(self.episodes[412]["start_seconds"],x["stop_seconds"])
        for a,b in zip(self.rows,self.rows[1:]):
            self.assertEqual(a["stop_seconds"],b["start_seconds"])
    def test_unclassified_footage_is_preserved(self):
        tail=self.rows[-1]
        self.assertEqual((tail["special_key"],tail["start_seconds"],tail["stop_seconds"]),
                         ("404-416-unclassified-tail",46223,57956))
    def test_does_not_affect_another_recording(self):
        other = {**VOD,"vod_id":"not-this-source"}
        rows = make_fixed_test_chapters(other,404,416,{})
        self.assertEqual([x["start_seconds"] for x in rows[:2]],[0,3480])

if __name__=="__main__":
    unittest.main()
