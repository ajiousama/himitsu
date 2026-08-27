#!/usr/bin/env python3
import re
import urllib.request
from pathlib import Path

CONFIG = "https://www.nhk.or.jp/radio/config/config_web.xml"
OUT = Path("nhk_radio.m3u")

# NHK currently exposes regional R1/FM streams in config_web.xml.
# R2 ended in March 2026, so it is deliberately excluded.
def get_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")

def tag(block, name):
    m = re.search(rf"<{name}>\s*(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?\s*</{name}>", block, re.S)
    return re.sub(r"\s+", " ", m.group(1)).strip() if m else ""

def main():
    xml = get_text(CONFIG)
    entries = []
    for block in re.findall(r"<data>(.*?)</data>", xml, re.S):
        area = tag(block, "areajp")
        r1 = tag(block, "r1hls")
        fm = tag(block, "fmhls")
        if area and r1.startswith("http"):
            entries.append((f"NHKラジオ第1（{area}）", r1))
        if area and fm.startswith("http"):
            entries.append((f"NHK-FM（{area}）", fm))
    if not entries:
        raise SystemExit("No NHK radio streams found in config_web.xml")
    lines = ["#EXTM3U"]
    for name, url in entries:
        lines += [f'#EXTINF:-1 group-title="ラジオ",{name}', url]
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"wrote {OUT}: {len(entries)} channels")

if __name__ == "__main__":
    main()
