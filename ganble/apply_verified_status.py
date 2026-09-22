"""Apply the official daily venue status to today's generated XMLTV."""

from __future__ import annotations

import datetime
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path


JST = datetime.timezone(datetime.timedelta(hours=9))
TODAY = datetime.datetime.now(JST).date()
DATE = TODAY.strftime("%Y%m%d")
EPG = Path("epg.xml")
STATUS = Path("/tmp/verified_daily_status.json")

NON_EVENT = "🚫💤 本日は開催していません 💤🚫"
ACTIVE_WAIT = "✅ 本日開催（各R情報取得待ち）"
BAD_MARKERS = ("本日は開催していません", "BOAT EPG診断", "開催情報確認待ち")

CATEGORY_LABEL = {
    "keirin": "競輪",
    "keiba": "地方競馬",
    "autorace": "オートレース",
    "boat": "ボートレース",
}


def parse_dt(value):
    m = re.match(r"(\d{14})\s*([+-]\d{4})?", str(value or ""))
    if not m:
        return None
    digits, offset = m.groups()
    if offset:
        return datetime.datetime.strptime(f"{digits} {offset}", "%Y%m%d%H%M%S %z").astimezone(JST)
    return datetime.datetime.strptime(digits, "%Y%m%d%H%M%S").replace(tzinfo=JST)


def fmt(dt):
    return dt.astimezone(JST).strftime("%Y%m%d%H%M%S +0900")


def programme(root, cid, start, stop, title, desc):
    p = ET.Element("programme", start=fmt(start), stop=fmt(stop), channel=cid)
    ET.SubElement(p, "title", lang="ja").text = title
    ET.SubElement(p, "desc", lang="ja").text = desc
    root.append(p)
    return p


def overlaps_today(p, start, stop):
    ps = parse_dt(p.get("start"))
    pe = parse_dt(p.get("stop"))
    return ps is not None and pe is not None and pe > start and ps < stop


def channel_name(root, cid):
    for ch in root.findall("channel"):
        if ch.get("id") == cid:
            return ch.findtext("display-name") or cid
    return cid


def set_karatsu_hiragana(root):
    changed = 0
    for ch in root.findall("channel"):
        if ch.get("id") != "boat.karatsu":
            continue
        dn = ch.find("display-name")
        if dn is None:
            dn = ET.SubElement(ch, "display-name")
        if dn.text != "BOATRACEからつ":
            dn.text = "BOATRACEからつ"
            changed += 1
    for p in root.findall("programme"):
        if p.get("channel") != "boat.karatsu":
            continue
        for node in (p.find("title"), p.find("desc")):
            if node is not None and node.text:
                new = node.text.replace("BOATRACE唐津", "BOATRACEからつ").replace("23 唐津", "23 からつ").replace("唐津", "からつ")
                if new != node.text:
                    node.text = new
                    changed += 1
    return changed


def apply_inactive(root, cid, category, day_start, day_end, source):
    for p in list(root.findall("programme")):
        if p.get("channel") == cid and overlaps_today(p, day_start, day_end):
            root.remove(p)
    name = channel_name(root, cid)
    for p in root.findall("programme"):
        if p.get("channel") != cid:
            continue
        ps, pe = parse_dt(p.get("start")), parse_dt(p.get("stop"))
        if ps is None or pe is None or pe != day_start:
            continue
        title = p.find("title")
        if title is not None and any(marker in (title.text or "") for marker in BAD_MARKERS):
            title.text = f"🔄 ただ今データ取得準備中です。 {name}（{category}）"
            desc = p.find("desc")
            if desc is None:
                desc = ET.SubElement(p, "desc", lang="ja")
            desc.text = "日付更新後の次回EPGデータ取得・反映を準備しています。"
    programme(
        root,
        cid,
        day_start,
        day_end,
        NON_EVENT,
        f"{source}で{TODAY:%Y年%m月%d日}の{category}開催なしを確認しました。\n{name}",
    )


