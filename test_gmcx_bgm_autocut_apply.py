#!/usr/bin/env python3
"""Regression test for guarded BGM publishing without real repository writes."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import gmcx_bgm_autocut_apply as publisher


class GuardedPublishTests(unittest.TestCase):
    def test_verified_cuts_untouched_and_consensus_published(self):
        with tempfile.TemporaryDirectory() as d:
            folder=Path(d)
            source="example-vod-357"
            items=[
                {"kind":"episode","episode":357,"title":"Ep357","start_seconds":0,
                 "stop_seconds":3488,"duration_seconds":3488,
                 "replay_url":"https://example.test/?vod=x&start=0&duration=3488",
                 "method":"user-test-broadcast-order","confidence":"provisional"},
                {"kind":"episode","episode":358,"title":"Ep358","start_seconds":3488,
                 "stop_seconds":6968,"duration_seconds":3480,
                 "replay_url":"https://example.test/?vod=x&start=3488&duration=3480",
                 "method":"manual-playback-confirmed","confidence":"confirmed"},
                {"kind":"episode","episode":359,"title":"Ep359","start_seconds":6968,
                 "stop_seconds":10448,"duration_seconds":3480,
                 "replay_url":"https://example.test/?vod=x&start=6968&duration=3480",
                 "method":"manual-playback-offset-propagated","confidence":"provisional"},
                {"kind":"special","special_key":"357-359-tail","title":"Tail","start_seconds":10448,
                 "stop_seconds":10800,"duration_seconds":352,
                 "replay_url":"https://example.test/?vod=x&start=10448&duration=352",
                 "method":"manual-playback-offset-propagated","confidence":"provisional"},
            ]
            state={"results":[{"vod_id":source,"episode_start":357,"episode_end":359,
                              "duration_seconds":10800,"chapters":items}]}
            votes=[{"reference_episode":ep,"correction_seconds":-3.1,
                    "similarity":.9,"support_templates":5} for ep in (378,388,398)]
            report={"bundles":[{"episode_start":357,"status":"review_only",
                 "reference_sources_used":3,"manual_anchor_episodes":[358],
                 "rows":[{"episode":359,"existing_start_seconds":6968,
                          "proposed_start_seconds":6965,"status":"candidate",
                          "independent_reference_proposals":votes}]}]}
            play=["#EXTM3U"]
            for c in items:
                key=(f"kick.gmcx.chapter.{c['episode']}" if c["kind"]=="episode"
                     else "kick.gmcx.special."+c["special_key"])
                play += [f'#EXTINF:-1 tvg-id="{key}",{c["title"]}',c["replay_url"]]
            paths={
                "CHAPTERS":folder/"chapters.json",
                "REPORT":folder/"report.json",
                "LEDGER":folder/"ledger.json",
                "M3U":folder/"playlist.m3u"
            }
            paths["CHAPTERS"].write_text(json.dumps(state))
            paths["REPORT"].write_text(json.dumps(report))
            paths["M3U"].write_text("\n".join(play)+"\n")
            with patch.multiple(publisher,**paths):
                publisher.main()
            newer=json.loads(paths["CHAPTERS"].read_text())["results"][0]["chapters"]
            self.assertEqual(3488,newer[1]["start_seconds"])
            self.assertEqual(6965,newer[2]["start_seconds"])
            self.assertEqual(6965,newer[1]["stop_seconds"])
            self.assertEqual(10448,newer[2]["stop_seconds"])
            self.assertEqual(3483,newer[2]["duration_seconds"])
            self.assertIn("start=6965&duration=3483",
                          paths["M3U"].read_text())
            saved=json.loads(paths["LEDGER"].read_text())["vods"]
            self.assertEqual(6965,saved[source]["starts"]["359"])

    def test_current_independent_reference_triplets(self):
        def row(ids):
            return {"status":"candidate","existing_start_seconds":10000,
                    "proposed_start_seconds":10003,
                    "independent_reference_proposals":[
                        {"reference_episode":n,"correction_seconds":3.0,
                         "similarity":.96,"support_templates":5} for n in ids]}
        self.assertTrue(publisher.report_candidate_valid(row([388,398,404]), 385, 10000))
        self.assertTrue(publisher.report_candidate_valid(row([378,398,404]), 395, 10000))
        self.assertTrue(publisher.report_candidate_valid(row([378,388,398]), 405, 10000))
        self.assertFalse(publisher.report_candidate_valid(row([398,404,404]), 405, 10000))
        self.assertFalse(publisher.report_candidate_valid(row([378,388]), 405, 10000))

    def test_previous_conflict_episode_is_held(self):
        self.assertIn(390,publisher.HOLD_EPISODES)
        row={"status":"candidate","existing_start_seconds":10448,
             "proposed_start_seconds":10450,
             "independent_reference_proposals":[{"reference_episode":x,
                    "correction_seconds":2,"similarity":.96,"support_templates":5}
                    for x in (357,367,377)]}
        self.assertFalse(publisher.report_candidate_valid(row,390,10448))


if __name__=="__main__":
    unittest.main()
