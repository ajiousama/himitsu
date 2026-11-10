#!/usr/bin/env python3
"""Sync Cafe au lait's 101 M3U tvg-id attributes to EXISTING Karenda/ajiousama XMLTV IDs.

Unlike the old hybrid EPG, we never republish or rename XMLTV programmes.
The TV player loads the two original XMLTV guide feeds directly.
"""
from __future__ import annotations

import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_epg import ALIASES, NOW, norm, programme_items, read_source

M3U = Path("cafeaulait.m3u")
REPORT = Path("cafeaulait_direct_epg_report.txt")
KARENDA = "https://raw.githubusercontent.com/karenda-jp/etc/main/guides.xml"
AJIOUSAMA = "https://raw.githubusercontent.com/ajiousama/himitsu/main/guides.xml"
HEADER = f'#EXTM3U url-tvg="{KARENDA},{AJIOUSAMA}" tvg-shift=0 m3uautoload=1'

# Verified / existing identifiers found in Yovi or from Karenda/ajiousama guide mappings.
# Candidates are accepted ONLY if the referenced guide actually declares the ID.
EXACT = {
    "tokyo_mx2": ["TOKYO・MX2_jp"],
    "abc": ["ABCテレビ_jp"],
    "kbs": ["KBS京都_jp"],
    "kansai_tv": ["関西テレビ_jp"],
    "mbs": ["毎日テレビ_jp", "毎日放送_jp"],
    "nhk_g_osaka": ["NHK大阪・総合_jp"],
    "sun": ["サンテレビ_jp"],
    "tv_osaka": ["テレビ大阪_jp"],
    "ytv": ["読売テレビ_jp"],
    "bs11": ["BS11-イレブン_jp"],
    "at-x": ["AT-X_jp", "AT-X"],
    "dlife": ["Dlife.jp", "Dlife_jp"],
    "fuji_tv_one": ["フジテレビONE_jp"],
    "fuji_tv_two": ["フジテレビTWO_jp"],
    "kntv": ["KNTV_jp"],
    "music_on_tv": ["MUSIC ON! TV_jp"],
    "ntv_news24": ["tver.news24", "日テレNEWS24_jp"],
    "pigoo_nsfw": ["Pigoo_jp", "Pigoo"],
    "v_paradise_nsfw": ["V☆パラダイス_jp"],
    "kbs_world": ["KBS-WORLD_jp"],
    "weather_news": ["ウェザーニュース_jp"],
}


def index_channels(root):
    ids = set()
    names = defaultdict(list)
    for ch in root.iter("channel"):
        cid = ch.get("id")
        if not cid:
            continue
        ids.add(cid)
        for item in [cid] + [v.text or "" for v in ch.findall("display-name")]:
            key = norm(item)
            if key and cid not in names[key]:
                names[key].append(cid)
    return ids, names


def locate(slug, current_id, ids, names):
    for exact in EXACT.get(slug, []):
        if exact in ids:
            return exact
    # Do not match ambiguous short names such as KBS against KBS World.
    candidates = ALIASES.get(slug, [])[:]
    if slug not in {"kbs", "kbs_world", "nhk_bs_2"}:
        candidates.insert(0, current_id)
    for alias in candidates:
        if alias in ids:
            return alias
        matches = names.get(norm(alias), [])
        if len(matches) == 1:
            return matches[0]
    return None


def main():
    lines = M3U.read_text(encoding="utf-8-sig").splitlines()
    rows = []
    for pos, line in enumerate(lines[:-1]):
        if not line.startswith("#EXTINF:"):
            continue
        slug_match = re.search(r"/stream/jp/([^/]+)/stream-output", lines[pos + 1])
        id_match = re.search(r'tvg-id="([^"]+)"', line)
        if not slug_match or not id_match:
            raise ValueError(f"Invalid channel at line {pos+1}")
        rows.append((pos, slug_match.group(1), id_match.group(1)))
    if len(rows) != 101 or len({slug for _, slug, _ in rows}) != 101:
        raise ValueError("Expected 101 distinct Coffee channels")
    live_urls = [lines[p+1] for p, _, _ in rows]
    if any('catchup=' in lines[p] or 'catchup-source=' in lines[p] for p, _, _ in rows):
        raise ValueError("Catch-up must stay disabled")

    found = defaultdict(dict)
    provider_counts = {}
    for name, url in [("karenda", KARENDA), ("ajiousama", None)]:
        root = read_source(name, url)
        ids, names = index_channels(root)
        candidate = {}
        for pos, slug, current_id in rows:
            cid = locate(slug, current_id, ids, names)
            if cid is not None:
                candidate[slug] = cid
        schedules = programme_items(root, set(candidate.values()))
        for slug, cid in candidate.items():
            if schedules.get(cid):
                found[slug][name] = (cid, len(schedules[cid]))
        provider_counts[name] = (len(ids), len(candidate), sum(bool(schedules.get(cid)) for cid in candidate.values()))
        print(name, "indexed / matched / with programmes =", provider_counts[name], flush=True)
        del root

    new_ids = []
    records = []
    for pos, slug, current_id in rows:
        if "karenda" in found[slug]:
            source = "karenda"
        elif "ajiousama" in found[slug]:
            source = "ajiousama"
        else:
            source = "none"
        cid, count = found[slug][source] if source != "none" else (current_id, 0)
        new_ids.append(cid)
        records.append((slug, source, cid, count))
        lines[pos] = re.sub(r'tvg-id="[^"]+"', lambda _m: f'tvg-id="{cid}"', lines[pos], count=1)

    if len(set(new_ids)) != 101:
        raise ValueError("Duplicate XMLTV IDs after aligning to upstream guides")
    supported = sum(source != "none" for _, source, _, _ in records)
    if supported < 80:
        raise RuntimeError(f"Refusing to publish weak XMLTV mapping: {supported}/101")
    lines[0] = HEADER
    for n, line in enumerate(lines):
        if line.startswith("# EPG IDs:"):
            lines[n] = "# EPG IDs: existing upstream Karenda/ajiousama guides, no proprietary XMLTV."
    if [lines[p+1] for p, _, _ in rows] != live_urls:
        raise AssertionError("Stream URLs changed unexpectedly")
    M3U.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report = [
        "Café au lait DIRECT EPG mapping report",
        f"generated={NOW.isoformat()}",
        f"epg_urls={KARENDA},{AJIOUSAMA}",
        f"supported={supported}/101",
        "Source priority: Karenda -> ajiousama/FreeWiFi. Source IDs are copied unchanged.",
        "",
        "slug\tsource\ttvg_id\tprogrammes",
    ]
    report += [f"{slug}\t{src}\t{cid}\t{count}" for slug, src, cid, count in records]
    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")
    print("DIRECT EPG MAPPING:", supported, "/101; unmapped:",
          [slug for slug, src, _, _ in records if src == "none"], flush=True)


if __name__ == "__main__":
    main()
