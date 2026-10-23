#!/usr/bin/env python3
"""Fail scheduled updates if FreeWiFi/Yovi TV source ownership reverts."""
from pathlib import Path
import re

BASE = Path(__file__).resolve().parent.parent
EXPECTED_SHINORI = 66
EXPECTED_YOITV = 75


def entries(filename):
    lines = (BASE / filename).read_text(encoding="utf-8-sig").splitlines()
    result = []
    for i, line in enumerate(lines):
        if not line.startswith("#EXTINF:"):
            continue
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        url = lines[j].strip() if j < len(lines) else ""
        match = re.search(r'tvg-id="([^"]+)"', line)
        result.append((match.group(1) if match else "", line, url))
    return result


def validate():
    free = entries("freewifi")
    canonical = entries("tv/playlist.m3u")
    yovi = entries("yovi")
    rakuten = entries("rakuten/playlist.m3u")

    for name, rows in (
        ("freewifi", free),
        ("tv/playlist.m3u", canonical),
        ("rakuten/playlist.m3u", rakuten),
    ):
        leaked = [tag for _id, tag, url in rows
                  if "/tv/yoitv.php" in url or "(YoiTV)" in tag]
        if leaked:
            raise SystemExit(f"{name}: YoiTV was restored ({len(leaked)} entries)")

    if any("ri.shinori.my.id/" in url for _id, _tag, url in yovi):
        raise SystemExit("yovi: Shinori was restored")

    source_maps = []
    for name, rows in (("freewifi", free), ("tv/playlist.m3u", canonical)):
        seen = {}
        for i, (channel_id, tag, url) in enumerate(rows):
            if "ri.shinori.my.id/" not in url:
                continue
            if channel_id in seen:
                raise SystemExit(f"{name}: duplicate Shinori {channel_id}")
            seen[channel_id] = url
            if i == 0:
                raise SystemExit(f"{name}: unanchored Shinori {channel_id}")
            previous_id, previous_tag, _previous_url = rows[i - 1]
            if previous_id != channel_id or "（newblog系）" not in previous_tag:
                raise SystemExit(f"{name}: Shinori is not directly after newblog: {channel_id}")
        if len(seen) != EXPECTED_SHINORI:
            raise SystemExit(f"{name}: expected {EXPECTED_SHINORI} Shinori entries, got {len(seen)}")
        source_maps.append(seen)
    if source_maps[0] != source_maps[1]:
        raise SystemExit("freewifi/canonical: Shinori IDs or URLs differ")

    count_yovi = sum("/tv/yoitv.php" in url for _id, _tag, url in yovi)
    if count_yovi < EXPECTED_YOITV:
        raise SystemExit(f"yovi: YoiTV shrank below {EXPECTED_YOITV}: {count_yovi}")

    # Yovi's former 29 rows contained 11 exact-URL duplicates, deliberately
    # removed on 2026-10-22. Protect the 18 distinct remaining streams instead
    # of blocking refreshes or restoring deleted duplicates.
    for name, rows, minimum in (
        ("freewifi", free, 49),
        ("tv/playlist.m3u", canonical, 48),
        ("yovi", yovi, 18),
    ):
        urls = [url for _id, _tag, url in rows if ":5002/" in url]
        unique = len(set(urls))
        if unique < minimum:
            raise SystemExit(f"{name}: unique 5002 URLs shrank below {minimum}: {unique}")
        if name == "yovi" and len(urls) != unique:
            raise SystemExit(f"yovi: {len(urls) - unique} duplicate 5002 URLs were restored")

    required_gch = ["グリーンチャンネル (5002直)", "グリーンチャンネル（newblog系）",
                    "グリーンチャンネル（sinori）"]
    for label in required_gch:
        if not any(tag.rsplit(",", 1)[-1] == label for _id, tag, _url in free):
            raise SystemExit(f"freewifi: required GCH source missing: {label}")

    print(f"TV SOURCE PARTITION OK: FreeWiFi Shinori={len(source_maps[0])}, "
          f"YoiTV=0, yovi YoiTV={count_yovi}, Shinori=0, "
          f"5002 entries protected.")


if __name__ == "__main__":
    validate()
