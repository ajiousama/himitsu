"""Offline checks: evidence-backed GCCX continuous shows don't merge long videos."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from gmcx_continuity import grouped_label, grouped_slices


class ContinuityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/"groups.json"
        self.vod = {"vod_id": "example-vod-123", "source_url": "https://example.invalid/hls.m3u8"}
        self.spans = [(0,3480),(3480,6960),(6960,10440)]
        self.observed = {
            ("example-vod-123",0): ("Game A",None),
            ("example-vod-123",6960): ("Game A",None),
        }
        self.data = {"schema_version":1,"groups":[{
            "group_id": "programme-a",
            "source_vod_id": "example-vod-123",
            "source_url": self.vod["source_url"],
            "start_seconds":0, "end_seconds":10440,
            "title":"Game A programme",
            "evidence_anchor_starts":[0,6960],
            "confidence":"video_anchored_continuity_estimate"
        }]}

    def save(self):
        self.path.write_text(json.dumps(self.data), encoding="utf-8")

    def test_three_consecutive_chunks_one_programme(self):
        self.save()
        grouped=grouped_slices(self.vod,self.spans,self.observed,self.path)
        self.assertEqual([grouped[t]["part"] for t in (0,3480,6960)],[1,2,3])
        self.assertTrue(grouped[0]["anchor"])
        self.assertFalse(grouped[3480]["anchor"])
        self.assertIn("前後の映像から継続推定",
                      grouped_label(grouped[3480],None,"11/11","00:58:00","01:56:00"))
        self.assertIn("［映像：Game A］",
                      grouped_label(grouped[0],"Game A","11/11","00:00:00","00:58:00"))

    def test_wrong_source_never_groups(self):
        self.save()
        fake=dict(self.vod,source_url="https://example.invalid/replaced.m3u8")
        self.assertEqual(grouped_slices(fake,self.spans,self.observed,self.path),{})

    def test_missing_frame_evidence_rejects(self):
        self.save()
        self.assertEqual(grouped_slices(self.vod,self.spans,{("example-vod-123",0):("Game A",None)},self.path),{})

    def test_unsafe_overlap_is_not_published(self):
        self.data["groups"].append(dict(self.data["groups"][0],
                                         group_id="overlap",start_seconds=3480))
        self.save()
        result=grouped_slices(self.vod,self.spans,self.observed,self.path)
        self.assertEqual(len(result),3)
        self.assertTrue(all(g["group_id"]=="programme-a" for g in result.values()))

    def test_group_does_not_create_new_stream(self):
        self.save()
        rows=grouped_slices(self.vod,self.spans,self.observed,self.path)
        self.assertEqual(set(rows),{0,3480,6960})
        self.assertTrue(all((stop-start)<=3605 for start,stop in self.spans))


if __name__ == "__main__":
    unittest.main()
