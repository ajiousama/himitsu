#!/usr/bin/env python3
from __future__ import annotations

import html
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

GUIDES = "https://raw.githubusercontent.com/karenda-jp/etc/main/guides.xml"
OUT = Path(__file__).with_name("haru_kai_epg.xml")

# guides.xml channel id -> HARU replay source.
CHANNELS = {
    "NHK東京・教育_jp": "nhk_e",
    "NHK大阪・教育_jp": "nhk_e",
    "日本テレビ_jp": "ntv",
    "テレビ朝日_jp": "tv_asahi",
    "TBS_jp": "tbs",
    "テレ東_jp": "tv_tokyo",
    "フジテレビ_jp": "fuji_tv",
    "毎日テレビ_jp": "mbs",
    "ABCテレビ_jp": "abc",
    "テレビ大阪_jp": "tv_osaka",
    "関西テレビ_jp": "kansai_tv",
    "読売テレビ_jp": "ytv",
    "KBS京都_jp": "kbs",
    "サンテレビ_jp": "sun",
}


def fetch() -> bytes:
    req = urllib.request.Request(GUIDES, headers={"User-Agent": "Mozilla/5.0 HARU-KAI-EPG/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read(50_000_000)


def parse_xmltv_time(raw: str) -> datetime:
    # XMLTV: YYYYmmddHHMMSS +0900. datetime.strptime handles numeric offsets.
    return datetime.strptime(raw.strip(), "%Y%m%d%H%M%S %z")


def main() -> None:
    root = ET.fromstring(fetch())
    programmes = []
    used_channels = set()
    for p in root.findall("programme"):
        ch = p.attrib.get("channel", "")
        source = CHANNELS.get(ch)
        if not source:
            continue
        start_raw = p.attrib.get("start", "")
        stop_raw = p.attrib.get("stop", "")
        try:
            start = parse_xmltv_time(start_raw)
            stop = parse_xmltv_time(stop_raw)
        except Exception:
            continue
        epoch = int(start.astimezone(timezone.utc).timestamp())
        replay = f"https://haru.charandom.blog/stream/jp/{source}/replay.m3u8?mode=hls&start={epoch}"
        used_channels.add(ch)
        programmes.append((start, replay, p))

    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<tv generator-info-name="himitsu HARU replay EPG">']
    for c in root.findall("channel"):
        if c.attrib.get("id", "") in used_channels:
            out.append(ET.tostring(c, encoding="unicode"))
    for _, replay, p in sorted(programmes, key=lambda x: x[0]):
        out.append(f"<!-- {html.escape(replay)} -->")
        out.append(ET.tostring(p, encoding="unicode"))
    out.append("</tv>")
    OUT.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"HARU KAI EPG: {len(programmes)} programmes / {len(used_channels)} channels -> {OUT}")


if __name__ == "__main__":
    main()
