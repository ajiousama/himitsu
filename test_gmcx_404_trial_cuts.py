#!/usr/bin/env python3
"""#404-416 playback trial: 10s start and 58m15s steps."""
import unittest
from kick_gmcx_chapters import make_fixed_test_chapters

VOD={"vod_id":"4b6ff754-ab2f-43b3-bc30-ec3e9f0d8208","duration_seconds":57956}
class TrialCuts(unittest.TestCase):
    def test_grid_and_tail(self):
        rows=make_fixed_test_chapters(VOD,404,416,{})
        self.assertEqual(len(rows),14)
        for i,row in enumerate(rows[:-1]):
            start=10+i*3495
            self.assertEqual((row["episode"],row["start_seconds"],row["stop_seconds"],row["duration_seconds"]),
                             (404+i,start,start+3495,3495))
            self.assertEqual(row["confidence"],"provisional")
            self.assertIn(f"start={start}&duration=3495",row["replay_url"])
        self.assertEqual((rows[-1]["special_key"],rows[-1]["start_seconds"],rows[-1]["stop_seconds"],rows[-1]["duration_seconds"]),
                         ("404-416-unclassified-tail",45445,57956,12511))
    def test_does_not_affect_other_vods(self):
        rows=make_fixed_test_chapters({**VOD,"vod_id":"other"},404,416,{})
        self.assertEqual((rows[0]["start_seconds"],rows[1]["start_seconds"]),(0,3480))
if __name__=="__main__":
    unittest.main()
