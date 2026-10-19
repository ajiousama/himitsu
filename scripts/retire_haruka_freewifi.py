#!/usr/bin/env python3
"""Retire HARUKA and Arva playback rows from FreeWiFi sources.

Idempotent: safe to run on every canonical refresh. Other streams are retained.
"""
from __future__ import annotations

from pathlib import Path
import re

FILES = [Path("tv/playlist.m3u"), Path("rakuten/playlist.m3u"), Path("freewifi")]
ARVA_VOD_START = "# === ARVA_VOD_START ==="
ARVA_VOD_END = "# === ARVA_VOD_END ==="


def clean_playlist(text: str, *, reposition: bool = False) -> tuple[str, int]:
    """Remove retired HARUKA and Arva entries; preserve every unrelated row."""
    text = re.sub(
        r"\n*" + re.escape(ARVA_VOD_START) + r".*?" + re.escape(ARVA_VOD_END) + r"\n*",
        "\n\n",
        text,
        flags=re.S,
    )
    lines = text.splitlines()
    kept: list[str] = []
    removed = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#EXTINF:"):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            uri = lines[j].strip() if j < len(lines) else ""
            retired = (
                "haruka" in line.casefold()
                or "arva" in line.casefold()
                or bool(re.search(r":9394/stream/\d+\.m3u8(?:[?#]|$)", uri, re.I))
            )
            if retired:
                removed += 1
                i = j + 1
                while i < len(lines) and not lines[i].strip():
                    i += 1
                continue
        kept.append(line)
        i += 1

    updated = re.sub(r"\n{4,}", "\n\n\n", "\n".join(kept)).rstrip() + "\n"
    if re.search(r"haruka|arva|:9394/stream/", updated, re.I):
        raise RuntimeError("Retired HARUKA or Arva source remains")
    return updated, removed


def main() -> None:
    for path in FILES:
        old = path.read_text(encoding="utf-8-sig")
        updated, count = clean_playlist(old)
        if updated != old:
            path.write_text(updated, encoding="utf-8")
        print(f"{path}: retired HARUKA/Arva entries={count}")


if __name__ == "__main__":
    main()
