#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path

FREEWIFI = Path("freewifi")
HARU_M3U = Path("haru_vod.m3u")
KICK_REPLAY_END = "# === KICK_REPLAY_END ==="
KICK_END = "# === KICK_MANAGED_END ==="
START = "# === HARU_VOD_START ==="
END = "# === HARU_VOD_END ==="


def entries(path: Path):
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    out = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF:"):
            j = i + 1
            while j < len(lines) and (not lines[j].strip() or lines[j].lstrip().startswith("#")):
                j += 1
            if j < len(lines) and lines[j].strip().startswith(("http://", "https://")):
                out.append((line, lines[j].strip()))
                i = j
        i += 1
    return out


def as_vod(extinf: str) -> str:
    if "group-title=" in extinf:
        return re.sub(r'group-title="[^"]*"', 'group-title="VOD"', extinf)
    if extinf.startswith("#EXTINF:"):
        p = extinf.find(" ")
        if p >= 0:
            return extinf[:p] + ' group-title="VOD"' + extinf[p:]
    return extinf


def remove_old(text: str) -> str:
    return re.sub(r"\n?" + re.escape(START) + r".*?" + re.escape(END) + r"\n?", "\n", text, flags=re.S)


def main() -> int:
    if not FREEWIFI.exists() or not HARU_M3U.exists():
        raise RuntimeError("FreeWiFi/HARU VOD input missing")

    vod = entries(HARU_M3U)
    body = [START, "## VOD / HARU blog"]
    for ext, url in vod:
        body += [as_vod(ext), url]
    body.append(END)
    block = "\n".join(body) + "\n"

    text = remove_old(FREEWIFI.read_text(encoding="utf-8-sig", errors="replace"))
    marker = KICK_REPLAY_END if KICK_REPLAY_END in text else KICK_END
    pos = text.find(marker)
    if pos < 0:
        raise RuntimeError("KICK managed insertion marker not found")
    pos += len(marker)
    FREEWIFI.write_text(text[:pos] + "\n\n" + block + text[pos:].lstrip("\n"), encoding="utf-8")
    print(f"FreeWiFi HARU VOD: {len(vod)} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
