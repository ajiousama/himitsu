#!/usr/bin/env python3
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

CONFIG = "https://www.nhk.or.jp/radio/config/config_web.xml"
OUT = Path("radio.m3u")
LOGO = "https://upload.wikimedia.org/wikipedia/commons/b/bb/NHK_logo_2020.svg"

WANTED = ["札幌", "仙台", "東京", "名古屋", "大阪", "広島", "松山", "福岡"]
SLUG = {
    "札幌": "sapporo", "仙台": "sendai", "東京": "tokyo", "名古屋": "nagoya",
    "大阪": "osaka", "広島": "hiroshima", "松山": "matsuyama", "福岡": "fukuoka",
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


def build_entries(rows):
    entries = []
    for wanted in WANTED:
        area, (r1, fm) = choose_area(rows, wanted)
        if not area:
            continue
        slug = SLUG[wanted]
        if r1.startswith("http"):
            entries.append((f"nhk_r1_{slug}", f"NHKラジオ第1（{wanted}）", r1))
        if fm.startswith("http"):
            entries.append((f"nhk_fm_{slug}", f"NHK-FM（{wanted}）", fm))
    return entries


def preserved_non_nhk_lines():
    if not OUT.exists():
        return []
    lines = OUT.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    kept = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#EXTM3U"):
            i += 1
            continue
        if line.startswith("#EXTINF:") and ('tvg-id="nhk_r1_' in line or 'tvg-id="nhk_fm_' in line):
            i += 2 if i + 1 < len(lines) else 1
            continue
        kept.append(line)
        i += 1
    while kept and not kept[0].strip():
        kept.pop(0)
    while kept and not kept[-1].strip():
        kept.pop()
    return kept


def make_m3u(entries):
    lines = ["#EXTM3U"]
    for tvgid, name, url in entries:
        lines.append(f'#EXTINF:-1 tvg-id="{tvgid}" tvg-logo="{LOGO}" group-title="ラジオ",{name}')
        lines.append(url)
    preserved = preserved_non_nhk_lines()
    if preserved:
        lines.append("")
        lines.extend(preserved)
    return "\n".join(lines).rstrip() + "\n"


def main():
    rows = parse_config(get_text(CONFIG))
    entries = build_entries(rows)
    if len(entries) < 2:
        raise SystemExit("No usable NHK radio streams found in config_web.xml")
    OUT.write_text(make_m3u(entries), encoding="utf-8")
    print(f"wrote {OUT}: refreshed {len(entries)} NHK channels; FreeWiFi untouched")


if __name__ == "__main__":
    main()
