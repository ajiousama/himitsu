#!/usr/bin/env python3
"""Standardize pre-start EPG for every public-sports channel visible in FreeWiFi."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone, time
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET

from sports_race_time import race_time

FREEWIFI = Path("freewifi")
GUIDES = Path("guides.xml")
LOCAL_EPG = Path("public_sports_epg_local.xml")
PUBLIC_STATUS = Path("today_public_sports_status.json")

JST = timezone(timedelta(hours=9))
TARGET_PREFIXES = ("keirin.", "chihou.", "auto.", "jra.")
MODE_LABEL = {
    "morning": "モーニング",
    "day": "デイ",
    "twilight": "薄暮",
    "night": "ナイター",
    "midnight": "ミッドナイト",
    "overnight": "オーバーミッドナイト",
}
PRESTART_RE = re.compile(r"^本日.+開催　1R\d{2}:\d{2}発走　")


def parse_xmltv(value: str | None) -> datetime | None:
    m = re.match(r"^(\d{14})\s*([+-]\d{4})?", str(value or "").strip())
    if not m:
        return None
    base = datetime.strptime(m.group(1), "%Y%m%d%H%M%S")
    off = m.group(2)
    if not off:
        return base.replace(tzinfo=JST)
    sign = 1 if off[0] == "+" else -1
    tz = timezone(sign * timedelta(hours=int(off[1:3]), minutes=int(off[3:5])))
    return base.replace(tzinfo=tz).astimezone(JST)


def xmltv(value: datetime) -> str:
    return value.astimezone(JST).strftime("%Y%m%d%H%M%S +0900")


def playlist_today_channels() -> dict[str, str]:
    if not FREEWIFI.exists():
        raise SystemExit("freewifi not found")
    channels = {}
    for line in FREEWIFI.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        if not line.startswith("#EXTINF:") or 'group-title="今日の開催場"' not in line:
            continue
        mid = re.search(r'tvg-id="([^"]+)"', line)
        if not mid or not mid.group(1).startswith(TARGET_PREFIXES):
            continue
        cid = mid.group(1)
        mname = re.search(r'tvg-name="([^"]+)"', line)
        name = mname.group(1) if mname else line.rsplit(",", 1)[-1].strip()
        channels[cid] = name
    return channels


def load_modes() -> dict[str, str]:
    try:
        data = json.loads(PUBLIC_STATUS.read_text(encoding="utf-8-sig"))
        return {
            cid: str(item.get("mode") or "")
            for cid, item in (data.get("channels") or {}).items()
            if isinstance(item, dict)
        }
    except Exception:
        return {}


def infer_mode(cid: str, programme: ET.Element, modes: dict[str, str]) -> str:
    if cid.startswith("jra."):
        return "day"
    mode = modes.get(cid)
    if mode in MODE_LABEL:
        return mode
    joined = " ".join([
        programme.findtext("title") or "",
        programme.findtext("desc") or "",
    ])
    if "オーバーミッドナイト" in joined:
        return "overnight"
    if "ミッドナイト" in joined:
        return "midnight"
    if "ナイター" in joined:
        return "night"
    if "モーニング" in joined:
        return "morning"
    if "薄暮" in joined:
        return "twilight"
    return "day"


def find_first_race(root: ET.Element, cid: str, today) -> tuple[ET.Element, dict] | None:
    found = []
    for p in root.findall("programme"):
        if p.get("channel") != cid:
            continue
        race = race_time(p)
        if race and race["day"] == today and race["race"] == 1:
            found.append((race["dt"], p, race))
    if not found:
        return None
    found.sort(key=lambda row: row[0])
    _dt, p, race = found[0]
    return p, race


def standardize_file(path: Path, visible: dict[str, str], modes: dict[str, str], now: datetime) -> int:
    if not path.exists() or path.stat().st_size == 0:
        return 0
    tree = ET.parse(path)
    root = tree.getroot()
    today = now.date()
    midnight = datetime.combine(today, time(0, 0), tzinfo=JST)
    changed = 0

    for cid, playlist_name in visible.items():
        result = find_first_race(root, cid, today)
        if not result:
            continue
        first_programme, race = result
        first_dt = race["dt"]
        if first_dt <= midnight:
            continue

        mode = infer_mode(cid, first_programme, modes)
        mode_label = MODE_LABEL.get(mode, "デイ")
        clean_name = re.sub(r"\s+(?:HQ|LQ)$", "", playlist_name).strip()
        clean_name = clean_name.replace("BOATRACE", "").strip() or playlist_name
        title = f"本日{clean_name}開催　1R{race['start']}発走　{mode_label}"

        # Give the standardized waiting programme the whole pre-start window.
        race_leadin = max(midnight, first_dt - timedelta(minutes=3))
        first_programme.set("start", xmltv(race_leadin))

        for p in list(root.findall("programme")):
            if p is first_programme or p.get("channel") != cid:
                continue
            ptitle = (p.findtext("title") or "").strip()
            pstart = parse_xmltv(p.get("start"))
            pstop = parse_xmltv(p.get("stop"))
            if PRESTART_RE.match(ptitle):
                root.remove(p)
                continue
            if pstart and pstop and pstart.date() == today and pstart < race_leadin and pstop > midnight:
                if race_time(p) is None:
                    root.remove(p)

        if race_leadin > midnight:
            wait = ET.Element("programme", {
                "channel": cid,
                "start": xmltv(midnight),
                "stop": xmltv(race_leadin),
            })
            ET.SubElement(wait, "title", {"lang": "ja"}).text = title
            ET.SubElement(wait, "desc", {"lang": "ja"}).text = (
                f"{clean_name}は本日開催です。\n"
                f"開催区分: {mode_label}\n"
                f"1R発走予定: {race['start']}"
            )
            root.append(wait)
            changed += 1

    channels = [el for el in list(root) if el.tag == "channel"]
    other = [el for el in list(root) if el.tag not in {"channel", "programme"}]
    programmes = [el for el in list(root) if el.tag == "programme"]
    programmes.sort(key=lambda p: (p.get("start", ""), p.get("channel", "")))
    root[:] = channels + other + programmes
    if hasattr(ET, "indent"):
        ET.indent(tree, space="  ")
    tree.write(path, encoding="utf-8", xml_declaration=True)
    return changed


def main() -> int:
    now = datetime.now(JST)
    visible = playlist_today_channels()
    modes = load_modes()
    total = 0
    for path in (LOCAL_EPG, GUIDES):
        changed = standardize_file(path, visible, modes, now)
        print(f"Prestart EPG standardized: {path} channels={changed}")
        total += changed
    print(f"FreeWiFi public-sports prestart total={total} visible_targets={len(visible)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
