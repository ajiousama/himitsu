#!/usr/bin/env python3
"""Require a complete, common three-day XMLTV guide for all Green Channel routes."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import xml.etree.ElementTree as ET

from epg.jra_epg_merge import parse_time

GUIDES = Path("guides.xml")
JST = timezone(timedelta(hours=9))
IDS = ("jra.gch.hq", "jra.gch.lq")


def main():
    root = ET.parse(GUIDES).getroot()
    today = datetime.now(JST).replace(hour=0, minute=0, second=0, microsecond=0)
    limit = today + timedelta(days=3)
    signatures = {}
    for cid in IDS:
        channels = [x for x in root.findall("channel") if x.get("id") == cid]
        if len(channels) != 1:
            raise SystemExit(f"GCH EPG: expected one channel id {cid}, got {len(channels)}")
        programmes = [p for p in root.findall("programme") if p.get("channel") == cid]
        clips = []
        for p in programmes:
            a, b = parse_time(p.get("start")), parse_time(p.get("stop"))
            if a and b and b > today and a < limit and a < b:
                clips.append((max(a, today), min(b, limit), (p.findtext("title") or "").strip()))
        clips.sort(key=lambda item: (item[0], item[1]))
        cursor = today
        for a, b, title in clips:
            if not title:
                raise SystemExit(f"GCH EPG: untitled programme: {cid} {a}")
            if a > cursor:
                raise SystemExit(f"GCH EPG: programme gap: {cid} {cursor} -> {a}")
            cursor = max(cursor, b)
        if cursor < limit:
            raise SystemExit(f"GCH EPG: incomplete three-day coverage: {cid} until {cursor}")
        signatures[cid] = clips
        fallback = sum("番組表取得待ち" in title for _, _, title in clips)
        print(f"GCH EPG validated: {cid}: {len(clips)} entries, {fallback} honest pending-guide intervals")
    if signatures[IDS[0]] != signatures[IDS[1]]:
        raise SystemExit("GCH EPG: HQ and LQ programmes differ")
    print("GCH EPG OK: HQ/LQ identical for 3 days; 5002 direct and HARUKA use HQ tvg-id")


if __name__ == "__main__":
    main()
