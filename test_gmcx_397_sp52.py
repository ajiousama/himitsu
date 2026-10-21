#!/usr/bin/env python3
"""No-network test of the 2025 GMCX SP52 insertion and full-VOD coverage."""
import unittest
from kick_gmcx_chapters import make_fixed_test_chapters, _mark_provisional_titles

VOD={"vod_id":"c60eb405-0e1a-4679-beca-79d8c95b2e7f","duration_seconds":51537}
EP_TITLES={"397":"炎の闘球児 ドッジ弾平","398":"新・忍伝（前編）",
"399":"新・忍伝（後編）","400":"愛戦士ニコル",
"401":"亀の恩返し ウラシマ伝説","402":"ECHO NIGHT",
"403":"ピカチュウげんきでちゅう"}

class TestMixed2025Archive(unittest.TestCase):
    def setUp(self):
        self.rows=make_fixed_test_chapters(VOD,397,403,EP_TITLES)
    def test_broadcast_order_and_sp52_position(self):
        seq=[c.get("episode") if c["kind"]=="episode" else c["special_key"] for c in self.rows]
        self.assertEqual(seq,[397,398,399,"2025-sp52-400min-live",400,401,402,403,"397-403-unclassified-tail"])
        sp=self.rows[3]
        self.assertEqual(sp["start_seconds"],10440)
        self.assertEqual(sp["duration_seconds"],24000)
        self.assertIn("400分生放送",sp["title"])
        self.assertEqual(self.rows[4]["start_seconds"],34440)
        self.assertEqual(self.rows[8]["duration_seconds"],3177)
        self.assertEqual(self.rows[8]["stop_seconds"],51537)
        self.assertEqual(len(self.rows),9)
    def test_no_gaps_and_user_checked_old_ranges_not_modified(self):
        self.assertEqual(self.rows[0]["start_seconds"],0)
        for current,next_ in zip(self.rows,self.rows[1:]):
            self.assertEqual(current["stop_seconds"],next_["start_seconds"])
            self.assertEqual(current["duration_seconds"],current["stop_seconds"]-current["start_seconds"])
        for row in self.rows:
            self.assertEqual(row["confidence"],"provisional" if row["kind"]=="episode" or row["special_key"]=="2025-sp52-400min-live" else "low")
    def test_special_title_reference_but_boundary_not_confirmed(self):
        rows=_mark_provisional_titles(self.rows,397,403)
        by_key={c.get("special_key"):c for c in rows if c["kind"]=="special"}
        sp=by_key["2025-sp52-400min-live"]
        self.assertEqual(sp["title_status"],"confirmed-reference")
        self.assertEqual(sp["confidence"],"provisional")
        for c in rows:
            if c["kind"]=="episode":
                self.assertEqual(c["title_status"],"confirmed-reference")
                self.assertEqual(c["confidence"],"provisional")

if __name__=="__main__":
    unittest.main()
