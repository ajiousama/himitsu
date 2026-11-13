#!/usr/bin/env python3
import json
import tempfile
import unittest
from pathlib import Path
from gmcx_long_nav import build_video_observed_opening_entries

VOD_ID = "df1386fd-4bd1-41ae-ac64-743ff49a838f"
OTHER_ID = "invalid-id-2345"


def fixture(d: str, *, duration=172798, is_partial=True, source_id=VOD_ID,
            start=59152, end=None):
    root=Path(d)
    replay=root/"kick_replay.json"
    chapters=root/"kick_gmcx_chapters.json"
    observed=root/"gmcx_video_verified_openings.json"
    replay.write_text(json.dumps({"vods":[{
        "vod_id":VOD_ID,"tvg_id":"kick.gccx2","playable":True,
        "ready_for_publish":True,"duration_seconds":duration,
    }]}),encoding="utf-8")
    chapters.write_text(json.dumps({"results":[{
        "vod_id":VOD_ID,"status":"ready","partial":is_partial,
        "chapters":[
            {"kind":"episode","start_seconds":0,"stop_seconds":52213},
            {"kind":"special","confidence":"unconfirmed",
             "title":"長時間特別編以降（未分割・確認待ち）",
             "start_seconds":52213,"stop_seconds":172795},
        ],
    }]}),encoding="utf-8")
    observed.write_text(json.dumps({
        "source_vod_id":source_id,"source_duration_seconds":172798,
        "openings":[{
            "key":"sp","start_seconds":start,"end_seconds":end,
            "episode_number":None,"clip_preview_seconds":3480,
            "title":"ゲームセンターCX 3時間生放送スペシャル 冒頭",
            "confidence":"video_intro_observed_episode_end_unverified",
        }]
    }),encoding="utf-8")
    return replay,chapters,observed


class VideoObservedGccxOpeningTests(unittest.TestCase):
    def test_video_observed_special_is_preview_only(self):
        with tempfile.TemporaryDirectory() as d:
            r,c,e=fixture(d)
            result=build_video_observed_opening_entries(r,c,e)
            self.assertEqual(len(result),1)
            meta,url=result[0]
            self.assertIn("映像で冒頭確認",meta)
            self.assertIn("終点未確定",meta)
            self.assertIn("&start=59152&duration=3480",url)
            self.assertNotIn("#60",meta)

    def test_wrong_vod_never_publishes(self):
        with tempfile.TemporaryDirectory() as d:
            r,c,e=fixture(d,source_id=OTHER_ID)
            self.assertEqual(build_video_observed_opening_entries(r,c,e),[])

    def test_source_duration_change_never_publishes(self):
        with tempfile.TemporaryDirectory() as d:
            r,c,e=fixture(d,duration=180000)
            self.assertEqual(build_video_observed_opening_entries(r,c,e),[])

    def test_verified_full_episode_must_not_get_duplicate(self):
        with tempfile.TemporaryDirectory() as d:
            r,c,e=fixture(d,is_partial=False)
            self.assertEqual(build_video_observed_opening_entries(r,c,e),[])

    def test_end_not_verified_must_remain_null(self):
        with tempfile.TemporaryDirectory() as d:
            r,c,e=fixture(d,end=69952)
            self.assertEqual(build_video_observed_opening_entries(r,c,e),[])

    def test_cannot_overwrite_confirmed_earlier_boundary(self):
        with tempfile.TemporaryDirectory() as d:
            r,c,e=fixture(d,start=3480)
            self.assertEqual(build_video_observed_opening_entries(r,c,e),[])


if __name__=="__main__":
    unittest.main()
