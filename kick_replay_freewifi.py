#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import urllib.parse
from pathlib import Path

FREEWIFI = Path("freewifi")
KICK_M3U = Path("kick_replay.m3u")
GMCX_M3U = Path("kick_gmcx_chapters.m3u")
GMCX_JSON = Path("kick_gmcx_chapters.json")

KICK_END = "# === KICK_MANAGED_END ==="
START = "# === KICK_REPLAY_START ==="
END = "# === KICK_REPLAY_END ==="


def entries(path: Path) -> list[tuple[str, str]]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    out: list[tuple[str, str]] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith("#EXTINF:"):
            j = i + 1
            while j < len(lines) and (not lines[j].strip() or lines[j].lstrip().startswith("#")):
                j += 1
            if j < len(lines):
                url = lines[j].strip()
                if url.startswith(("http://", "https://")):
                    out.append((line, url))
                    i = j
        i += 1
    return out


def tvg_id(extinf: str) -> str:
    m = re.search(r'\btvg-id="([^"]+)"', extinf)
    return m.group(1) if m else ""


def vod_id(url: str) -> str:
    try:
        q = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        return (q.get("vod") or [""])[0]
    except Exception:
        return ""


def remove_old_block(text: str) -> str:
    pattern = re.compile(
        r"\n?" + re.escape(START) + r".*?" + re.escape(END) + r"\n?",
        re.S,
    )
    return pattern.sub("\n", text)


def main() -> int:
    if not FREEWIFI.exists():
        raise RuntimeError("freewifi is missing")
    if not KICK_M3U.exists():
        raise RuntimeError("kick_replay.m3u is missing")

    generic: list[tuple[str, str]] = []
    gccx_whole: list[tuple[str, str]] = []
    chapter_entries = entries(GMCX_M3U)

    ai_required: set[str] = set()
    if GMCX_JSON.exists():
        data = json.loads(GMCX_JSON.read_text(encoding="utf-8-sig"))
        for item in data.get("results") or []:
            if isinstance(item, dict) and item.get("status") == "ai_required" and item.get("vod_id"):
                ai_required.add(str(item["vod_id"]))

    for extinf, url in entries(KICK_M3U):
        tid = tvg_id(extinf)
        if tid.startswith("kick.gccx"):
            if vod_id(url) in ai_required:
                gccx_whole.append((extinf, url))
        else:
            generic.append((extinf, url))

    body: list[str] = [START]

    if generic:
        body.append("## 📼 KICK Replay")
        for extinf, url in generic:
            body.extend((extinf, url))

    if chapter_entries:
        body.append("")
        body.append("## 🎮 GMCX Replay（回別）")
        for extinf, url in chapter_entries:
            body.extend((extinf, url))

    if gccx_whole:
        body.append("")
        body.append("## 🎞 GMCX Replay（SP・変則 / AI判定待ち）")
        for extinf, url in gccx_whole:
            # Keep the original VOD title but make the special handling visible.
            if "," in extinf:
                head, name = extinf.split(",", 1)
                extinf = f"{head},🎞 {name.removeprefix('📼 ').strip()} [変則VOD]"
            body.extend((extinf, url))

    body.append(END)
    block = "\n".join(body) + "\n"

    text = FREEWIFI.read_text(encoding="utf-8-sig", errors="replace")
    text = remove_old_block(text)
    pos = text.find(KICK_END)
    if pos < 0:
        raise RuntimeError(f"{KICK_END} not found in freewifi")
    pos += len(KICK_END)
    text = text[:pos] + "\n\n" + block + text[pos:].lstrip("\n")
    FREEWIFI.write_text(text, encoding="utf-8")

    print(
        "FreeWiFi KICK Replay:",
        f"generic={len(generic)}",
        f"gmcx_chapters={len(chapter_entries)}",
        f"gmcx_special={len(gccx_whole)}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
