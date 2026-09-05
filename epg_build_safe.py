from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import epg_build

# Public-sports EPG is generated locally in this repository and merged later by
# public_sports_epg_merge.py. Never fetch the retired external public-sports repo
# from the base EPG builder.
epg_build.SOURCES = [(name, url) for name, url in epg_build.SOURCES if name != "public_sports"]
epg_build.SOURCE_PRIORITY = {name: i for i, (name, _) in enumerate(epg_build.SOURCES)}

epg_build.main()

out = Path("guides.xml")
if not out.is_file() or out.stat().st_size < 100_000:
    raise SystemExit(f"guides.xml suspiciously small: {out.stat().st_size if out.exists() else 0} bytes")

# 愛南ライブカメラ has no programme grid. Keep a 24-hour guide visible so the
# FreeWiFi EPG row never appears blank. Rebuild four JST days on every EPG run.
AINAN_ID = "ecatv.ainan_livecam"
AINAN_NAME = "愛南ライブカメラ"
JST = timezone(timedelta(hours=9))

root = ET.parse(out).getroot()

# Replace only our synthetic Ainan entries; leave every other channel untouched.
for p in list(root.findall("programme")):
    if p.get("channel") == AINAN_ID:
        root.remove(p)

ch = root.find(f"channel[@id='{AINAN_ID}']")
if ch is None:
    ch = ET.SubElement(root, "channel", {"id": AINAN_ID})
    ET.SubElement(ch, "display-name").text = AINAN_NAME

start_day = datetime.now(JST).replace(hour=0, minute=0, second=0, microsecond=0)
for offset in range(4):
    start = start_day + timedelta(days=offset)
    stop = start + timedelta(days=1)
    programme = ET.SubElement(
        root,
        "programme",
        {
            "start": start.strftime("%Y%m%d%H%M%S +0900"),
            "stop": stop.strftime("%Y%m%d%H%M%S +0900"),
            "channel": AINAN_ID,
        },
    )
    ET.SubElement(programme, "title", {"lang": "ja"}).text = "📹 愛南ライブカメラ｜24時間LIVE"
    ET.SubElement(programme, "desc", {"lang": "ja"}).text = (
        "愛媛CATV 愛南ライブカメラ。愛南地域のライブ映像を24時間配信しています。"
    )
    ET.SubElement(programme, "category", {"lang": "ja"}).text = "ライブカメラ"

ET.ElementTree(root).write(out, encoding="utf-8", xml_declaration=True)

root = ET.parse(out).getroot()
channels = len(root.findall("channel"))
programmes = len(root.findall("programme"))
if channels < 50 or programmes < 100:
    raise SystemExit(f"guides.xml suspiciously sparse: channels={channels} programmes={programmes}")

ainan_programmes = sum(1 for p in root.findall("programme") if p.get("channel") == AINAN_ID)
if ainan_programmes != 4:
    raise SystemExit(f"Ainan live-camera EPG missing: programmes={ainan_programmes}")

print(
    f"SAFE EPG OK: bytes={out.stat().st_size} channels={channels} programmes={programmes} "
    f"ainan_programmes={ainan_programmes}"
)
