#!/usr/bin/env python3
"""Build an independent hybrid XMLTV guide for the 101 Cafe au lait channels.

Real schedules only: FreeWiFi -> J:COM -> Sky PerfecTV -> JapanTerebi (no direct Karenda dependency).
Rolling EPG: preserve the past 5 days and next 24 hours for catch-up navigation.
Sources are matched to Cafe au lait's existing, stable tvg-id values.
Never invent programme schedules or rewrite live/catch-up URLs.
"""
from __future__ import annotations

import copy
import gzip
import json
import re
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
NOW = datetime.now(JST)
CUTOFF = NOW - timedelta(days=5)
END = NOW + timedelta(hours=24)
M3U = Path("cafeaulait.m3u")
OUT = Path("cafeaulait_epg.xml")
REPORT = Path("cafeaulait_epg_report.txt")

SOURCES = [
    ("nhk_official", "https://api.nhk.jp/r8/pg/date/tv/130/{date}.json"),
    ("freewifi", None),
    ("jcom", "https://raw.githubusercontent.com/dbghelp/JCOM-TV-EPG/main/jcom.xml"),
    ("sky", "https://raw.githubusercontent.com/dbghelp/SKY-PerfecTV-EPG/main/perfectv.xml"),
    ("japanterebi", "https://animenosekai.github.io/japanterebi-xmltv/guide.xml"),
]

# Exact upstream XMLTV identifiers verified from provider channel listings.
# Keep the independent Cafe au lait tvg-id stable; clone upstream programmes to it.
PIN = {
    "me-tele_next": {"sky": ["CS301", "Ch.618"]},
    "abc": {"jcom": ["jcom_2_2072_32723"]},
    "kbs": {"jcom": ["jcom_2_42032_32102"]},
    "kansai_tv": {"jcom": ["jcom_2_2080_32724"]},
    "mbs": {"jcom": ["jcom_2_2064_32722"]},
    "nhk_g_osaka": {"jcom": ["jcom_2_40960_32112"]},
    "sun": {"jcom": ["jcom_2_43056_32086"]},
    "tv_osaka": {"jcom": ["jcom_2_41008_32118"]},
    "ytv": {"jcom": ["jcom_2_2088_32725"]},
    "fuji_tv_one": {"sky": ["CS307", "Ch.614"], "jcom": ["jcom_120_138_65406"]},
    "fuji_tv_two": {"sky": ["CS308", "Ch.615"]},
    "fuji_tv_next": {"sky": ["CS309", "Ch.613"]},
    "nouvelle_paradise": {"sky": ["Ch.535"], "karenda": ["ヌーヴェルパラダイス_jp"]},
    "pigoo_nsfw": {"sky": ["Ch.663"]},
    "kbs_world": {"sky": ["CS317", "Ch.656"]},
    "at-x": {"sky": ["CS333", "Ch.667"]},
    "action_channel": {"sky": ["CS311", "Ch.650"]},
    "mystery_channel": {"sky": ["CS316", "Ch.649"]},
    "tbs_channel_1": {"sky": ["CS296", "Ch.616"], "jcom": ["jcom_120_144_65406"]},
    "tbs_channel_2": {"sky": ["CS297", "Ch.617"], "jcom": ["jcom_120_176_65406"]},
    "tv_asahi_channel_1": {"sky": ["CS298", "Ch.611"]},
    "tv_asahi_channel_2": {"sky": ["CS299", "Ch.612"]},
    "nittele_plus": {"sky": ["CS300", "Ch.619"]},
    "the_cinema": {"sky": ["CS227", "Ch.631"]},
    "v_paradise_nsfw": {"sky": ["Ch.635"]},
    "bbc_news": {"sky": ["CS353", "Ch.565"]},
    "kntv": {"sky": ["Ch.657"]},
    "mnet": {"sky": ["CS318", "Ch.658"]},
    "bs11": {"jcom": ["jcom_3_211_4"]},
    "wowow_plus": {"sky": ["BS252", "Ch.630"], "jcom": ["jcom_120_155_65406"]},
    "music_on_tv": {"sky": ["CS325", "Ch.641"]},
}

