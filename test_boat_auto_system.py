from __future__ import annotations

import base64
from datetime import date, datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET

import boat_auto_system as boat


def fake_stream(day: date) -> str:
    start = int(datetime(day.year, day.month, day.day, 6, 0, tzinfo=boat.JST).timestamp())
    payload = {"start": start, "exp": start + 36 * 60 * 60}
    encoded = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"https://manifest.streaks.jp/test/hls/v3/manifest.m3u8?token=x.{encoded}.x"


def card(day: date, first_hour: int, first_minute: int = 0):
    first = datetime(day.year, day.month, day.day, first_hour, first_minute, tzinfo=boat.JST)
    return [
        {"race": number, "start": first + timedelta(minutes=(number - 1) * 30), "name": "テスト競走"}
        for number in range(1, 13)
    ]


class BoatAutoSystemTests(unittest.TestCase):
    def test_midnight_provider_404_is_schedule_pending(self):
        self.assertTrue(boat.schedule_not_published_error(RuntimeError("HTTPError: HTTP Error 404: Not Found")))
        self.assertFalse(boat.schedule_not_published_error(RuntimeError("HTTP Error 500: Server Error")))

    def test_finished_venue_is_kept_until_date_change(self):
        day = date(2026, 9, 8)
        races = card(day, 8, 30)
        now = datetime(2026, 9, 8, 20, 0, tzinfo=boat.JST)
        url = fake_stream(day)
        venues, rows, phases = boat.build_venue_state(
            {"10": races},
            {"boat.mikuni": {"url": url, "source": "test"}},
            now,
        )
        item = venues["boat.mikuni"]
        self.assertTrue(item["ended"])
        self.assertTrue(item["visible"])
        self.assertEqual(item["stream_window"], "ended_kept")
        self.assertEqual(len(rows), 1)
        self.assertEqual(phases["morning"]["ended"], 1)

    def test_seed_alert_starts_only_when_venue_is_due(self):
        day = date(2026, 9, 8)
        races = card(day, 15, 0)
        early = datetime(2026, 9, 8, 10, 0, tzinfo=boat.JST)
        due = datetime(2026, 9, 8, 14, 30, tzinfo=boat.JST)
        early_item = boat.build_venue_state({"07": races}, {}, early)[0]["boat.gamagori"]
        due_item = boat.build_venue_state({"07": races}, {}, due)[0]["boat.gamagori"]
        self.assertFalse(early_item["seed_required"])
        self.assertTrue(due_item["seed_required"])

    def test_epg_switches_to_tomorrow_guidance_after_45_minutes(self):
        day = date(2026, 9, 8)
        races = card(day, 10, 5)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "epg.xml"
            root = ET.Element("tv")
            future = ET.SubElement(root, "programme", {
                "channel": "boat.heiwajima",
                "start": "20260909100000 +0900",
                "stop": "20260909180000 +0900",
            })
            ET.SubElement(future, "title", {"lang": "ja"}).text = "BOATRACE平和島 開催予定（仮時間）"
            ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)
            boat.overlay_epg_file(path, {"04": races}, day)
            root = ET.parse(path).getroot()
            today_titles = [
                (p.findtext("title") or "")
                for p in root.findall("programme")
                if p.get("channel") == "boat.heiwajima" and (p.get("start") or "").startswith("20260908")
            ]
            self.assertIn("本日の開催は終了しました", today_titles)
            self.assertIn("翌日開催予定（仮時間）", today_titles)

    def test_epg_contains_every_race_and_exact_finished_message(self):
        day = date(2026, 9, 8)
        races = card(day, 10, 5)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "epg.xml"
            count = boat.overlay_epg_file(path, {"04": races}, day)
            root = ET.parse(path).getroot()
            programmes = [p for p in root.findall("programme") if p.get("channel") == "boat.heiwajima"]
            titles = [p.findtext("title") for p in programmes]
            self.assertEqual(count, 13)
            self.assertEqual(len(programmes), 13)
            self.assertIn("【１Ｒ】 10:05発走  🚤【BOATRACE平和島 🚤】", titles)
            self.assertEqual(titles[-1], "本日の開催は終了しました")


if __name__ == "__main__":
    unittest.main()
