from __future__ import annotations

# Final post-merge repair for FreeWiFi XMLTV output.
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

EPG = Path("guides.xml")
PLAYLIST = Path("freewifi")
JST = timezone(timedelta(hours=9))
SPORT_PREFIXES = ("boat.", "keirin.", "chihou.", "auto.")
TVER_NEWS = {
    "Tver 日テレ NEWS24": "tver_ntv_news24",
    "Tver TBS NEWSDIG": "tver_tbs_newsdig",
}


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


def patch_tver_news_playlist() -> int:
    """Give TVer news-only streams stable tvg-id values.

    These two entries historically had no tvg-id at all, so players could not
    bind them to guides.xml even when the rest of the TV section was healthy.
    """
    if not PLAYLIST.exists():
        return 0
    text = PLAYLIST.read_text(encoding="utf-8-sig", errors="replace")
    lines = text.splitlines()
    changed = 0
    for i, line in enumerate(lines):
        if not line.startswith("#EXTINF:"):
            continue
        name = line.rsplit(",", 1)[-1].strip() if "," in line else ""
        tid = TVER_NEWS.get(name)
        if not tid or 'tvg-id="' in line:
            continue
        lines[i] = re.sub(r"^(#EXTINF:[^ ]+)", rf'\1 tvg-id="{tid}"', line, count=1)
        changed += 1
    if changed:
        PLAYLIST.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return changed


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


def _clone_programme_for_channel(p: ET.Element, cid: str) -> ET.Element:
    cp = ET.fromstring(ET.tostring(p, encoding="utf-8"))
    cp.set("channel", cid)
    return cp


def ensure_tver_news_epg(root: ET.Element) -> tuple[int, dict[str, int]]:
    """Populate the two TVer news rows instead of leaving them blank.

    NEWS24 can reuse the existing 日テレNEWS24 grid. NEWS DIG has no reliable
    programme grid in the TVer XML source, so use an explicit live-news guide
    rather than pretending it follows a different TBS schedule.
    """
    channel_nodes = {ch.get("id") for ch in root.findall("channel")}
    added: dict[str, int] = {}
    total = 0

    ntv_id = "tver_ntv_news24"
    if ntv_id not in channel_nodes:
        ch = ET.SubElement(root, "channel", {"id": ntv_id})
        ET.SubElement(ch, "display-name").text = "Tver 日テレ NEWS24"
        channel_nodes.add(ntv_id)
    existing_ntv = root.findall(f"programme[@channel='{ntv_id}']")
    if not existing_ntv:
        src = root.findall("programme[@channel='日テレNEWS24_jp']")
        for p in src:
            root.append(_clone_programme_for_channel(p, ntv_id))
        if src:
            added[ntv_id] = len(src)
            total += len(src)

    tbs_id = "tver_tbs_newsdig"
    if tbs_id not in channel_nodes:
        ch = ET.SubElement(root, "channel", {"id": tbs_id})
        ET.SubElement(ch, "display-name").text = "Tver TBS NEWSDIG"
        channel_nodes.add(tbs_id)
    if not root.findall(f"programme[@channel='{tbs_id}']"):
        now = datetime.now(JST)
        cursor = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_window = cursor + timedelta(days=4)
        count = 0
        while cursor < end_window:
            end = min(end_window, cursor + timedelta(hours=6))
            p = ET.SubElement(root, "programme", {"start": xmltv_time(cursor), "stop": xmltv_time(end), "channel": tbs_id})
            ET.SubElement(p, "title", {"lang": "ja"}).text = "TBS NEWS DIG｜ニュースライブ"
            ET.SubElement(p, "desc", {"lang": "ja"}).text = "TVerのTBS NEWS DIGライブ配信です。専用の番組表が公開されていないため、ライブニュース枠として表示しています。"
            ET.SubElement(p, "category", {"lang": "ja"}).text = "ニュース"
            count += 1
            cursor = end
        added[tbs_id] = count
        total += count

    # If the NEWS24 source EPG is ever unavailable, keep the row non-blank but
    # label it honestly as a live feed rather than borrowing another schedule.
    if not root.findall(f"programme[@channel='{ntv_id}']"):
        now = datetime.now(JST)
        cursor = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_window = cursor + timedelta(days=4)
        count = 0
        while cursor < end_window:
            end = min(end_window, cursor + timedelta(hours=6))
            p = ET.SubElement(root, "programme", {"start": xmltv_time(cursor), "stop": xmltv_time(end), "channel": ntv_id})
            ET.SubElement(p, "title", {"lang": "ja"}).text = "日テレ NEWS24｜ニュースライブ"
            ET.SubElement(p, "desc", {"lang": "ja"}).text = "TVerの日テレ NEWS24ライブ配信です。"
            ET.SubElement(p, "category", {"lang": "ja"}).text = "ニュース"
            count += 1
            cursor = end
        added[ntv_id] = count
        total += count

    return total, added


def main() -> int:
    if not EPG.exists() or not EPG.stat().st_size:
        raise RuntimeError("guides.xml is missing or empty")
    tver_bound = patch_tver_news_playlist()
    tree = ET.parse(EPG)
    root = tree.getroot()
    sports_fixed = repair_public_sports_first_race(root)
    catv_added, catv_detail = fill_catv_gaps(root)
    tver_added, tver_detail = ensure_tver_news_epg(root)
    ET.indent(root, space="  ")
    tree.write(EPG, encoding="utf-8", xml_declaration=True)
    print(
        f"EPG FINAL GUARD: sports_first_race_fixed={sports_fixed} "
        f"catv_gap_programmes={catv_added} {catv_detail} "
        f"tver_news_bound={tver_bound} tver_news_programmes={tver_added} {tver_detail}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())