ALIASES = {
    "tokyo_mx2": ["TOKYO MX2", "TOKYO・MX2"],
    "kbs": ["KBS京都"],
    "bs_12": ["BS12", "BS12 トゥエルビ"],
    "bs_yoshimoto": ["BSよしもと"],
    "bs10": ["BS10"],
    "bs11": ["BS11", "BSイレブン"],
    "wowow_plus": ["WOWOWプラス"],
    "at-x": ["AT-X", "アニメシアターX"],
    "action_channel": ["アクションチャンネル"],
    "bbc_news": ["BBCニュース"],
    "dlife": ["Dlife"],
    "fighting_tv_samurai": ["FIGHTING TV サムライ"],
    "fuji_tv_one": ["フジテレビONE", "フジテレビＯＮＥ スポーツ・バラエティ"],
    "fuji_tv_two": ["フジテレビTWO", "フジテレビＴＷＯ ドラマ・アニメ"],
    "kbs_world": ["KBS World", "KBS World 韓流専門チャンネル"],
    "kntv": ["KNTV"],
    "me-tele_next": ["メ～テレNEXT"],
    "mnet": ["Mnet"],
    "music_on_tv": ["MUSIC ON! TV", "M-ON!"],
    "mystery_channel": ["ミステリーチャンネル"],
    "neco_ch": ["映画・チャンネルNECO", "チャンネルNECO"],
    "nittele_plus": ["日テレプラス"],
    "nouvelle_paradise": ["大人のイキヌキ！ヌーヴェルパラダイス", "ヌーヴェルパラダイス"],
    "pigoo_nsfw": ["アイドル専門チャンネルPigoo", "Pigoo"],
    "sport_live_plus": ["スポーツライブ＋"],
    "tbs_channel_1": ["TBSチャンネル1"],
    "tbs_channel_2": ["TBSチャンネル2"],
    "tv_asahi_channel_1": ["テレ朝チャンネル1"],
    "tv_asahi_channel_2": ["テレ朝チャンネル2"],
    "the_cinema": ["ザ・シネマ"],
    "v_paradise_nsfw": ["V☆パラダイス"],
    "weather_news": ["ウェザーニュース"],
}

# Verified NHK public schedule service IDs (2026-11-11):
# s1 = NHK BS, s2 = NHK BS sub, s5 = NHK BSP4K.
# Keep these distinct: the FreeWiFi guide currently assigns BSP4K to NHK BS.
NHK_BS_SERVICES = {
    "nhk_bs": ("s1", "NHK・BS_jp", "NHK BS"),
    "nhk_bs_2": ("s2", "nhk_bs_2", "NHK BSサブ"),
    "nhk_bs4k": ("s5", "NHK・BSP_jp", "NHK BSP4K"),
}
OFFICIAL_GUIDE_MARK = "Cafe au lait hybrid XMLTV (NHK BS official s1/s2/s5)"

def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    return re.sub(r"[^0-9a-zぁ-んァ-ン一-龯]+", "", s)

def parse_time(s: str | None) -> datetime | None:
    if not s:
        return None
    m = re.match(r"^(\d{14})(?:\s*([+-]\d{4}))?", s.strip())
    if not m:
        return None
    try:
        raw = datetime.strptime(m.group(1) + (" " + m.group(2) if m.group(2) else ""),
                                "%Y%m%d%H%M%S %z" if m.group(2) else "%Y%m%d%H%M%S")
        if raw.tzinfo is None:
            raw = raw.replace(tzinfo=JST)
        return raw.astimezone(JST)
    except (ValueError, OverflowError):
        return None

def targets():
    rows = []
    lines = M3U.read_text(encoding="utf-8-sig").splitlines()
    for i, line in enumerate(lines[:-1]):
        if not line.startswith("#EXTINF:"):
            continue
        cid = re.search(r'tvg-id="([^"]+)"', line)
        slug = re.search(r"/stream/jp/([^/]+)/stream-output", lines[i + 1])
        if not cid or not slug:
            raise ValueError("Invalid Cafe au lait entry at line " + str(i + 1))
        rows.append((slug.group(1), cid.group(1), line.rsplit(",", 1)[-1]))
    if len(rows) != 101 or len({x[1] for x in rows}) != 101:
        raise ValueError("Expected 101 unique Cafe au lait channels")
    return rows

