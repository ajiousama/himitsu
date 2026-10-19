#!/usr/bin/env python3
"""Retired Arva publisher. This guard only removes legacy entries."""
from pathlib import Path
import re

FREEWIFI = Path("freewifi")
START = "# === ARVA_VOD_START ==="
END = "# === ARVA_VOD_END ==="


def remove_arva(text: str) -> str:
    text = re.sub(r"\n*" + re.escape(START) + r".*?" + re.escape(END) + r"\n*",
                  "\n\n", text, flags=re.S)
    lines = text.splitlines()
    kept = []
    i = 0
    while i < len(lines):
        if lines[i].startswith("#EXTINF:") and "arva" in lines[i].lower():
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i < len(lines) and not lines[i].lstrip().startswith("#"):
                i += 1
            continue
        kept.append(lines[i])
        i += 1
    return re.sub(r"\n{4,}", "\n\n\n", "\n".join(kept)).rstrip() + "\n"


def main() -> None:
    if not FREEWIFI.is_file():
        raise SystemExit("freewifi not found")
    before = FREEWIFI.read_text(encoding="utf-8-sig")
    after = remove_arva(before)
    if after != before:
        FREEWIFI.write_text(after, encoding="utf-8")
    print("Arva publishing disabled; legacy Arva rows removed")


if __name__ == "__main__":
    main()
