#!/usr/bin/env python3
from pathlib import Path
import json
from urllib.parse import quote

FREEWIFI = Path("freewifi")
PLAYLIST = Path("tv/playlist.m3u")
START = "## 地上波"
END = "## ラジオ"
CONTRAST_DB = Path("logos/contrast_sources.json")
RAW_BASE = "https://raw.githubusercontent.com/ajiousama/himitsu/main"

def payload():
    text = PLAYLIST.read_text(encoding="utf-8-sig", errors="replace")
    lines = text.splitlines()
    if lines and lines[0].startswith("#EXTM3U"):
        lines = lines[1:]
    return "\n".join(lines).strip() + "\n\n"

def reuse_known_contrast_logos(text: str) -> tuple[str, int]:
    """Reuse already-generated local contrast logos without fetching/rebuilding images."""
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
        local = f"{RAW_BASE}/{quote(relpath, safe='/._-')}"
        text = text.replace(source, local)
        replaced += count
    return text, replaced


def main():
    text = FREEWIFI.read_text(encoding="utf-8-sig", errors="replace")
    a = text.find(START)
    b = text.find(END, a + len(START))
    if a < 0 or b < 0:
        raise SystemExit("TV section boundary missing in freewifi")
    updated = text[:a] + payload() + text[b:]
    updated, reused = reuse_known_contrast_logos(updated)
    FREEWIFI.write_text(updated.rstrip() + "\n", encoding="utf-8")
    print(f"TV synced from tv/playlist.m3u; reused contrast logos={reused}")

if __name__ == "__main__":
    main()
