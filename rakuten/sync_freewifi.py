#!/usr/bin/env python3
from pathlib import Path
import json
from urllib.parse import quote

FREEWIFI = Path("freewifi")
CONTRAST_DB = Path("logos/contrast_sources.json")
RAW_BASE = "https://raw.githubusercontent.com/ajiousama/himitsu/main"
PLAYLIST = Path("rakuten/playlist.m3u")
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


def payload():
    text = PLAYLIST.read_text(encoding="utf-8-sig", errors="replace")
    lines = text.splitlines()
    if lines and lines[0].startswith("#EXTM3U"):
        lines = lines[1:]
    return "\n".join(lines).strip() + "\n\n"

def main():
    text = FREEWIFI.read_text(encoding="utf-8-sig", errors="replace")
    a = text.find(START)
    b = text.find(END, a + len(START))
    if a < 0 or b < 0:
        raise SystemExit("Rakuten Rch section boundary missing in freewifi")
    updated = text[:a] + payload() + text[b:]
    updated, reused = reuse_known_contrast_logos(updated)
    FREEWIFI.write_text(updated.rstrip() + "\n", encoding="utf-8")
    print(f"Rakuten Rch synced from rakuten/playlist.m3u; reused white-card logos={reused}")

if __name__ == "__main__":
    main()