def source_priority(slug: str, name: str) -> int:
    if slug in {"abc", "kbs", "kansai_tv", "mbs", "nhk_g_osaka",
                "sun", "tv_osaka", "ytv"}:
        order = ["jcom", "freewifi", "sky", "japanterebi"]
    elif slug in {"nouvelle_paradise", "pigoo_nsfw", "fuji_tv_one", "fuji_tv_two"}:
        order = ["sky", "jcom", "freewifi", "japanterebi"]
    else:
        order = [x[0] for x in SOURCES]
    return order.index(name)

def nhk_bs_official_xmltv() -> ET.Element:
    """Convert NHK's public s1/s2/s5 timetable into verified XMLTV records."""
    root = ET.Element("tv")
    for service, tid, label in NHK_BS_SERVICES.values():
        channel = ET.SubElement(root, "channel", {"id": tid})
        ET.SubElement(channel, "display-name").text = label

    # NHK's dated timetable uses the 05:00 broadcast-day boundary.
    day = CUTOFF.date() - timedelta(days=1)
    end_day = END.date()
    seen = set()
    now_keys = set()
    while day <= end_day:
        url = f"https://api.nhk.jp/r8/pg/date/tv/130/{day.isoformat()}.json"
        req = urllib.request.Request(url, headers={"User-Agent": "CafeAuLait-EPG/1.1"})
        with urllib.request.urlopen(req, timeout=45) as response:
            payload = json.load(response)
        for service, tid, label in NHK_BS_SERVICES.values():
            data = payload.get(service)
            events = data.get("publication") if isinstance(data, dict) else None
            if not isinstance(events, list) or not events:
                raise ValueError(f"NHK official {service} has no schedule for {day}")
            declared = " ".join(
                str(x.get("broadcastDisplayName", ""))
                for x in data.get("publishedOn", [])
                if isinstance(x, dict)
            )
            expected = {"s1": "NHK BS", "s2": "NHK BSサブ", "s5": "NHK BSP4K"}[service]
            if expected not in declared:
                raise ValueError(f"NHK {service} identity changed: {declared!r}")
            for item in events:
                title = (item.get("name") or "").strip()
                start_raw, stop_raw = item.get("startDate"), item.get("endDate")
                if not title or not start_raw or not stop_raw:
                    continue
                st = datetime.fromisoformat(start_raw).astimezone(JST)
                en = datetime.fromisoformat(stop_raw).astimezone(JST)
                if en <= st or en <= CUTOFF or st >= END:
                    continue
                key = (tid, st, en, title)
                if key in seen:
                    continue
                seen.add(key)
                if st <= NOW < en:
                    now_keys.add(tid)
                p = ET.SubElement(root, "programme", {
                    "channel": tid,
                    "start": st.strftime("%Y%m%d%H%M%S %z"),
                    "stop": en.strftime("%Y%m%d%H%M%S %z"),
                })
                ET.SubElement(p, "title", {"lang": "ja"}).text = title
                desc = item.get("description") or item.get("detailedDescription")
                if desc:
                    ET.SubElement(p, "desc", {"lang": "ja"}).text = str(desc)
        day += timedelta(days=1)
    if len(now_keys) != len(NHK_BS_SERVICES):
        raise RuntimeError("Missing current NHK BS, BS sub or BSP4K schedule")
    return root


def read_source(name: str, url: str | None):
    if name == "nhk_official":
        return nhk_bs_official_xmltv()
    if url is None:
        data = Path("guides.xml").read_bytes()
    else:
        req = urllib.request.Request(url, headers={"User-Agent": "CafeAuLait-EPG/1.0"})
        with urllib.request.urlopen(req, timeout=45) as resp:
            data = resp.read()
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return ET.fromstring(data)

