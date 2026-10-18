#!/usr/bin/env python3
"""Retire HARUKA sources and keep Arva trial channels just after TOKYO MX1.

Idempotent: safe to run in every FreeWiFi refresh. Does not touch other streams.
"""
from __future__ import annotations

from pathlib import Path
import re

FILES = [Path("tv/playlist.m3u"), Path("rakuten/playlist.m3u"), Path("freewifi")]
TRIALS = ("テレ玉 (Arva・試験)", "tvk (Arva・試験)")
ANCHOR = "TOKYO MX1 (YoiTV)"


def clean_playlist(text: str, *, reposition: bool) -> tuple[str, int]:
    lines = text.splitlines()
    kept: list[str] = []
    trials: dict[str, tuple[str, str]] = {}
    removed = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#EXTINF:"):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            uri = lines[j].strip() if j < len(lines) else ""
            retired = "haruka" in line.casefold() or bool(
                re.search(r":9394/stream/\d+\.m3u8(?:[?#]|$)", uri, re.I)
            )
            if retired:
                removed += 1
                i = j + 1
                while i < len(lines) and not lines[i].strip():
                    i += 1
                continue
            trial = next((name for name in TRIALS if name in line), None)
            if reposition and trial:
                if trial in trials or not uri.startswith(("http://", "https://")):
                    raise RuntimeError(f"Invalid or duplicate Arva trial: {trial}")
                trials[trial] = (line, uri)
                i = j + 1
                while i < len(lines) and not lines[i].strip():
                    i += 1
                continue
        kept.append(line)
        i += 1

    if reposition:
        if set(trials) != set(TRIALS):
            raise RuntimeError(f"Missing Arva trial channels: {set(TRIALS) - set(trials)}")
        insertion = None
        for k, row in enumerate(kept):
            if row.startswith("#EXTINF:") and ANCHOR in row:
                j = k + 1
                while j < len(kept) and not kept[j].strip():
                    j += 1
                insertion = j + 1
        if insertion is None:
            raise RuntimeError("TOKYO MX1 (YoiTV) anchor is missing")
        block: list[str] = [""]
        for trial in TRIALS:
            block.extend([*trials[trial], ""])
        kept[insertion:insertion] = block

    updated = "\n".join(kept)
    updated = re.sub(r"\n{4,}", "\n\n\n", updated).rstrip() + "\n"
    if re.search(r"haruka|:9394/stream/", updated, re.I):
        raise RuntimeError("Retired HARUKA source remains")
    return updated, removed


def main() -> None:
    for p in FILES:
        old = p.read_text(encoding="utf-8-sig")
        updated, count = clean_playlist(old, reposition=p != Path("rakuten/playlist.m3u"))
        if updated != old:
            p.write_text(updated, encoding="utf-8")
        print(f"{p}: retired {count} HARUKA rows; Arva order guarded")


if __name__ == "__main__":
    main()
