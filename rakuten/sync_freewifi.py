#!/usr/bin/env python3
from pathlib import Path
import json
from urllib.parse import quote

FREEWIFI = Path("freewifi")
CONTRAST_DB = Path("logos/contrast_sources.json")
RAW_BASE = "https://raw.githubusercontent.com/ajiousama/himitsu/main"
PLAYLIST = Path("rakuten/playlist.m3u")
EXTRA = Path("rakuten/freewifi_extra.m3u")
START = "## Rch"
END = "## 今日の開催場"

def reuse_known_contrast_logos(text: str) -> tuple[str, int]:
    if not CONTRAST_DB.exists():
        return text, 0
    try:
        db = json.loads(CONTRAST_DB.read_text(encoding="utf-8"))
    except Exception:
        return text, 0
    replaced = 0
    for source, meta in db.items():
        if not isinstance(source, str) or not isinstance(meta, dict):
            continue
        relpath = meta.get("path")
        if not isinstance(relpath, str) or not relpath or not Path(relpath).is_file():
            continue
        count = text.count(source)
        if not count:
            continue
        text = text.replace(source, f"{RAW_BASE}/{quote(relpath, safe='/._-')}")
        replaced += count
    return text, replaced


def strip_retired_haruka(text: str) -> str:
    lines = text.splitlines()
    kept = []
    i = 0
    while i < len(lines):
        if lines[i].startswith("#EXTINF:") and "haruka" in lines[i].lower():
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i < len(lines) and not lines[i].startswith("#"):
                i += 1
            continue
        kept.append(lines[i])
        i += 1
    return "\n".join(kept)


def payload():
    text = strip_retired_haruka(PLAYLIST.read_text(encoding="utf-8-sig", errors="replace"))
    lines = text.splitlines()
    if lines and lines[0].startswith("#EXTM3U"):
        lines = lines[1:]
    extra = EXTRA.read_text(encoding="utf-8-sig", errors="strict").strip()
    # Supplemental Rch sources are optional. The retired Arva bridge must
    # not be restored by the scheduled 10-minute rebuild.
    if "nouvelle-paradise-bridge" in extra.lower() or "ヌーヴェルパラダイス (Arva)" in extra:
        raise RuntimeError("Retired Nouvelle Paradise Arva source detected")
    if extra and (not extra.startswith("#EXTINF:") or 'group-title="Rch"' not in extra):
        raise RuntimeError("Rch FreeWiFi extras malformed")
    # Running as python rakuten/sync_freewifi.py must resolve the repository root.
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    base = "\n".join(lines).strip() + "\n\n"
    body = base + (extra + "\n\n" if extra else "")
    return body

def main():
    text = FREEWIFI.read_text(encoding="utf-8-sig", errors="replace")
    a = text.find(START)
    b = text.find(END, a + len(START))
    if a < 0 or b < 0:
        raise SystemExit("Rakuten Rch section boundary missing in freewifi")
    updated = text[:a] + payload() + text[b:]
    # The Rch job is independent; retire legacy rows elsewhere before enforcing the guard.
    updated = strip_retired_haruka(updated)
    updated, reused = reuse_known_contrast_logos(updated)
    if "haruka" in updated.lower():
        raise RuntimeError("Retired HARUKA source unexpectedly restored")
    if "nouvelle-paradise-bridge" in updated.lower() or "ヌーヴェルパラダイス (Arva)" in updated:
        raise RuntimeError("Retired Nouvelle Paradise Arva source unexpectedly restored")
    if "（newblog系）" in updated or "0i4neux01.charandom.blog/stream/jp/" in updated:
        raise RuntimeError("Retired newblog Rch was restored into FreeWiFi")
    FREEWIFI.write_text(updated.rstrip() + "\n", encoding="utf-8")
    print(f"Rakuten Rch synced from rakuten/playlist.m3u; reused white-card logos={reused}")

if __name__ == "__main__":
    main()
