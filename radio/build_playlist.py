#!/usr/bin/env python3
from pathlib import Path

ROOT = Path("radio")
NATIONWIDE = ROOT / "nationwide.m3u"
NHK = ROOT / "nhk.m3u"
OUT = ROOT / "playlist.m3u"
COMPAT = Path("radio.m3u")

def body(path: Path):
    if not path.exists():
        raise SystemExit(f"missing radio source: {path}")
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    if lines and lines[0].startswith("#EXTM3U"):
        lines = lines[1:]
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines

def main():
    nationwide = body(NATIONWIDE)
    nhk = body(NHK)
    text = "#EXTM3U\n\n" + "\n".join(nationwide) + "\n\n" + "\n".join(nhk) + "\n"
    count = text.count("#EXTINF:")
    if count < 110:
        raise SystemExit(f"radio combined catalog too small: {count}")
    OUT.write_text(text, encoding="utf-8")
    COMPAT.write_text(text, encoding="utf-8")
    print(f"radio combined static-image video catalog: {count} channels")

if __name__ == "__main__":
    main()
