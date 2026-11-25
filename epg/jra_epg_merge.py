"""Merge JRA race cards without losing the always-on Green Channel EPG.

The MAIN HQ/LQ, PH (5002) and HARUKA rows in FreeWiFi share jra.gch.hq
(or jra.gch.lq for MAIN LQ).  They must be present every day regardless of
JRA/local/overseas race schedules.  Programme data comes from the actual
Green Channel XMLTV source when available, never from invented race coverage.
"""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import copy
import re
import xml.etree.ElementTree as ET

GUIDES = Path("guides.xml")
LOCAL = Path("public_sports_epg_local.xml")
REGIONAL = ("jra.east", "jra.west", "jra.hokkaido")
QUALITY = {
    "jra.east": ("jra.east", "JRA EAST WEB3"),
    "jra.west": ("jra.west", "JRA WEST WEB4"),
    "jra.hokkaido": ("jra.local", "JRA LOCAL WEB5"),
}
TARGET = {
    "jra.gch", "jra.east", "jra.west", "jra.hokkaido", "jra.local",
    "jra.official", "jra.gch.free", "jra.gch.hq", "jra.gch.lq",
}
for base, _ in QUALITY.values():
    TARGET |= {base + ".hq", base + ".lq"}

JST = timezone(timedelta(hours=9))
GCH_QUALITIES = ("jra.gch.hq", "jra.gch.lq")
GCH_LOGO = "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/public_sports/jra_quality/sinori.webp"
MISSING_MARKERS = (
    "番組詳細EPG未取得", "実EPG未対応", "番組表取得待ち",
    "実レースEPG取得失敗", "データ取得準備中",
)


def parse_time(value):
    match = re.match(r"^(\d{14})(?:\s*([+-]\d{4}))?", (value or "").strip())
    if not match:
        return None
    dt = datetime.strptime(match.group(1), "%Y%m%d%H%M%S")
    offset = match.group(2)
    if offset:
        sign = 1 if offset[0] == "+" else -1
        delta = timedelta(hours=int(offset[1:3]), minutes=int(offset[3:5]))
        return dt.replace(tzinfo=timezone(sign * delta)).astimezone(JST)
    return dt.replace(tzinfo=JST)


def xmltv_time(dt):
    return dt.strftime("%Y%m%d%H%M%S %z")


def add_channel(root, cid, name):
    ch = ET.SubElement(root, "channel", {"id": cid})
    ET.SubElement(ch, "display-name").text = name
    quality_logos = {"jra.gch.lq":"https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/public_sports/jra_quality/main_lq.webp","jra.east.hq":"https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/public_sports/jra_quality/east_hq.webp","jra.east.lq":"https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/public_sports/jra_quality/east_lq.webp","jra.west.hq":"https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/public_sports/jra_quality/west_hq.webp","jra.west.lq":"https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/public_sports/jra_quality/west_lq.webp","jra.local.hq":"https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/public_sports/jra_quality/local_hq.webp","jra.local.lq":"https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/public_sports/jra_quality/local_lq.webp"}
    # MAIN HQ and common-logo variants share a guide ID. Leave this XMLTV
    # icon absent so each M3U row retains its own logo.
    if cid in quality_logos:
        ET.SubElement(ch, "icon", {"src": quality_logos[cid]})


def clone(programme, channel):
    copied = copy.deepcopy(programme)
    copied.set("channel", channel)
    return copied


def real_gch(programme):
    text = " ".join(
        (programme.findtext("title") or "", programme.findtext("desc") or "")
    )
    return not any(marker in text for marker in MISSING_MARKERS)


def actual_gch_schedule(root, start, end):
    """Capture the true schedule BEFORE the EPG rebuild replaces GCH IDs."""
    by_id = {}
    for channel in root.findall("channel"):
        cid = channel.get("id") or ""
        name = " ".join(ch.text or "" for ch in channel.findall("display-name"))
        # Do not silently borrow Green Channel 2's separate programme service.
        if "グリーンチャンネル2" in (name + cid) or "GreenChannel2" in (name + cid):
            continue
        if cid in GCH_QUALITIES or "グリーンチャンネル" in name or cid == "グリーンチャンネル_jp":
            by_id[cid] = []
    for programme in root.findall("programme"):
        cid = programme.get("channel") or ""
        if cid not in by_id or not real_gch(programme):
            continue
        a, b = parse_time(programme.get("start")), parse_time(programme.get("stop"))
        if a and b and b > start and a < end and a < b:
            by_id[cid].append(programme)
    # Both quality versions should contain the same schedule. Prefer HQ, then LQ.
    # An unsuffixed original guide is a valid additional source.
    preferred = list(GCH_QUALITIES) + sorted(
        cid for cid in by_id if cid not in GCH_QUALITIES
    )
    for cid in preferred:
        if by_id.get(cid):
            return cid, by_id[cid]
    return None, []


