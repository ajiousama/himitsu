import unittest
import xml.etree.ElementTree as ET
from normalize_race_epg_switch import normalize_root, validate_root, title

def add(root, cid, start, stop, name):
    p = ET.SubElement(root, "programme", channel=cid, start=start+" +0900", stop=stop+" +0900")
    ET.SubElement(p, "title").text = name
    return p

class RaceEPGTest(unittest.TestCase):
    def test_all_sports_and_two_dates(self):
        root = ET.Element("tv")
        ids = ("keirin.test", "chihou.test", "auto.test", "boat.test",
               "jra.east", "jra.west.hq", "jra.local.lq", "jra.hokkaido")
        races = []
        for cid in ids:
            ch = ET.SubElement(root, "channel", id=cid)
            ET.SubElement(ch, "display-name").text = "テスト"
            for day in ("20261126", "20261127"):
                if day.endswith("26"):
                    add(root, cid, day+"000000", day+"103700", "本日テスト開催　1R10:40発走　デイ")
                a = add(root, cid, day+"103700", day+"104300", "【１Ｒ】 10:40発走")
                b = add(root, cid, day+"104300", day+"111300", "【２Ｒ】 11:10発走")
                add(root, cid, day+"111300", day+"235900", "本日の開催は終了しました")
                races.append((cid, day, a, b))
        tv = add(root, "jra.gch.hq", "20261126103700", "20261126104300", "【１Ｒ】 10:40発走")
        normalize_root(root)
        validate_root(root, "fixture")
        for cid, day, a, b in races:
            self.assertEqual(a.get("start"), day+"101000 +0900")
            self.assertEqual(a.get("stop"), day+"104300 +0900")
            self.assertEqual(b.get("start"), a.get("stop"))
            guides = [p for p in root.findall("programme") if p.get("channel")==cid
                      and p.get("start")==day+"000000 +0900" and "開催" in title(p)]
            self.assertEqual(len(guides), 1)
            self.assertEqual(guides[0].get("stop"), a.get("start"))
        self.assertEqual(tv.get("start"), "20261126103700 +0900")
        self.assertEqual(normalize_root(root)[0], 0)

if __name__ == "__main__":
    unittest.main()
