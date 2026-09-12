#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
import re
import urllib.request
import xml.etree.ElementTree as ET

CHANNEL_ID = "youtube.ehime_mandarin"
CHANNEL_NAME = "愛媛マンダリンパイレーツ"
SCHEDULE_URL = "https://www.m-pirates.jp/schedule"
EPG_PATH = Path("public_sports_epg_local.xml")
PLAYLISTS = (Path("general_youtube.m3u"), Path("freewifi"))
JST = timezone(timedelta(hours=9))
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"

OPPONENTS = (
    "福岡ソフトバンクホークス（三軍）",
    "福岡ソフトバンクホークス(三軍)",
    "徳島インディゴソックス",
    "高知ファイティングドッグス",
    "香川オリーブガイナーズ",
)


def live_present() -> bool:
    needle = f'tvg-id="{CHANNEL_ID}"'
    return any(
        p.exists() and needle in p.read_text(encoding="utf-8-sig", errors="replace")
        for p in PLAYLISTS
    )


def fetch_schedule_text() -> str:
    req = urllib.request.Request(SCHEDULE_URL, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=20) as r:
        html = r.read().decode("utf-8", "replace")
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    text = unescape(re.sub(r"<[^>]+>", " ", html))
    return re.sub(r"\s+", " ", text)


def today_game(now: datetime):
    text = fetch_schedule_text()
    key = now.strftime("%Y.%m.%d")
    pos = text.find(key)
    if pos < 0:
        return None
    segment = text[pos:pos + 700]
    tm = re.search(r"\b([0-2]\d:[0-5]\d)\b", segment)
    if not tm:
        return None
    opponent = next((x for x in OPPONENTS if x in segment), None)
    if not opponent:
        return None
    start_h, start_m = map(int, tm.group(1).split(":"))
    start = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
    # Baseball broadcasts commonly continue beyond 3 hours; keep EPG open for 4 hours.
    stop = start + timedelta(hours=4)
    after_time = segment[tm.end():]
    opp_pos = after_time.find(opponent)
    venue = re.sub(r"\s+", " ", after_time[:opp_pos]).strip(" -|・") if opp_pos >= 0 else ""
    venue = venue[:80] or "愛媛県内球場"
    return start, stop, venue, opponent


def fmt(dt: datetime) -> str:
    return dt.strftime("%Y%m%d%H%M%S %z")


def ensure_epg(game) -> bool:
    if not EPG_PATH.exists() or EPG_PATH.stat().st_size == 0:
        root = ET.Element("tv", {"generator-info-name": "ajiousama/himitsu local public sports EPG"})
        tree = ET.ElementTree(root)
    else:
        tree = ET.parse(EPG_PATH)
        root = tree.getroot()

    changed = False
    if not any(x.get("id") == CHANNEL_ID for x in root.findall("channel")):
        ch = ET.Element("channel", {"id": CHANNEL_ID})
        ET.SubElement(ch, "display-name").text = CHANNEL_NAME
        # Keep channels before programmes.
        first_prog = next((i for i, x in enumerate(list(root)) if x.tag == "programme"), len(root))
        root.insert(first_prog, ch)
        changed = True

    # Rebuild only this channel's programme entries; other sports remain untouched.
    for prog in list(root.findall("programme")):
        if prog.get("channel") == CHANNEL_ID:
            root.remove(prog)
            changed = True

    if game:
        start, stop, venue, opponent = game
        prog = ET.SubElement(root, "programme", {
            "start": fmt(start),
            "stop": fmt(stop),
            "channel": CHANNEL_ID,
        })
        ET.SubElement(prog, "title", {"lang": "ja"}).text = f"愛媛MP vs {opponent}"
        ET.SubElement(prog, "desc", {"lang": "ja"}).text = f"{venue} / 愛媛マンダリンパイレーツ公式YouTube LIVE"
        ET.SubElement(prog, "category", {"lang": "ja"}).text = "野球"
        changed = True

    ET.indent(tree, space="  ")
    tree.write(EPG_PATH, encoding="utf-8", xml_declaration=True)
    return changed


def main() -> None:
    now = datetime.now(JST)
    if not live_present():
        # No current official LIVE entry: remove stale Mandarin programme, but keep the channel definition.
        ensure_epg(None)
        print("Mandarin LIVE not present; stale programme removed.")
        return
    game = today_game(now)
    if game is None:
        print("Mandarin LIVE is present but today's official schedule entry was not found; EPG left without a guessed programme.")
        ensure_epg(None)
        return
    ensure_epg(game)
    start, stop, venue, opponent = game
    print(f"Mandarin EPG: {start:%Y-%m-%d %H:%M} {venue} vs {opponent} -> {stop:%H:%M}")


if __name__ == "__main__":
    main()
