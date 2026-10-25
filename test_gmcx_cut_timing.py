#!/usr/bin/env python3
import unittest
from gmcx_cut_timing import check_chapter_time

def regular(*times):
    return [{"kind":"episode","episode":404+i,"start_seconds":n} for i,n in enumerate(times)]

class CutTimeTests(unittest.TestCase):
    def test_sound_and_near_58_min_are_accepted(self):
        result=check_chapter_time(regular(0,3480,6960,10440),2,6972,15000)
        self.assertTrue(result["ok"])
        self.assertEqual(result["status"],"audio_and_time_consistent")
    def test_mismatching_length_fails_even_if_audio_is_strong(self):
        self.assertEqual(check_chapter_time(regular(0,3480,7060,10440),2,7065,15000)["status"],
                         "bad_regular_duration")
    def test_drift_outside_15_seconds_not_published(self):
        self.assertFalse(check_chapter_time(regular(0,3480,6960),1,3520,15000)["ok"])
    def test_specials_do_not_get_58_min_assumption(self):
        seq=[{"kind":"episode","start_seconds":10448},
             {"kind":"special","start_seconds":13928},
             {"kind":"episode","start_seconds":18814},
             {"kind":"special","start_seconds":22294},
             {"kind":"episode","start_seconds":23194},
             {"kind":"episode","start_seconds":26674}]
        self.assertEqual(check_chapter_time(seq,2,18817,42836)["status"],
                         "special_neighbours_baseline_only")
        self.assertTrue(check_chapter_time(seq,4,23196,42836)["ok"])
        self.assertFalse(check_chapter_time(seq,3,22296,42836)["ok"])

if __name__=="__main__":
    unittest.main()
