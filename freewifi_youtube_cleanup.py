from __future__ import annotations

import re
from pathlib import Path

FREEWIFI = Path("freewifi")
GENERAL = Path("general_youtube.m3u")

# Old one-off YouTube IDs that were superseded by the managed general_youtube IDs.
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

# GCH A/B are owned only by jra_free_channels_update.py.
GCH_IDS = {"jra.official", "jra.gch.free"}
A_START = "# === JRA_GCH_FREE_A_START ==="
A_END = "# === JRA_GCH_FREE_A_END ==="
B_START = "# === JRA_GCH_FREE_B_START ==="
B_END = "# === JRA_GCH_FREE_B_END ==="


def entry_id(line: str) -> str | None:
    m = re.search(r'tvg-id="([^"]+)"', line)
    return m.group(1).strip() if m else None


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


def main() -> int:
    total = 0

    if GENERAL.exists():
        text = GENERAL.read_text(encoding="utf-8-sig", errors="replace")
        # Dedicated JRA/GCH updater owns jra.official; general YouTube must not republish it.
        text, n1 = remove_entries(text, LEGACY_IDS | {"jra.official"})
        text, n2 = dedupe_exact_ids(text)
        GENERAL.write_text(text, encoding="utf-8")
        total += n1 + n2
        print(f"general_youtube.m3u: removed={n1+n2}")

    if FREEWIFI.exists():
        text = FREEWIFI.read_text(encoding="utf-8-sig", errors="replace")
        text, n1 = remove_entries(text, LEGACY_IDS)
        # Remove stray GCH/JRA copies, but preserve canonical managed A/B blocks.
        text, n2 = remove_entries(text, GCH_IDS, preserve_gch_blocks=True)
        # FreeWiFi intentionally has several alternate sources sharing the same EPG ID
        # (HARUKA/NAORI/kaitekitv etc.), so only YouTube/JRA families may be deduped here.
        text, n3 = dedupe_exact_ids(text, prefixes=("youtube.", "jra."))
        FREEWIFI.write_text(text, encoding="utf-8")
        total += n1 + n2 + n3
        print(f"freewifi: legacy={n1} stray_gch={n2} duplicate_youtube_jra={n3}")

    print(f"cleanup total removed={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