def apply_active(root, cid, category, day_start, day_end, source):
    items = []
    for p in list(root.findall("programme")):
        if p.get("channel") != cid or not overlaps_today(p, day_start, day_end):
            continue
        title = p.findtext("title") or ""
        # False non-event, diagnostic, and synthetic gap programmes are rebuilt.
        if any(marker in title for marker in BAD_MARKERS):
            root.remove(p)
            continue
        start = max(parse_dt(p.get("start")), day_start)
        stop = min(parse_dt(p.get("stop")), day_end)
        if stop <= start:
            root.remove(p)
            continue
        p.set("start", fmt(start))
        p.set("stop", fmt(stop))
        items.append((start, stop, p))

    items.sort(key=lambda x: (x[0], x[1]))
    # Cut accidental overlaps without discarding the earlier programme.
    clean = []
    cursor = day_start
    for start, stop, p in items:
        start = max(start, cursor)
        if stop <= start:
            root.remove(p)
            continue
        p.set("start", fmt(start))
        p.set("stop", fmt(stop))
        clean.append((start, stop, p))
        cursor = stop

    name = channel_name(root, cid)
    gaps = []
    cursor = day_start
    for start, stop, _ in clean:
        if start > cursor:
            gaps.append((cursor, start))
        cursor = max(cursor, stop)
    if cursor < day_end:
        gaps.append((cursor, day_end))

    # Small gaps are presentation artefacts created by the three-minute switch.
    # Extending the preceding programme is cleaner than showing "unconfirmed"
    # even though the official daily index has confirmed the venue.
    for gap_start, gap_stop in gaps:
        following = next((p for s, e, p in clean if s == gap_stop), None)
        if following is not None and "終了しました" in (following.findtext("title") or ""):
            following.set("start", fmt(gap_start))
            continue
        previous = next((p for s, e, p in reversed(clean) if e == gap_start), None)
        if previous is not None and gap_stop - gap_start <= datetime.timedelta(minutes=15):
            previous.set("stop", fmt(gap_stop))
            continue
        programme(
            root,
            cid,
            gap_start,
            gap_stop,
            f"{ACTIVE_WAIT} {name}",
            f"{source}で本日の{category}開催を確認済みです。詳細番組の取得を待っています。",
        )


def collapse_confirmation_gaps(root):
    """Remove short synthetic confirmation gaps left by the v11 timeline pass."""
    changed = 0
    for p in list(root.findall("programme")):
        title = p.findtext("title") or ""
        if "開催情報確認待ち" not in title:
            continue
        start, stop = parse_dt(p.get("start")), parse_dt(p.get("stop"))
        if start is None or stop is None:
            continue
        same = [x for x in root.findall("programme") if x.get("channel") == p.get("channel") and x is not p]
        following = next((x for x in same if parse_dt(x.get("start")) == stop), None)
        if following is not None and "終了しました" in (following.findtext("title") or ""):
            following.set("start", fmt(start))
            root.remove(p)
            changed += 1
            continue
        if stop - start > datetime.timedelta(minutes=15):
            continue
        previous = next((x for x in same if parse_dt(x.get("stop")) == start), None)
        if previous is not None:
            previous.set("stop", fmt(stop))
            root.remove(p)
            changed += 1
    return changed


def main():
    if not STATUS.exists():
        raise SystemExit(f"Verified status is missing: {STATUS}")
    data = json.loads(STATUS.read_text(encoding="utf-8"))
    if data.get("date") != DATE:
        raise SystemExit(f"Verified status date mismatch: {data.get('date')} != {DATE}")

    tree = ET.parse(EPG)
    root = tree.getroot()
    day_start = datetime.datetime.combine(TODAY, datetime.time(8, 0), tzinfo=JST)
    day_end = datetime.datetime.combine(TODAY + datetime.timedelta(days=1), datetime.time(0, 0), tzinfo=JST)
    active_count = inactive_count = 0

    for key, info in data.get("categories", {}).items():
        if not info.get("verified"):
            print(f"APPLY {key}: unverified -> preserved")
            continue
        label = CATEGORY_LABEL.get(key, key)
        source = info.get("source") or "公式開催情報"
        for cid in info.get("inactive", []):
            apply_inactive(root, cid, label, day_start, day_end, source)
            inactive_count += 1
        for cid in info.get("active", []):
            apply_active(root, cid, label, day_start, day_end, source)
            active_count += 1

    karatsu_count = set_karatsu_hiragana(root)
    collapsed = collapse_confirmation_gaps(root)
    channels = [x for x in list(root) if x.tag == "channel"]
    programmes = [x for x in list(root) if x.tag == "programme"]
    programmes.sort(key=lambda p: (parse_dt(p.get("start")) or datetime.datetime.max.replace(tzinfo=JST), p.get("channel", "")))
    for node in list(root):
        root.remove(node)
    for node in channels + programmes:
        root.append(node)
    ET.indent(tree, space="    ")
    tree.write(EPG, encoding="utf-8", xml_declaration=True)
    print(f"Verified status applied: active={active_count} inactive={inactive_count} karatsu={karatsu_count} gaps={collapsed}")


if __name__ == "__main__":
    main()
