from __future__ import annotations

import re
from pathlib import Path

FREEWIFI = Path("freewifi")
GENERAL = Path("general_youtube.m3u")
DEFAULT_YOUTUBE_LOGO = "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/youtube/youtube_live_camera_default.png"
JRA_LOGOS = {
    "jra.official": "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/youtube/jra_youtube_free.jpg",
    "jra.gch.free": "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/youtube/jra_gch_free.jpg",
}

LEGACY_IDS = {
    "youtube.matsuyama.clean",
    "youtube.matsuyama.airport",
    "youtube.namibia.live",
    "youtube.shiba.natsu",
    "youtube.osaka.loop",
    "youtube.kobe.waterfront",
    "youtube.muko.camera",
    "youtube.itami.mbs",
    "youtube.narita.asahi",
    "youtube.kix.ktv",
    "youtube.kyoto.station",
    "youtube.conode.horse.near",
    "youtube.conode.horse.far",
    "youtube.osaka.station.tvo",
    "youtube.haneda.t2.ntv",
    "youtube.centrair.ctv",
    "youtube.katsuragawa.mlit",
    "youtube.radio171.rail",
    "youtube.newchitose.stv",
    "youtube.fukuoka.ube.tnc",
}

GCH_IDS = {"jra.official", "jra.gch.free"}
A_START = "# === JRA_GCH_FREE_A_START ==="
A_END = "# === JRA_GCH_FREE_A_END ==="
B_START = "# === JRA_GCH_FREE_B_START ==="
B_END = "# === JRA_GCH_FREE_B_END ==="


def entry_id(line: str) -> str | None:
    m = re.search(r'tvg-id="([^"]+)"', line)
    return m.group(1).strip() if m else None


def ensure_logo(line: str) -> tuple[str, bool]:
    if not line.startswith("#EXTINF:"):
        return line, False
    cid = entry_id(line)
    if not cid or not (cid.startswith("youtube.") or cid in JRA_LOGOS):
        return line, False

    desired = JRA_LOGOS.get(cid, DEFAULT_YOUTUBE_LOGO)
    m = re.search(r'tvg-logo="([^"]*)"', line)
    if m:
        if m.group(1).strip():
            return line, False
        return line[:m.start(1)] + desired + line[m.end(1):], True

    pos = None
    for pat in (r'tvg-name="[^"]*"', r'tvg-id="[^"]*"'):
        mm = re.search(pat, line)
        if mm:
            pos = mm.end()
            break
    if pos is None:
        return line + f' tvg-logo="{desired}"', True
    return line[:pos] + f' tvg-logo="{desired}"' + line[pos:], True


def fill_missing_logos(text: str) -> tuple[str, int]:
    out = []
    changed = 0
    for line in text.splitlines():
        line2, did = ensure_logo(line)
        out.append(line2)
        changed += int(did)
    return "\n".join(out).rstrip() + "\n", changed


def remove_entries(text: str, ids: set[str], preserve_gch_blocks: bool = False) -> tuple[str, int]:
    lines = text.splitlines()
    out: list[str] = []
    removed = 0
    i = 0
    in_gch = False

    while i < len(lines):
        line = lines[i]
        if line in (A_START, B_START):
            in_gch = True
        if preserve_gch_blocks and in_gch:
            out.append(line)
            if line in (A_END, B_END):
                in_gch = False
            i += 1
            continue
        if line in (A_END, B_END):
            in_gch = False

        if line.startswith("#EXTINF:") and entry_id(line) in ids:
            removed += 1
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i < len(lines) and lines[i].strip().startswith(("http://", "https://")):
                i += 1
            continue

        out.append(line)
        i += 1

    return "\n".join(out).rstrip() + "\n", removed


def dedupe_exact_ids(text: str, prefixes: tuple[str, ...] | None = None) -> tuple[str, int]:
    """Keep the first exact ID. When prefixes is set, only those ID families are deduped."""
    lines = text.splitlines()
    out: list[str] = []
    seen: set[str] = set()
    removed = 0
    i = 0
    in_gch = False

    while i < len(lines):
        line = lines[i]
        if line in (A_START, B_START):
            in_gch = True
        if in_gch:
            out.append(line)
            if line in (A_END, B_END):
                in_gch = False
            i += 1
            continue

        if line.startswith("#EXTINF:"):
            cid = entry_id(line)
            eligible = bool(cid) and (prefixes is None or cid.startswith(prefixes))
            if eligible and cid in seen:
                removed += 1
                i += 1
                while i < len(lines) and not lines[i].strip():
                    i += 1
                if i < len(lines) and lines[i].strip().startswith(("http://", "https://")):
                    i += 1
                continue
            if eligible and cid:
                seen.add(cid)

        out.append(line)
        i += 1

    return "\n".join(out).rstrip() + "\n", removed


def dedupe_same_id_url(text: str) -> tuple[str, int]:
    """Remove only true duplicate entries: same tvg-id AND same stream URL.

    Different URLs for the same tvg-id are intentionally preserved because FreeWiFi
    contains alternate/backup sources (for example HARUKA1/2/3).
    """
    lines = text.splitlines()
    out: list[str] = []
    seen: set[tuple[str, str]] = set()
    removed = 0
    i = 0

    while i < len(lines):
        line = lines[i]
        if not line.startswith("#EXTINF:"):
            out.append(line)
            i += 1
            continue

        cid = entry_id(line)
        j = i + 1
        blanks: list[str] = []
        while j < len(lines) and not lines[j].strip():
            blanks.append(lines[j])
            j += 1

        if cid and j < len(lines) and lines[j].strip().startswith(("http://", "https://")):
            url = lines[j].strip()
            key = (cid, url)
            if key in seen:
                removed += 1
                i = j + 1
                continue
            seen.add(key)
            out.append(line)
            out.extend(blanks)
            out.append(lines[j])
            i = j + 1
            continue

        out.append(line)
        i += 1

    return "\n".join(out).rstrip() + "\n", removed


def main() -> int:
    total = 0

    if GENERAL.exists():
        text = GENERAL.read_text(encoding="utf-8-sig", errors="replace")
        text, n1 = remove_entries(text, LEGACY_IDS | {"jra.official"})
        text, n2 = dedupe_exact_ids(text)
        text, n3 = fill_missing_logos(text)
        GENERAL.write_text(text, encoding="utf-8")
        total += n1 + n2
        print(f"general_youtube.m3u: removed={n1+n2} logos_filled={n3}")

    if FREEWIFI.exists():
        text = FREEWIFI.read_text(encoding="utf-8-sig", errors="replace")
        text, n1 = remove_entries(text, LEGACY_IDS)
        text, n2 = remove_entries(text, GCH_IDS, preserve_gch_blocks=True)
        text, n3 = dedupe_exact_ids(text, prefixes=("youtube.", "jra."))
        text, n4 = dedupe_same_id_url(text)
        text, n5 = fill_missing_logos(text)
        FREEWIFI.write_text(text, encoding="utf-8")
        total += n1 + n2 + n3 + n4
        print(f"freewifi: legacy={n1} stray_gch={n2} duplicate_youtube_jra={n3} duplicate_same_id_url={n4} logos_filled={n5}")

    print(f"cleanup total removed={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
