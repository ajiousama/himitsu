#!/usr/bin/env python3
from pathlib import Path

FREEWIFI = Path("freewifi")
PLAYLIST = Path("rakuten/playlist.m3u")
START = "## Rch"
END = "## 今日の開催場"

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
    FREEWIFI.write_text(updated.rstrip() + "\n", encoding="utf-8")
    print("Rakuten Rch synced from rakuten/playlist.m3u")

if __name__ == "__main__":
    main()