def placeholder(start, stop):
    p = ET.Element("programme", {
        "start": xmltv_time(start),
        "stop": xmltv_time(stop),
    })
    ET.SubElement(p, "title", {"lang": "ja"}).text = "グリーンチャンネル｜番組表取得待ち"
    ET.SubElement(p, "desc", {"lang": "ja"}).text = (
        "番組情報を取得できていません。放送休止を意味する案内ではありません。"
    )
    ET.SubElement(p, "category", {"lang": "ja"}).text = "番組情報"
    return p


def build_gch_schedule(programmes, start, end):
    """Keep source programmes and cover only missing intervals with honest labels."""
    found = []
    seen = set()
    for p in programmes:
        a = parse_time(p.get("start"))
        b = parse_time(p.get("stop"))
        if not a or not b or a >= b or b <= start or a >= end:
            continue
        a, b = max(a, start), min(b, end)
        key = (a, b, (p.findtext("title") or "").strip())
        if key in seen:
            continue
        seen.add(key)
        cp = copy.deepcopy(p)
        cp.set("start", xmltv_time(a))
        cp.set("stop", xmltv_time(b))
        found.append((a, b, cp))
    found.sort(key=lambda row: (row[0], row[1]))
    result = []
    cursor = start
    for a, b, p in found:
        if a > cursor:
            result.append(placeholder(cursor, a))
        result.append(p)
        cursor = max(cursor, b)
    if cursor < end:
        result.append(placeholder(cursor, end))
    return result


JRA_VENUE_RE = re.compile(r"^JRA (東京|中山|新潟|福島|京都|阪神|中京|小倉|札幌|函館)(?:\s|$)")


def meeting_names_by_day(regional):
    """Derive meeting names only from dated, actual JRA race-card descriptions."""
    result = {}
    for cid in REGIONAL:
        for p in regional.get(cid, []):
            dt = parse_time(p.get("start"))
            match = JRA_VENUE_RE.match((p.findtext("desc") or "").strip())
            if dt and match:
                names = result.setdefault(dt.date(), [])
                if match.group(1) not in names:
                    names.append(match.group(1))
    return result


def regional_placeholder(start, stop, name, venues=()):
    """Describe confirmed meetings, not an unverified broadcast on this feed."""
    p = ET.Element("programme", {
        "start": xmltv_time(start),
        "stop": xmltv_time(stop),
    })
    if venues:
        title = "本日は" + "と".join(v + "競馬" for v in venues) + "を開催しています"
        desc = "確認済みの中央競馬開催場のご案内です。この枠の個別の放送内容・レース情報は未確認です。"
    else:
        title = "本日は中央競馬開催日｜開催場情報取得待ち"
        desc = "中央競馬の開催日は確認済みですが、開催場名を取得できていません。"
    ET.SubElement(p, "title", {"lang": "ja"}).text = title
    ET.SubElement(p, "desc", {"lang": "ja"}).text = desc
    return p


def regional_schedule_with_unknowns(programmes, race_days, name, venues_by_day=None):
    """Fill unassigned feed days and gaps with the confirmed meeting announcement."""
    out = list(programmes)
    venues_by_day = venues_by_day or {}
    for day in sorted(race_days):
        midnight = datetime.combine(day, datetime.min.time(), tzinfo=JST)
        next_day = midnight + timedelta(days=1)
        has_race = any(
            (dt := parse_time(p.get("start"))) and dt.date() == day
            and JRA_VENUE_RE.match((p.findtext("desc") or "").strip())
            for p in programmes
        )
        # A feed without race cards gets a full-day meeting announcement.
        # Keep assigned feeds' actual race cards and existing post-race notices.
        start = midnight + timedelta(hours=9) if has_race else midnight
        stop = midnight + timedelta(hours=17) if has_race else next_day
        intervals = []
        for p in programmes:
            a, b = parse_time(p.get("start")), parse_time(p.get("stop"))
            if a and b and a < stop and b > start:
                intervals.append((max(a, start), min(b, stop)))
        intervals.sort()
        cursor = start
        for a, b in intervals:
            if a > cursor:
                out.append(regional_placeholder(cursor, a, name, venues_by_day.get(day, ())))
            cursor = max(cursor, b)
        if cursor < stop:
            out.append(regional_placeholder(cursor, stop, name, venues_by_day.get(day, ())))
    return out


