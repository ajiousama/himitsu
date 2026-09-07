from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

EPG = Path("guides.xml")
PLAYLIST = Path("freewifi")
JST = timezone(timedelta(hours=9))
SPORT_PREFIXES = ("boat.", "keirin.", "chihou.", "auto.")


def parse_xmltv_time(value: str | None) -> datetime | None:
    if not value:
        return None
    m = re.match(r"^(\d{14})(?:\s*([+-]\d{4}))?", value.strip())
    if not m:
        return None
    stamp, offset = m.groups()
    try:
        if offset:
            return datetime.strptime(f"{stamp} {offset}", "%Y%m%d%H%M%S %z")
        return datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(tzinfo=JST)
    except ValueError:
        return None


def xmltv_time(dt: datetime) -> str:
    return dt.astimezone(JST).strftime("%Y%m%d%H%M%S +0900")


def parse_catv_channels() -> dict[str, str]:
    if not PLAYLIST.exists():
        return {}
    out: dict[str, str] = {}
    for line in PLAYLIST.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        if not line.startswith("#EXTINF:") or 'group-title="愛媛CATV"' not in line:
            continue
        mid = re.search(r'tvg-id="([^"]+)"', line)
        if not mid:
            continue
        name = line.rsplit(",", 1)[-1].strip() if "," in line else mid.group(1)
        out[mid.group(1).strip()] = name
    return out


def repair_public_sports_first_race(root: ET.Element) -> int:
    fixed = 0
    first_race = re.compile(r"【(?:１|1)(?:Ｒ|R)】.*?([0-2]?\d:[0-5]\d)発走")
    for p in root.findall("programme"):
        cid = p.get("channel") or ""
        if not cid.startswith(SPORT_PREFIXES):
            continue
        title = p.findtext("title") or ""
        m = first_race.search(title)
        if not m:
            continue
        start = parse_xmltv_time(p.get("start"))
        if start is None:
            continue
        hh, mm = map(int, m.group(1).split(":"))
        race = start.astimezone(JST).replace(hour=hh, minute=mm, second=0, microsecond=0)
        # Overnight meetings can cross midnight. If the listed race clock is
        # far behind the XML date/time, treat it as the following day.
        if race < start.astimezone(JST) - timedelta(hours=8):
            race += timedelta(days=1)
        desired = race - timedelta(minutes=20)
        # The old race-grid builder started 1R at 08:00 for every venue. Only
        # shorten obviously overlong first-race blocks; never push a legitimate
        # source programme later.
        if start < desired - timedelta(minutes=5):
            p.set("start", xmltv_time(desired))
            fixed += 1
    return fixed


def _add_catv_gap(root: ET.Element, cid: str, name: str, start: datetime, stop: datetime) -> int:
    count = 0
    cursor = start
    while cursor < stop:
        end = min(stop, cursor + timedelta(hours=6))
        p = ET.SubElement(
            root,
            "programme",
            {"start": xmltv_time(cursor), "stop": xmltv_time(end), "channel": cid},
        )
        title = f"📺 愛媛CATV｜{name}"
        category = "愛媛CATV"
        if cid == "ecatv.ainan_livecam":
            title = "📹 愛南ライブカメラ｜24時間LIVE"
            category = "ライブカメラ"
        ET.SubElement(p, "title", {"lang": "ja"}).text = title
        ET.SubElement(p, "desc", {"lang": "ja"}).text = (
            f"{name}。実番組表の空白時間を補完する案内表示です。映像チャンネル自体はそのまま利用できます。"
        )
        ET.SubElement(p, "category", {"lang": "ja"}).text = category
        count += 1
        cursor = end
    return count


def fill_catv_gaps(root: ET.Element) -> tuple[int, dict[str, int]]:
    channels = parse_catv_channels()
    if not channels:
        return 0, {}

    now = datetime.now(JST)
    window_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    window_end = window_start + timedelta(days=4)
    channel_nodes = {ch.get("id") for ch in root.findall("channel")}
    total = 0
    added: dict[str, int] = {}

    for cid, name in channels.items():
        if cid not in channel_nodes:
            ch = ET.SubElement(root, "channel", {"id": cid})
            ET.SubElement(ch, "display-name").text = name
            channel_nodes.add(cid)

        intervals: list[tuple[datetime, datetime]] = []
        for p in root.findall("programme"):
            if p.get("channel") != cid:
                continue
            st = parse_xmltv_time(p.get("start"))
            en = parse_xmltv_time(p.get("stop"))
            if st is None or en is None or en <= st:
                continue
            st, en = st.astimezone(JST), en.astimezone(JST)
            if en <= window_start or st >= window_end:
                continue
            intervals.append((max(st, window_start), min(en, window_end)))

        intervals.sort(key=lambda x: x[0])
        merged: list[list[datetime]] = []
        for st, en in intervals:
            if not merged or st > merged[-1][1] + timedelta(seconds=1):
                merged.append([st, en])
            elif en > merged[-1][1]:
                merged[-1][1] = en

        cursor = window_start
        count = 0
        for st, en in merged:
            if st > cursor + timedelta(minutes=1):
                count += _add_catv_gap(root, cid, name, cursor, st)
            if en > cursor:
                cursor = en
        if cursor < window_end - timedelta(minutes=1):
            count += _add_catv_gap(root, cid, name, cursor, window_end)

        if count:
            added[cid] = count
            total += count

    return total, added


def main() -> int:
    if not EPG.exists() or not EPG.stat().st_size:
        raise RuntimeError("guides.xml is missing or empty")
    tree = ET.parse(EPG)
    root = tree.getroot()
    sports_fixed = repair_public_sports_first_race(root)
    catv_added, catv_detail = fill_catv_gaps(root)
    ET.indent(root, space="  ")
    tree.write(EPG, encoding="utf-8", xml_declaration=True)
    print(f"EPG FINAL GUARD: sports_first_race_fixed={sports_fixed} catv_gap_programmes={catv_added} {catv_detail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
