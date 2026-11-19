import tempfile
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from ganble.race_vod.build import extract, assemble, safe_video_url, m3u

JST = timezone(timedelta(hours=9))

FIXTURE = '''<?xml version="1.0"?><tv>
<channel id="keirin.kokura"><display-name>小倉</display-name></channel>
<channel id="chihou.sonoda"><display-name>園田</display-name></channel>
<channel id="boat.marugame"><display-name>丸亀</display-name></channel>
<programme channel="keirin.kokura" start="20261120151200 +0900" stop="20261120154000 +0900">
<title>【１Ｒ】 15:15発走 🚲【予選 🚲】</title><desc>競輪 小倉</desc></programme>
<programme channel="chihou.sonoda" start="20261120110700 +0900" stop="20261120114000 +0900">
<title>【２Ｒ】 11:10発走 🏇【２歳初出走 🏇】</title></programme>
<programme channel="boat.marugame" start="20261120151200 +0900"><title>【１Ｒ】 15:15発走</title></programme>
<programme channel="keirin.kokura" start="20261120000000 +0900"><title>本日小倉開催 1R15:15発走</title></programme>
</tv>'''

class TestRaceVod(unittest.TestCase):
    def get_rows(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "epg.xml"
            path.write_text(FIXTURE, encoding="utf-8")
            return extract(path)

    def test_filters_and_dates(self):
        rows = self.get_rows()
        self.assertEqual(2, len(rows))
        self.assertEqual({"keirin", "nar"}, {r["sport"] for r in rows})
        self.assertEqual("2026-11-20", rows[0]["date"])
        self.assertEqual("keirin:20261120:keirin.kokura:01", rows[0]["id"])

    def test_unverified_does_not_enter_m3u(self):
        rows = assemble(self.get_rows(), [], {}, datetime(2026, 11, 20, 19, tzinfo=JST))
        self.assertTrue(all(row["video_status"] == "not_verified" for row in rows))
        self.assertEqual("#EXTM3U\n", m3u(rows))

    def test_explicit_verified_source(self):
        data = self.get_rows()
        approved = {data[0]["id"]: {"url": "https://media.example.org/a.m3u8", "playback_verified": True}}
        rows = assemble(data, [], approved, datetime(2026, 11, 20, 19, tzinfo=JST))
        self.assertIn("https://media.example.org/a.m3u8", m3u(rows))
        self.assertEqual(1, sum(r["video_status"] == "verified" for r in rows))
        self.assertFalse(safe_video_url("https://media.example.org/stream/live"))
        self.assertFalse(safe_video_url("http://media.example.org/a.m3u8"))
        self.assertFalse(safe_video_url("https://user:pass@media.example.org/a.mp4"))

    def test_history_survives_epg_rollover(self):
        old = self.get_rows()
        rows = assemble([], old, {}, datetime(2026, 11, 21, 13, tzinfo=JST))
        self.assertEqual(len(old), len(rows))

if __name__ == "__main__":
    unittest.main()
