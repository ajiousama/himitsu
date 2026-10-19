#!/usr/bin/env python3
"""Maintain 101 approved newblog entries after existing FreeWiFi TV sources."""
from __future__ import annotations
import json, re
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "newblog/source.m3u"
CATALOG = ROOT / "newblog/channel_map.json"
TV = ROOT / "tv/playlist.m3u"
LABEL = "（newblog系）"
COUNT = 101

def get_source():
    metadata = json.loads(CATALOG.read_text(encoding="utf-8"))
    lines = SOURCE.read_text(encoding="utf-8-sig").splitlines()
    out = []
    for i, inf in enumerate(lines):
        if not inf.startswith("#EXTINF:"):
            continue
        if i + 1 >= len(lines):
            raise ValueError("Incomplete source")
        url = lines[i + 1].strip()
        p = urlsplit(url)
        m = re.fullmatch(r"/stream/jp/([\w+\-]+)/stream-output\.m3u8", p.path)
        if (p.scheme != "https" or p.hostname != "0i4neux01.charandom.blog"
                or not m or not parse_qs(p.query).get("ac_tk")):
            raise ValueError("Unexpected newblog URL")
        slug = m.group(1)
        if slug not in metadata or any(r[0] == slug for r in out):
            raise ValueError("Unknown or duplicate newblog station: " + slug)
        out.append((slug, metadata[slug], url))
    if len(out) != COUNT or set(r[0] for r in out) != set(metadata):
        raise ValueError("newblog 101-station registry mismatch")
    return out

def apply(text):
    lines = text.splitlines()
    kept = []
    i = 0
    while i < len(lines):
        if lines[i].startswith("#EXTINF:") and LABEL in lines[i]:
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i >= len(lines) or lines[i].startswith("#"):
                raise ValueError("Incomplete old newblog entry")
            i += 1
            continue
        kept.append(lines[i])
        i += 1
    lines = kept
    for slug, meta, uri in get_source():
        cat = "グリーンCh" if slug == "green_channel" else meta["category"]
        # Group labels are a protected user-facing FreeWiFi setting.
        # A source refresh must never merge newblog back into PH/5002 groups.
        group_title = ("今日の開催場" if cat == "グリーンCh" else
                       f"{cat} newblog系" if cat in {"地上波", "BS", "CS", "その他"} else cat)
        if cat == "Rch":
            continue
        start = {"地上波":"## 地上波", "BS":"## BS",
                 "グリーンCh":"# === GREEN_CHANNEL_PERSISTENT_START ===",
                 "CS":"## CS", "その他":"## CS"}[cat]
        end = {"地上波":"## BS", "BS":"# === GREEN_CHANNEL_PERSISTENT_START ===",
               "グリーンCh":"# === GREEN_CHANNEL_PERSISTENT_END ==="}.get(cat)
        a = lines.index(start)
        b = lines.index(end) if end else len(lines)
        if b <= a:
            raise ValueError("Invalid section")
        matches = [j for j in range(a + 1, b)
                   if lines[j].startswith("#EXTINF:")
                   and ('tvg-id="' + meta["id"] + '"') in lines[j]]
        at = matches[-1] + 2 if matches else b
        inf = ('#EXTINF:-1 tvg-id="' + meta["id"] + '" tvg-logo="'
               + meta["logo"] + '" group-title="' + group_title + '",'
               + meta["name"] + LABEL)
        lines[at:at] = ["", inf, uri]
    result = re.sub(r"\n{4,}", "\n\n\n", "\n".join(lines)).rstrip() + "\n"
    if result.count(LABEL) != COUNT - 2:
        raise ValueError("newblog row count incorrect")
    if "haru.charandom.blog" in result or ":9394/stream/" in result:
        raise ValueError("Retired HARUKA returned")
    return result

def inject_rch(body: str) -> str:
    """Place the 2 newblog Rch streams directly after their existing sources."""
    import re
    rows = {slug: (meta, uri) for slug, meta, uri in get_source()
            if slug in {"pigoo_nsfw", "nouvelle_paradise"}}
    if len(rows) != 2:
        raise ValueError("Missing newblog Rch records")
    ls = body.splitlines()
    kept = []
    i = 0
    while i < len(ls):
        if ls[i].startswith("#EXTINF:") and LABEL in ls[i]:
            i += 1
            while i < len(ls) and not ls[i].strip():
                i += 1
            if i >= len(ls) or ls[i].startswith("#"):
                raise ValueError("Incomplete newblog Rch record")
            i += 1
            continue
        kept.append(ls[i])
        i += 1
    ls = kept
    for slug in ("pigoo_nsfw", "nouvelle_paradise"):
        meta, uri = rows[slug]
        matches = [j for j, line in enumerate(ls)
                   if line.startswith("#EXTINF:")
                   and ('tvg-id="' + meta["id"] + '"') in line]
        if not matches:
            raise ValueError("Rch existing source missing for " + slug)
        j = matches[-1]
        insert = j + 2
        inf = ('#EXTINF:-1 tvg-id="' + meta["id"] + '" tvg-logo="'
               + meta["logo"] + '" group-title="Rch",'
               + meta["name"] + LABEL)
        ls[insert:insert] = ["", inf, uri]
    return re.sub(r"\n{4,}", "\n\n\n", "\n".join(ls)).strip() + "\n\n"

def main():
    current = TV.read_text(encoding="utf-8-sig")
    updated = apply(current)
    if current != updated:
        TV.write_text(updated, encoding="utf-8")
        print("newblog: restored all 101 sources into canonical TV")
    else:
        print("newblog: sources already current")

if __name__ == "__main__":
    main()
