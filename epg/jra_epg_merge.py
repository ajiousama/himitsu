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

    for el in list(root):
        cid = el.get("id") if el.tag == "channel" else el.get("channel") if el.tag == "programme" else ""
        if cid in TARGET:
            root.remove(el)

    for source, (base, display) in QUALITY.items():
        if not regional[source]:
            continue
        for quality, label in (("hq", "HQ"), ("lq", "LQ")):
            cid = f"{base}.{quality}"
            add_channel(root, cid, f"{display} {label}")
            for p in regional[source]:
                root.append(clone(p, cid))

    # Always create both XMLTV channel IDs, even if no race is scheduled.
    # MAIN HQ / 5002 / HARUKA share the HQ guide by design.
    schedule = build_gch_schedule(source_schedule, start, end)
    for quality, label in (("hq", "HQ"), ("lq", "LQ")):
        cid = f"jra.gch.{quality}"
        add_channel(root, cid, f"グリーンチャンネル MAIN {label}")
        for p in schedule:
            root.append(clone(p, cid))

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
