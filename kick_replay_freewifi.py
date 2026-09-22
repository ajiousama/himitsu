#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

FREEWIFI = Path("freewifi")
VOD5 = Path("VOD5")
REPLAY_M3U = Path("kick_replay.m3u")
REPLAY_JSON = Path("kick_replay.json")
GMCX_M3U = Path("kick_gmcx_chapters.m3u")
GMCX_JSON = Path("kick_gmcx_chapters.json")

START = "# === KICK_REPLAY_START ==="
END = "# === KICK_REPLAY_END ==="
LONG_START = "# === GMCX_LONG_VOD_START ==="
LONG_END = "# === GMCX_LONG_VOD_END ==="
FREEWIFI_SPECIAL_IDS = {"kick.gmcx.special.2012-last30s-live"}


def remove_old(text: str) -> str:
    text = re.sub(
        r"\n?" + re.escape(START) + r".*?" + re.escape(END) + r"\n?",
        "\n",
        text,
        flags=re.S,
    )
    return re.sub(
        r"\n?" + re.escape(LONG_START) + r".*?" + re.escape(LONG_END) + r"\n?",
        "\n",
        text,
        flags=re.S,
    )


def read_entries(path: Path) -> list[tuple[str, str]]:
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    out: list[tuple[str, str]] = []
    for i, line in enumerate(lines):
        if not line.startswith("#EXTINF:"):
            continue
        if i + 1 >= len(lines):
            continue
        url = lines[i + 1].strip()
        if not url or url.startswith("#"):
            continue
        out.append((line, url))
    return out


def ready_chapter_vods() -> set[str]:
    if not GMCX_JSON.exists():
        return set()
    payload = json.loads(GMCX_JSON.read_text(encoding="utf-8"))
    return {
        str(item.get("vod_id"))
        for item in payload.get("results", [])
        if item.get("status") == "ready" and item.get("chapters")
    }


def replay_vod_ids() -> dict[str, str]:
    if not REPLAY_JSON.exists():
        return {}
    payload = json.loads(REPLAY_JSON.read_text(encoding="utf-8"))
    return {
        str(item.get("tvg_id")) + ".replay." + str(item.get("vod_id"))[:12]: str(item.get("vod_id"))
        for item in payload.get("vods", [])
        if item.get("vod_id") and item.get("tvg_id")
    }


def tvg_id(extinf: str) -> str:
    m = re.search(r'tvg-id="([^"]+)"', extinf)
    return m.group(1) if m else ""


def build_vod5() -> str:
    chapter_vods = ready_chapter_vods()
    id_to_vod = replay_vod_ids()

    whole: list[tuple[str, str]] = []
    for extinf, url in read_entries(REPLAY_M3U):
        vod_id = id_to_vod.get(tvg_id(extinf))
        if vod_id and vod_id in chapter_vods:
            continue
        whole.append((extinf, url))

    chapters = [
        (extinf, url)
        for extinf, url in read_entries(GMCX_M3U)
        if tvg_id(extinf) not in FREEWIFI_SPECIAL_IDS
    ]
    lines = ["#EXTM3U"]
    for extinf, url in whole:
        lines.extend([extinf.replace('group-title="VOD"', 'group-title="VOD"'), url])
    for extinf, url in chapters:
        lines.extend([extinf.replace('group-title="GMCX Replay"', 'group-title="VOD"'), url])
    return "\n".join(lines) + "\n"


def main() -> int:
    if not FREEWIFI.exists():
        raise RuntimeError("FreeWiFi input missing")
    if not REPLAY_M3U.exists() or not REPLAY_JSON.exists():
        raise RuntimeError("KICK replay outputs missing")
    if not GMCX_M3U.exists() or not GMCX_JSON.exists():
        raise RuntimeError("GMCX chapter outputs missing")

    text = FREEWIFI.read_text(encoding="utf-8-sig", errors="replace")
    cleaned = remove_old(text).rstrip() + "\n"

    long_entries = [
        (extinf, url)
        for extinf, url in read_entries(GMCX_M3U)
        if tvg_id(extinf) in FREEWIFI_SPECIAL_IDS
    ]
    if long_entries:
        block = [LONG_START]
        for extinf, url in long_entries:
            block.extend([
                extinf.replace('group-title="GMCX Replay"', 'group-title="VOD"'),
                url,
            ])
        block.append(LONG_END)
        cleaned += "\n" + "\n".join(block) + "\n"

    if cleaned != text:
        FREEWIFI.write_text(cleaned, encoding="utf-8")

    vod5 = build_vod5()
    VOD5.write_text(vod5, encoding="utf-8")
    vod_count = vod5.count('group-title="VOD"')
    print(f"KICK VOD published to VOD5: {vod_count} entries")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