def programme_items(root: ET.Element, wanted: set[str]):
    by_id = defaultdict(list)
    for p in root.iter("programme"):
        cid = p.get("channel", "")
        if cid not in wanted:
            continue
        start, stop = parse_time(p.get("start")), parse_time(p.get("stop"))
        if not start or not stop or stop <= CUTOFF or start >= END or not (p.findtext("title") or "").strip():
            continue
        by_id[cid].append((start, stop, p))
    return by_id

def candidate_id(slug: str, tid: str, source: str, ids: set[str], names: dict[str, list[str]]) -> str | None:
    # NHK BS must not fall back to FreeWiFi's mislabeled BSP4K schedule.
    if slug in NHK_BS_SERVICES:
        return tid if source == "nhk_official" and tid in ids else None
    # Me-Tele NEXT is the renamed CS301 (not a similarly named channel).
    if slug == "me-tele_next" and source != "sky":
        return None
    # A provider-pinned ID takes precedence; never swap KBS for KBS World.
    for cid in PIN.get(slug, {}).get(source, []):
        if cid in ids:
            return cid
    if tid in ids:
        return tid
    # For known pinned providers, do not guess a similarly named channel.
    if source in PIN.get(slug, {}):
        return None
    for alias in [tid] + ALIASES.get(slug, []):
        matches = names.get(norm(alias), [])
        if len(matches) == 1:
            return matches[0]
    return None

def covered_seconds(programmes: list, begin: datetime, end: datetime) -> int:
    """Measure actual EPG coverage without counting overlapping schedules twice."""
    spans = sorted((max(st, begin), min(en, end))
                   for st, en, _ in programmes if st < end and en > begin)
    covered = 0
    cursor = begin
    for st, en in spans:
        if en <= cursor:
            continue
        covered += int((en - max(cursor, st)).total_seconds())
        cursor = en
    return covered

def score(slug: str, source: str, programmes: list) -> tuple[int, int, int, int, int]:
    current = any(st <= NOW < en for st, en, _ in programmes)
    near = covered_seconds(programmes, NOW, NOW + timedelta(hours=3))
    next_day = covered_seconds(programmes, NOW, NOW + timedelta(hours=24))
    return (int(current), near, next_day, -source_priority(slug, source), len(programmes))

