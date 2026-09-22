#!/usr/bin/env python3
from pathlib import Path

FREEWIFI = Path("freewifi")
PLAYLIST = Path("radio/freewifi.m3u")
START = "## ラジオ"
END = "## 愛媛CATV"

def body():
    text = PLAYLIST.read_text(encoding="utf-8-sig", errors="replace")
    lines = text.splitlines()
    if lines and lines[0].startswith("#EXTM3U"):
        lines = lines[1:]
    return "\n".join(lines).strip() + "\n\n"

def main():
    text = FREEWIFI.read_text(encoding="utf-8-sig", errors="replace")
    a = text.find(START); b = text.find(END, a + len(START))
    if a < 0 or b < 0:
        raise SystemExit("radio section boundary missing")
    FREEWIFI.write_text((text[:a] + body() + text[b:]).rstrip() + "\n", encoding="utf-8")
    print("radio synced from radio/freewifi.m3u")

if __name__ == "__main__":
    main()
