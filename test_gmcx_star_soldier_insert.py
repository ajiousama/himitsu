#!/usr/bin/env python3
"""GCCX #390 -> DVD Star Soldier -> #391 -> year-end SP49 -> #392 guard."""
import unittest
from kick_gmcx_chapters import (
    make_fixed_test_chapters, _apply_manual_episode_start_overrides,
    _mark_provisional_titles,
)

VOD = {"vod_id":"a640717e-6b99-4a10-a0d4-152d50117319","duration_seconds":42836}


class StarSoldierInsertionTests(unittest.TestCase):
    def setUp(self):
        seed=make_fixed_test_chapters(VOD,387,396,{str(ep):f"test-{ep}" for ep in range(387,397)})
        self.rows,self.overrides=_apply_manual_episode_start_overrides(VOD,seed)
        self.by_episode={int(c["episode"]):c for c in self.rows if c.get("kind")=="episode"}
        self.by_special={str(c["special_key"]):c for c in self.rows if c.get("kind")=="special"}

    def test_insertion_and_protected_manual_head(self):
        self.assertEqual("applied",self.overrides["status"])
        bonus=self.by_special["2024-dvdbox21-star-soldier"]
        self.assertEqual(13928,bonus["start_seconds"])
        self.assertEqual(18814,bonus["stop_seconds"])
        self.assertEqual(4886,bonus["duration_seconds"])
        self.assertEqual(3488,self.by_episode[388]["start_seconds"])
        self.assertEqual(13928,self.by_episode[390]["stop_seconds"])
        self.assertEqual(18814,self.by_episode[391]["start_seconds"])

    def test_yearend_2024_special_between_391_and_392(self):
        mini=self.by_special["2024-yearend-sp49-15min"]
        self.assertIn("年越し15分",mini["title"])
        self.assertEqual(22294,mini["start_seconds"])
        self.assertEqual(23194,mini["stop_seconds"])
        self.assertEqual(900,mini["duration_seconds"])
        self.assertEqual(self.by_episode[391]["stop_seconds"],mini["start_seconds"])
        self.assertEqual(self.by_episode[392]["start_seconds"],mini["stop_seconds"])

    def test_remaining_episodes_and_source_tail(self):
        self.assertEqual(37114,self.by_episode[396]["start_seconds"])
        self.assertEqual(40594,self.by_episode[396]["stop_seconds"])
        remaining=self.by_special["387-396-unclassified-tail"]
        self.assertEqual(40594,remaining["start_seconds"])
        self.assertEqual(42836,remaining["stop_seconds"])
        self.assertEqual(2242,remaining["duration_seconds"])
        self.assertEqual(13,len(self.rows))
        self.assertEqual(0,self.rows[0]["start_seconds"])
        for a,b in zip(self.rows,self.rows[1:]):
            self.assertEqual(a["stop_seconds"],b["start_seconds"])
        for item in self.rows:
            self.assertEqual(item["duration_seconds"],item["stop_seconds"]-item["start_seconds"])
            self.assertIn(f"start={item['start_seconds']}&duration={item['duration_seconds']}",item["replay_url"])

    def test_bonus_title_is_not_renamed_or_misnumbered(self):
        marked=_mark_provisional_titles(self.rows,387,396)
        bonus=next(c for c in marked if c.get("special_key")=="2024-dvdbox21-star-soldier")
        self.assertIn("スターソルジャー",bonus["title"])
        self.assertEqual("confirmed-reference",bonus["title_status"])
        self.assertEqual("manual-playback-offset-propagated",bonus["method"])
        self.assertEqual("provisional",bonus["confidence"])
        mini=next(c for c in marked if c.get("special_key")=="2024-yearend-sp49-15min")
        self.assertEqual("confirmed-reference",mini["title_status"])
        self.assertEqual("manual-playback-offset-propagated",mini["method"])
        self.assertEqual("provisional",mini["confidence"])
        self.assertNotIn("（仮）",mini["title"])


if __name__=="__main__":
    unittest.main()
