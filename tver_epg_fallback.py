#!/usr/bin/env python3
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

PLAYLIST = Path("freewifi")
GUIDE = Path("guides.xml")
JST = timezone(timedelta(hours=9))

ID_RE = re.compile(r'tvg-id="([^"]+)"')
GROUP_RE = re.compile(r'group-title="([^"]*)"')


def xmltv_time(dt):
    return dt.strftime("%Y%m%d%H%M%S +0900")


def tver_channels():
    out = {}
    for line in PLAYLIST.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        if not line.startswith("#EXTINF:"):
            continue
        mid = ID_RE.search(line)
        if not mid:
            continue
        tid = mid.group(1).strip()
        name = line.rsplit(",", 1)[-1].strip() if "," in line else tid
        grp = GROUP_RE.search(line)
        group = grp.group(1).strip() if grp else ""
        if tid.lower().startswith("tver_") or name.lower().startswith("tver") or group == "TVerﾘｱﾙﾀｲﾑ":
            out.setdefault(tid, name)
    return out


def main():
    if not PLAYLIST.exists() or not GUIDE.exists():
        raise SystemExit("freewifi or guides.xml missing")

    channels = tver_channels()
    if not channels:
        print("No TVer channels found")
        return

    tree = ET.parse(GUIDE)
    root = tree.getroot()
    existing_channels = {c.get("id") for c in root.findall("channel") if c.get("id")}
    programme_count = {}
    for p in root.findall("programme"):
        cid = p.get("channel")
        if cid:
            programme_count[cid] = programme_count.get(cid, 0) + 1

    now = datetime.now(JST)
    start_day = datetime(now.year, now.month, now.day, tzinfo=JST)
    added = []

    for tid, name in channels.items():
        # Real EPG exists -> leave it untouched.
        if programme_count.get(tid, 0) > 0:
            continue

        if tid not in existing_channels:
            ch = ET.SubElement(root, "channel", {"id": tid})
            ET.SubElement(ch, "display-name").text = name

        # One 23:59 programme per day, for the same 3-day horizon used by FreeWiFi.
        for d in range(3):
            st = start_day + timedelta(days=d)
            en = st + timedelta(hours=23, minutes=59)
            p = ET.SubElement(root, "programme", {
                "start": xmltv_time(st),
                "stop": xmltv_time(en),
                "channel": tid,
            })
            ET.SubElement(p, "title", {"lang": "ja"}).text = name
            ET.SubElement(p, "desc", {"lang": "ja"}).text = "TVer番組表を取得できないため、チャンネル名を23時間59分表示しています。"
            ET.SubElement(p, "category", {"lang": "ja"}).text = "TVer"
        added.append(tid)

    tree.write(GUIDE, encoding="utf-8", xml_declaration=True)
    print(f"TVer 23:59 fallback added: {len(added)} channel(s)")
    if added:
        print("  " + ", ".join(added))


if __name__ == "__main__":
    main()
