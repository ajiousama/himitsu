#!/usr/bin/env python3
from pathlib import Path

FREEWIFI = Path("freewifi")
PLAYLIST = Path("tver/playlist.m3u")
START = "### TVerﾘｱﾙﾀｲﾑ"
END = "## YouTube"

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
        raise SystemExit("TVer realtime section boundary missing in freewifi")
    updated = text[:a] + payload() + text[b:]
    FREEWIFI.write_text(updated.rstrip() + "\n", encoding="utf-8")
    print("TVer realtime synced from tver/playlist.m3u")

if __name__ == "__main__":
    main()