def main():
    if not GUIDES.exists() or not LOCAL.exists():
        raise SystemExit("guides/local JRA EPG missing")
    src = ET.parse(LOCAL).getroot()
    tree = ET.parse(GUIDES)
    root = tree.getroot()
    regional = {
        cid: [copy.deepcopy(p) for p in src.findall("programme") if p.get("channel") == cid]
        for cid in REGIONAL
    }
    now = datetime.now(JST)
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end = start + timedelta(days=3)
    source_id, source_schedule = actual_gch_schedule(root, start, end)
    # Capture real past metadata before replacing the shared GCH IDs.
    from epg.coffee_epg_history import merge_history
    previous_history = ET.Element('tv')
    for p in root.findall('programme'):
        if p.get('channel') in GCH_QUALITIES:
            previous_history.append(copy.deepcopy(p))

    venues_by_day = meeting_names_by_day(regional)

    # A race day keeps all WEB3/WEB4/WEB5 EPG channels, even if only
    # EAST and LOCAL have official race cards that day.
    race_days = {
        dt.date()
        for programmes in regional.values() for p in programmes
        if (dt := parse_time(p.get("start"))) and start <= dt < end
    }
    # Protect today's slot when a partial official JRA fetch failed.
    for source_file in ("today_jra_status.json", "verified_daily_status.json"):
        try:
            import json
            state = json.loads(Path(source_file).read_text(encoding="utf-8-sig"))
            state_date = (state.get("generated_at") or state.get("date") or "")[:10]
            valid = (state.get("jra_race_day") is True or
                     any(cid in REGIONAL for cid in state.get("jra_active_ids", [])))
            if state_date == now.date().isoformat() and valid:
                race_days.add(now.date())
        except (OSError, ValueError):
            pass

    for el in list(root):
        cid = el.get("id") if el.tag == "channel" else el.get("channel") if el.tag == "programme" else ""
        if cid in TARGET:
            root.remove(el)

    for source, (base, display) in QUALITY.items():
        if not regional[source] and not race_days:
            continue
        schedule = regional_schedule_with_unknowns(regional[source], race_days, display, venues_by_day)
        for quality, label in (("hq", "HQ"), ("lq", "LQ")):
            cid = f"{base}.{quality}"
            add_channel(root, cid, f"{display} {label}")
            for p in schedule:
                root.append(clone(p, cid))

    # Always create both XMLTV channel IDs, even if no race is scheduled.
    # MAIN HQ / 5002 / HARUKA share the HQ guide by design.
    schedule = build_gch_schedule(source_schedule, start, end)
    for quality, label in (("hq", "HQ"), ("lq", "LQ")):
        cid = f"jra.gch.{quality}"
        add_channel(root, cid, f"グリーンチャンネル MAIN {label}")
        for p in schedule:
            root.append(clone(p, cid))

    print('Coffee historical EPG:', merge_history(root, previous_history, now))

    # Keep the original common Green Channel guide icon.
    for ch in root.findall("channel"):
        if ch.get("id") == "グリーンチャンネル_jp":
            for icon in ch.findall("icon"):
                ch.remove(icon)
            ET.SubElement(ch, "icon", {"src": GCH_LOGO})
    ET.indent(tree, space="  ")
    tree.write(GUIDES, encoding="utf-8", xml_declaration=True)
    real = sum(real_gch(p) for p in schedule)
    fallback = len(schedule) - real
    print(
        "JRA race EPG:", {k: len(v) for k, v in regional.items()},
        "GCH always-on:", list(GCH_QUALITIES),
        "real schedule source:", source_id or "unavailable",
        "real programmes:", real,
        "missing intervals:", fallback,
        "days:", 3,
    )


if __name__ == "__main__":
    main()
