import unittest
from datetime import date, datetime
from unittest.mock import patch
import xml.etree.ElementTree as ET
from publish_public_sports import merge_fresh, prepare, project, validate_visible, groups, race_keys
from sports_race_time import JST

DAY=date(2026,11,26)
def channel(root,cid):
    c=ET.SubElement(root,"channel",id=cid)
    ET.SubElement(c,"display-name").text=cid
def row(root,cid,day,start,stop,title,desc=""):
    p=ET.SubElement(root,"programme",channel=cid,start=day+start+"00 +0900",stop=day+stop+"00 +0900")
    ET.SubElement(p,"title").text=title
    ET.SubElement(p,"desc").text=desc
    return p

class PublicationTest(unittest.TestCase):
    def test_same_day_retention_and_no_yesterday(self):
        old=ET.Element("tv"); fresh=ET.Element("tv")
        for cid in ("keirin.test","keirin.yesterday","keirin.cancel"):
            channel(old,cid)
        row(old,"keirin.test","20261126","0800","1043","【１Ｒ】10:40発走")
        row(old,"keirin.test","20261126","1043","1113","【２Ｒ】11:10発走")
        row(old,"keirin.yesterday","20261125","0800","1043","【１Ｒ】10:40発走")
        row(old,"keirin.cancel","20261126","0800","1043","【１Ｒ】10:40発走")
        channel(fresh,"keirin.cancel")
        row(fresh,"keirin.cancel","20261126","0000","2359","本日中止")
        result=merge_fresh(old,fresh,DAY)
        g=groups(result,DAY)
        self.assertEqual(len(race_keys(g["keirin.test"])),2)
        self.assertNotIn("keirin.yesterday",g)
        self.assertFalse(race_keys(g["keirin.cancel"]))
    def test_projection_waiting_and_tv_preservation(self):
        local=ET.Element("tv"); guide=ET.Element("tv")
        for cid in ("keirin.test","chihou.test","auto.pending"):
            channel(local,cid)
        row(local,"keirin.test","20261126","0800","1043","【１Ｒ】10:40発走")
        row(local,"chihou.test","20261126","0800","1043","【１Ｒ】10:40発走")
        row(local,"auto.pending","20261126","0900","1700","開催予定","公式出走表")
        tv=row(guide,"tv.test","20261126","0900","1700","TV番組")
        row(guide,"keirin.old","20261126","0900","1700","古い開催場")
        prepare(local,DAY)
        class Clock(datetime):
            @classmethod
            def now(cls,tz=None):
                return cls(2026,11,26,5,tzinfo=JST)
        with patch("publish_public_sports.datetime",Clock):
            project(local,guide)
        self.assertIn(tv,list(guide))
        self.assertNotIn("keirin.old",groups(guide,DAY))
        playlist='\n'.join(f'#EXTINF:-1 tvg-id="{cid}" group-title="今日の開催場",test' for cid in ("keirin.test","chihou.test","auto.pending"))
        validate_visible(local,guide,playlist,DAY)
        pending=groups(local,DAY)["auto.pending"][0]
        self.assertIn("発走時刻取得待ち",pending.findtext("title"))
        self.assertEqual(pending.get("start"),"20261126000000 +0900")

if __name__=="__main__":
    unittest.main()
