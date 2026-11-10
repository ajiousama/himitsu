#!/usr/bin/env python3
"""Build an independent hybrid XMLTV guide for the 101 Cafe au lait channels.

Real schedules only: FreeWiFi -> Karenda -> J:COM -> Sky PerfecTV -> JapanTerebi.
Live-only EPG: include only the last 2 hours and next 48 hours, with no catch-up history.
Sources are matched to Cafe au lait's existing, stable tvg-id values.
Never invent programme schedules or rewrite live/catch-up URLs.
"""
from __future__ import annotations

import copy
import gzip
import re
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

JST = timezone(timedelta(hours=9))
NOW = datetime.now(JST)
CUTOFF = NOW - timedelta(hours=2)
END = NOW + timedelta(days=2)
M3U = Path("cafeaulait.m3u")
OUT = Path("cafeaulait_epg.xml")
REPORT = Path("cafeaulait_epg_report.txt")

SOURCES = [
    ("freewifi", None),
    ("karenda", "https://raw.githubusercontent.com/karenda-jp/etc/main/guides.xml"),
    ("jcom", "https://raw.githubusercontent.com/dbghelp/JCOM-TV-EPG/main/jcom.xml"),
    ("sky", "https://raw.githubusercontent.com/dbghelp/SKY-PerfecTV-EPG/main/perfectv.xml"),
    ("japanterebi", "https://animenosekai.github.io/japanterebi-xmltv/guide.xml"),
]

# Exact upstream XMLTV identifiers verified from provider channel listings.
# Keep the independent Cafe au lait tvg-id stable; clone upstream programmes to it.
PIN = {
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
    "tbs_channel_1": {"sky": ["CS296", "Ch.616"]},
    "tbs_channel_2": {"sky": ["CS297", "Ch.617"]},
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
        order = ["jcom", "freewifi", "karenda", "sky", "japanterebi"]
    elif slug in {"nouvelle_paradise", "pigoo_nsfw", "fuji_tv_one", "fuji_tv_two"}:
        order = ["sky", "jcom", "karenda", "freewifi", "japanterebi"]
    else:
        order = [x[0] for x in SOURCES]
    return order.index(name)

def read_source(name: str, url: str | None):
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

    doc = ET.Element("tv", {"generator-info-name": "Cafe au lait hybrid XMLTV",
                            "generator-info-url": "https://github.com/ajiousama/himitsu"})
    report = ["Cafe au lait EPG hybrid report", f"generated={NOW.isoformat()}",
              "Sources: FreeWiFi, Karenda, JCOM, Sky PerfectTV, JapanTerebi",
              "Live-only: last 2 hours and next 48 hours; no six-day catch-up history",
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
    if matched < 20:
        raise RuntimeError(f"Hybrid EPG build blocked: only {matched}/101 real channels. " + "; ".join(errors))
    ET.ElementTree(doc).write(OUT, encoding="utf-8", xml_declaration=True)
    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")
    verify = ET.parse(OUT).getroot()
    assert len(verify.findall("channel")) == 101
    assert all(p.get("channel") in {r[1] for r in rows} for p in verify.findall("programme"))
    print(f"WRITTEN {OUT}: {OUT.stat().st_size:,} bytes; matched={matched}/101, currently={now_count}/101", flush=True)

if __name__ == "__main__":
    main()
