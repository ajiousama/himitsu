#!/usr/bin/env python3
from pathlib import Path
import re

FREEWIFI = Path("freewifi")
PLAYLIST = Path("patapata/playlist.m3u")
START = "# === PATAPATA_TV_START ==="
END = "# === PATAPATA_TV_END ==="
ANCHOR = "## YouTube"


def managed_block() -> str:
    text = PLAYLIST.read_text(encoding="utf-8-sig", errors="replace")
    lines = [line for line in text.splitlines() if not line.startswith("#EXTM3U")]
    body = "\n".join(lines).strip()
    return f"{START}\n{body}\n{END}"


def main() -> None:
    text = FREEWIFI.read_text(encoding="utf-8-sig", errors="replace")
    text = re.sub(re.escape(START) + r".*?" + re.escape(END) + r"\n*", "", text, flags=re.S)
    pos = text.find(ANCHOR)
    if pos < 0:
        raise SystemExit("YouTube anchor missing for Patapata TV insertion")
    block = managed_block()
    text = text[:pos].rstrip() + "\n\n" + block + "\n\n" + text[pos:].lstrip()
    FREEWIFI.write_text(text.rstrip() + "\n", encoding="utf-8")
    print("Patapata TV projection synced")


if __name__ == "__main__":
    main()