def main():
    rows = targets()
    # Existing XMLTV is the history archive. Without it, a fresh upstream
    # feed (often only future programmes) cannot provide five days of history.
    history = defaultdict(list)
    if OUT.exists():
        try:
            old_root = ET.parse(OUT).getroot()
        except ET.ParseError as exc:
            raise RuntimeError(f"Refusing to overwrite unreadable Coffee EPG history: {exc}") from exc
        expected_ids = {tid for _, tid, _ in rows}
        old_nhk_verified = old_root.get("generator-info-name") == OFFICIAL_GUIDE_MARK
        nhk_ids = {item[1] for item in NHK_BS_SERVICES.values()}
        for old in old_root.iter("programme"):
            tid = old.get("channel")
            if tid not in expected_ids or not (old.findtext("title") or "").strip():
                continue
            # Never retain stale BSP4K programmes masquerading as regular NHK BS.
            if tid in nhk_ids and not old_nhk_verified:
                continue
            st, en = parse_time(old.get("start")), parse_time(old.get("stop"))
            if st and en and st < END and en > CUTOFF:
                history[tid].append((st, en, old))
        print("Retained historical programmes:", sum(map(len, history.values())), flush=True)
    options = defaultdict(list)
    errors = []
    for source, url in SOURCES:
        try:
            root = read_source(source, url)
            ids = set()
            names = defaultdict(list)
            for ch in root.iter("channel"):
                cid = ch.get("id")
                if not cid:
                    continue
                ids.add(cid)
                for display in [cid] + [x.text or "" for x in ch.findall("display-name")]:
                    key = norm(display)
                    if key and cid not in names[key]:
                        names[key].append(cid)
            chosen = {}
            for slug, tid, label in rows:
                cid = candidate_id(slug, tid, source, ids, names)
                if cid:
                    chosen[slug] = cid
            progs = programme_items(root, set(chosen.values()))
            for slug, tid, label in rows:
                cid = chosen.get(slug)
                if cid and progs.get(cid):
                    options[slug].append((score(slug, source, progs[cid]), source, cid, progs[cid]))
            print(source, "channels=", len(ids), "matched=", len(chosen),
                  "with_programmes=", sum(bool(progs.get(cid)) for cid in chosen.values()), flush=True)
            del root
        except Exception as exc:
            errors.append(f"{source}: {type(exc).__name__}: {exc}")
            print("SOURCE ERROR:", errors[-1], flush=True)

    # Fail closed: never publish a stale/mislabeled NHK guide or a blank Me-Tele NEXT.
    for required_slug in (*NHK_BS_SERVICES, "me-tele_next"):
        if not options[required_slug]:
            raise RuntimeError(f"Required verified EPG source missing: {required_slug}")
    doc = ET.Element("tv", {"generator-info-name": OFFICIAL_GUIDE_MARK,
                            "generator-info-url": "https://github.com/ajiousama/himitsu"})
    report = ["Cafe au lait EPG hybrid report", f"generated={NOW.isoformat()}",
              "Sources: NHK official s1/s2/s5, FreeWiFi, JCOM, Sky PerfectTV, JapanTerebi (no direct Karenda)",
              "Rolling guide: past 5 days and next 24 hours; historical programmes retained across builds",
              ""]
    now_count = history_count = matched = 0
    # XMLTV requires the channel elements BEFORE any programme elements.
    for slug, tid, label in rows:
        ch = ET.SubElement(doc, "channel", {"id": tid})
        ET.SubElement(ch, "display-name", {"lang": "ja"}).text = label
    for slug, tid, label in rows:
        opts = sorted(options[slug], key=lambda o: o[0], reverse=True)
        src = upstream = "none"
        chosen = []
        if opts:
            _, src, upstream, chosen = opts[0]
            matched += 1
        items = list(chosen)
        # Add real programmes from fallback EPG providers only for uncovered slots.
        # This avoids blank schedule gaps when the primary source is sparse.
        for _, fallback_source, fallback_id, fallback in opts[1:]:
            for st, en, p in fallback:
                if st >= END or en <= CUTOFF:
                    continue
                if any(st < existing_en and existing_st < en for existing_st, existing_en, _ in items):
                    continue
                items.append((st, en, p))
        # Prefer freshly fetched programmes; backfill only genuinely uncovered
        # intervals from previous successful EPG builds. Never invent a show.
        for st, en, old in history[tid]:
            if any(st < existing_en and existing_st < en for existing_st, existing_en, _ in items):
                continue
            items.append((st, en, old))
        seen = set()
        saved = current = historical = 0
        items.sort(key=lambda x: (x[0], x[1]))
        for st, en, p in items:
            key = (st, en)
            if key in seen or st >= END or en <= CUTOFF:
                continue
            seen.add(key)
            q = copy.deepcopy(p)
            q.set("channel", tid)
            doc.append(q)
            saved += 1
            if st <= NOW < en:
                current += 1
            if st < NOW:
                historical += 1
        now_count += int(bool(current))
        history_count += historical
        report.append(f"{slug}\t{tid}\t{src}\t{upstream}\tprogrammes={saved}\tnow={current}\tpast={historical}")

    report += ["", f"real_sources={matched}/101", f"current_programmes={now_count}/101",
               f"past_programmes={history_count}", "", "[source errors]", *(errors or ["none"])]
    if matched < 80:
        raise RuntimeError(f"Hybrid EPG build blocked: only {matched}/101 real channels. " + "; ".join(errors))
    ET.ElementTree(doc).write(OUT, encoding="utf-8", xml_declaration=True)
    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")
    verify = ET.parse(OUT).getroot()
    assert len(verify.findall("channel")) == 101
    assert all(p.get("channel") in {r[1] for r in rows} for p in verify.findall("programme"))
    print(f"WRITTEN {OUT}: {OUT.stat().st_size:,} bytes; matched={matched}/101, currently={now_count}/101", flush=True)

if __name__ == "__main__":
    main()
