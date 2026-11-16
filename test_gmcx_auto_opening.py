"""Automatic GCCX opening-audio boundaries must never corrupt archived playback."""
import json
import tempfile
import unittest
from pathlib import Path

from gmcx_auto_opening import candidates_for_vod, snap_audio_starts


class AutoOpeningTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)
        self.report=self.base/"review.json"
        self.groups=self.base/"groups.json"
        self.vod={
            "vod_id":"test-gccx-vod-000123456",
            "source_url":"https://example.invalid/owned-gccx.m3u8",
            "duration_seconds":17400,
        }
        self.spans=[(0,3480),(3480,6960),(6960,10440),
                    (10440,13920),(13920,17400)]
        self.groups.write_text(json.dumps({"schema_version":1,"groups":[]}))
        self.rows={
            "3480": {"status":"candidate","verification":"audio_only_needs_video",
                     "candidate_seconds":3451.2,"strong_matches":3,
                     "mean_similarity":.83},
            "6960": {"status":"candidate","verification":"audio_only_needs_video",
                     "candidate_seconds":6966.4,"strong_matches":2,
                     "mean_similarity":.77},
            "10440":{"status":"insufficient","verification":"audio_only_needs_video"},
        }
        self.save()

    def save(self, source=None, duration=None):
        payload={
          "schema_version":1,"vods":{self.vod["vod_id"]:{
              "source_url":source or self.vod["source_url"],
              "duration_seconds": duration or self.vod["duration_seconds"],
              "rows":self.rows,
          }}}
        self.report.write_text(json.dumps(payload))

    def apply(self,verified=()):
        return snap_audio_starts(self.spans,self.vod,0,17400,list(verified),
                                 self.report,self.groups)

    def test_real_candidate_snaps_but_covers_every_second(self):
        spans,positions=self.apply()
        self.assertEqual(spans[0],(0,3451))
        self.assertEqual(spans[1],(3451,6966))
        self.assertEqual(spans[2],(6966,10440))
        self.assertEqual(spans[-1][1],17400)
        self.assertEqual(positions,{3451,6966})
        self.assertTrue(all(a[1]==b[0] for a,b in zip(spans,spans[1:])))
        self.assertTrue(all((b-a)<=3605 for a,b in spans))

    def test_a_video_verified_start_is_protected(self):
        spans,positions=self.apply(verified=(6960,))
        self.assertEqual(spans[1][1],6960)
        self.assertEqual(spans[2][0],6960)
        self.assertEqual(positions,{3451})

    def test_series_marathon_is_never_shifted(self):
        data={"schema_version":1,"groups":[{
          "source_vod_id":self.vod["vod_id"],
          "source_url":self.vod["source_url"],
          "start_seconds":3480,
          "end_seconds":10440,
        }]}
        self.groups.write_text(json.dumps(data))
        spans,positions=self.apply()
        self.assertEqual(spans,self.spans)
        self.assertFalse(positions)

    def test_wrong_source_and_duration_fail_closed(self):
        self.save(source="https://example.invalid/other.m3u8")
        self.assertEqual(self.apply(),(self.spans,set()))
        self.save(duration=17600)
        self.assertEqual(self.apply(),(self.spans,set()))

    def test_unverified_and_unreasonable_matches_rejected(self):
        self.rows["3480"]["verification"]="unverified_other_algorithm"
        self.rows["6960"]["candidate_seconds"]=7020
        self.save()
        self.assertEqual(self.apply(),(self.spans,set()))

    def test_reject_weak_evidence(self):
        self.rows["3480"]["strong_matches"]=1
        self.rows["6960"]["mean_similarity"]=.51
        self.save()
        self.assertEqual(candidates_for_vod(self.vod,0,17400,self.report),[])
        self.assertEqual(self.apply(),(self.spans,set()))

    def test_missing_scan_is_safe(self):
        self.report.unlink()
        self.assertEqual(self.apply(),(self.spans,set()))


if __name__=="__main__":
    unittest.main()
