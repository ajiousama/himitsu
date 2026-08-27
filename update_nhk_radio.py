#!/usr/bin/env python3
import re
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

CONFIG = "https://www.nhk.or.jp/radio/config/config_web.xml"
OUT = Path("nhk_radio.m3u")
FREEWIFI = Path("freewifi")
START = "# === NHK_RADIO_MANAGED_START ==="
END = "# === NHK_RADIO_MANAGED_END ==="
LOGO = "https://upload.wikimedia.org/wikipedia/commons/b/bb/NHK_logo_2020.svg"

# 全国版として主要8地域を掲載。松山を必ず含める。
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
            v = e.text.strip()
            if v:
                return v
    return ""


def parse_config(xml):
    root = ET.fromstring(xml)
    rows = []
    for node in root.iter():
        # config_web.xml の地域ブロックは data 系。タグ名変更にも少し耐える。
        area = first_text(node, ["areajp", "area", "name"])
        if not area:
            continue
        r1 = first_text(node, ["r1hls", "r1", "r1_url", "r1url"])
        fm = first_text(node, ["fmhls", "fm", "fm_url", "fmurl"])
        if (r1.startswith("http") or fm.startswith("http")):
            rows.append((area, r1, fm))
    # 同一地域の重複を除去
    out = {}
    for area, r1, fm in rows:
        if area not in out or (r1 and fm):
            out[area] = (r1, fm)
    return out


def choose_area(rows, wanted):
    # 完全一致優先、次に部分一致（例: 東京・首都圏）
    if wanted in rows:
        return wanted, rows[wanted]
    for area, urls in rows.items():
        if wanted in area:
            return area, urls
    return None, ("", "")


def build_entries(rows):
    entries = []
    missing = []
    for wanted in WANTED:
        area, (r1, fm) = choose_area(rows, wanted)
        if not area:
            missing.append(wanted)
            continue
        slug = SLUG[wanted]
        if r1.startswith("http"):
            entries.append((f"nhk_r1_{slug}", f"NHKラジオ第1（{wanted}）", r1))
        if fm.startswith("http"):
            entries.append((f"nhk_fm_{slug}", f"NHK-FM（{wanted}）", fm))
    if missing:
        print("warning: regions not found:", ", ".join(missing))
    return entries


def make_m3u(entries):
    lines = ["#EXTM3U"]
    for tvgid, name, url in entries:
        lines.append(f'#EXTINF:-1 tvg-id="{tvgid}" tvg-logo="{LOGO}" group-title="ラジオ",{name}')
        lines.append(url)
    return "\n".join(lines) + "\n"


def inject_freewifi(entries):
    if not FREEWIFI.exists():
        raise SystemExit("freewifi not found")
    text = FREEWIFI.read_text(encoding="utf-8")
    body_lines = [START, "## NHKラジオ（公式らじる★らじる・地域別LIVE）"]
    for tvgid, name, url in entries:
        body_lines += [f'#EXTINF:-1 tvg-id="{tvgid}" tvg-logo="{LOGO}" group-title="ラジオ",{name}', url]
    body_lines.append(END)
    block = "\n".join(body_lines)

    pat = re.compile(rf"\n?{re.escape(START)}.*?{re.escape(END)}\n?", re.S)
    text = pat.sub("\n", text)

    # 一般YouTubeの直前に置き、無ければ末尾へ。
    marker = "# === GENERAL_YOUTUBE_MANAGED_START ==="
    if marker in text:
        text = text.replace(marker, block + "\n\n" + marker, 1)
    else:
        text = text.rstrip() + "\n\n" + block + "\n"
    FREEWIFI.write_text(text, encoding="utf-8")


def main():
    xml = get_text(CONFIG)
    rows = parse_config(xml)
    entries = build_entries(rows)
    if len(entries) < 2:
        raise SystemExit("No usable NHK radio streams found in config_web.xml")
    OUT.write_text(make_m3u(entries), encoding="utf-8")
    inject_freewifi(entries)
    print(f"wrote {OUT}: {len(entries)} channels; injected into freewifi")


if __name__ == "__main__":
    main()
