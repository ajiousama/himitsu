#!/usr/bin/env python3
"""Publish only the isolated Arva catch-up VOD block, never alter VOD5/GCCX."""
from __future__ import annotations
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FREEWIFI = ROOT / "freewifi"
PLAYLIST = ROOT / "arva_vod" / "playlist.m3u"
START = "# === ARVA_VOD_START ==="
END = "# === ARVA_VOD_END ==="

def main():
    playlist = PLAYLIST.read_text(encoding="utf-8-sig")
    entries = playlist.splitlines()
    entries = [x for x in entries if x.startswith("#EXTINF:") or x.startswith("https://")]
    if not any(x.startswith("#EXTINF:") for x in entries):
        print("Arva VOD: no confirmed programmes; keeping existing FreeWiFi unchanged")
        return
    payload = START + "\n" + "\n".join(entries) + "\n" + END
    text = FREEWIFI.read_text(encoding="utf-8-sig")
    regex = re.compile(r"\n*" + re.escape(START) + r".*?" + re.escape(END), re.S)
    if regex.search(text):
        text = regex.sub("\n\n" + payload, text, count=1)
    else:
        marker = "# === VOD5_CATALOG_END ==="
        if marker not in text:
            raise RuntimeError("VOD5 catalogue boundary missing; refuse unsafe append")
        text = text.replace(marker, marker + "\n\n" + payload, 1)
    FREEWIFI.write_text(text.rstrip() + "\n", encoding="utf-8")
    print("Arva VOD: synced isolated catch-up entries; original VOD5 untouched")

if __name__ == "__main__":
    main()
