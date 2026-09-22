#!/usr/bin/env python3
import json
import os
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

CONFIG = "https://www.nhk.or.jp/radio/config/config_web.xml"
ROOT = Path("radio")
OUT = ROOT / "nhk.m3u"
MAP = ROOT / "nhk_stations.json"
LOGO = "https://upload.wikimedia.org/wikipedia/commons/b/bb/NHK_logo_2020.svg"
VIDEO_BASE = os.environ.get("RADIO_VIDEO_BASE", "https://ajiousama-radiko.onrender.com/radio-tv").rstrip("/")

WANTED = ["札幌", "仙台", "東京", "名古屋", "大阪", "広島", "松山", "福岡"]
SLUG = {
    "札幌": "sapporo", "仙台": "sendai", "東京": "tokyo", "名古屋": "nagoya",
    "大阪": "osaka", "広島": "hiroshima", "松山": "matsuyama", "福岡": "fukuoka",
}
DISPLAY = {
    "札幌": "SAPPORO", "仙台": "SENDAI", "東京": "TOKYO", "名古屋": "NAGOYA",
    "大阪": "OSAKA", "広島": "HIROSHIMA", "松山": "MATSUYAMA", "福岡": "FUKUOKA",
}

def get_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")

def local(tag):
    return tag.rsplit("}", 1)[-1].lower()

def first_text(node, names):
    names = {x.lower() for x in names}
    for e in node.iter():
        if local(e.tag) in names and e.text:
            value = e.text.strip()
            if value:
                return value
    return ""

def parse_config(xml):
    root = ET.fromstring(xml)
    rows = []
    for node in root.iter():
        area = first_text(node, ["areajp", "area", "name"])
        if not area:
            continue
        r1 = first_text(node, ["r1hls", "r1", "r1_url", "r1url"])
        fm = first_text(node, ["fmhls", "fm", "fm_url", "fmurl"])
        if r1.startswith("http") or fm.startswith("http"):
            rows.append((area, r1, fm))
    out = {}
    for area, r1, fm in rows:
        if area not in out or (r1 and fm):
            out[area] = (r1, fm)
    return out

def choose_area(rows, wanted):
    if wanted in rows:
        return wanted, rows[wanted]
    for area, urls in rows.items():
        if wanted in area:
            return area, urls
    return None, ("", "")

def main():
    rows = parse_config(get_text(CONFIG))
    stations = []
    m3u = ["#EXTM3U", "", "## NHKラジオ（静止画動画）"]

    for wanted in WANTED:
        area, (r1, fm) = choose_area(rows, wanted)
        if not area:
            continue
        slug = SLUG[wanted]
        for kind, source in (("r1", r1), ("fm", fm)):
            if not source.startswith("http"):
                continue
            tvgid = f"nhk_{kind}_{slug}"
            if kind == "r1":
                name = f"NHKラジオ第1（{wanted}）"
                display = f"NHK RADIO 1 {DISPLAY[wanted]}"
            else:
                name = f"NHK-FM（{wanted}）"
                display = f"NHK FM {DISPLAY[wanted]}"
            stations.append({
                "id": tvgid, "kind": kind, "slug": slug, "name": name,
                "display": display, "url": source,
            })
            video = f"{VIDEO_BASE}/{urllib.parse.quote(tvgid, safe='')}"
            m3u.append(
                f'#EXTINF:-1 tvg-id="{tvgid}" tvg-logo="{LOGO}" '
                f'group-title="NHKラジオ",{name}'
            )
            m3u.append(video)

    if len(stations) < 16:
        raise SystemExit(f"NHK station map too small: {len(stations)}")

    ROOT.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(m3u).rstrip() + "\n", encoding="utf-8")
    MAP.write_text(json.dumps({"version": 1, "stations": stations}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"NHK static-image video playlist: {len(stations)} stations -> {OUT}")

if __name__ == "__main__":
    main()
