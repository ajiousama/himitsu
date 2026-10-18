#!/usr/bin/env python3
"""Project Arva VOD and VLC-verified newblog replays into FreeWiFi.

Keep Railway for untested programmes and short exact-length clips.
Never touch Kick VOD5/GCCX. Idempotent and safe on hourly regeneration.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

ROOT = Path(__file__).resolve().parent.parent
FREEWIFI = ROOT / "freewifi"
PLAYLIST = ROOT / "arva_vod" / "playlist.m3u"
NEWBLOG = ROOT / "newblog" / "source.m3u"
START = "# === ARVA_VOD_START ==="
END = "# === ARVA_VOD_END ==="

# Verified on user's VLC on 2026-10-18: one replay from each source,
# plus two ABC 07:29 starts. ABC six-minute clips remain on Railway
# until their exact end at 07:35 is verified with a newblog-only method.
NEWBLOG_VERIFIED_PROGRAMMES = {
    "knight_scoop": "abc",
    "homeru_chan": "mbs",
    "0655": "nhk_e",
    "bakobako_sun": "sun",
}
SIX_DAYS_SECONDS = 6 * 86400


def catchup_templates() -> dict[str, str]:
    """Read the current approved upstream source, including refreshed token."""
    if not NEWBLOG.is_file():
        return {}
    templates: dict[str, str] = {}
    for line in NEWBLOG.read_text(encoding="utf-8-sig").splitlines():
        if not line.startswith("#EXTINF:"):
            continue
        match = re.search(r'catchup-source="([^"]+)"', line)
        if not match:
            continue
        url = match.group(1)
        parsed = urlsplit(url)
        slug_match = re.fullmatch(r"/stream/jp/([a-z0-9_-]+)/replay\.m3u8", parsed.path)
        if (parsed.scheme != "https" or parsed.hostname != "0i4neux01.charandom.blog"
                or not slug_match or not parse_qs(parsed.query).get("ac_tk")
                or "$" + "{start}" not in url):
            continue
        templates[slug_match.group(1)] = url
    return templates


def replay_uri(extinf: str, templates: dict[str, str], now_epoch: int) -> str | None:
    match = re.search(r'tvg-id="arva\.vod\.([a-z0-9_]+)\.(\d+)"', extinf)
    if not match:
        return None
    programme, start = match.group(1), int(match.group(2))
    slug = NEWBLOG_VERIFIED_PROGRAMMES.get(programme)
    if not slug or slug not in templates:
        return None
    # Never advertise a newblog replay older than its advertised six-day window.
    if not 0 <= now_epoch - start < SIX_DAYS_SECONDS:
        return None
    return templates[slug].replace("$" + "{start}", str(start))


def projected_entries(playlist: str) -> tuple[list[str], int]:
    """Rewrite approved source URLs, never alter names, IDs, logos or groups."""
    original = playlist.splitlines()
    entries = [line for line in original
               if line.startswith("#EXTINF:") or line.startswith("https://")]
    templates = catchup_templates()
    now_epoch = int(datetime.now(timezone.utc).timestamp())
    replacements = 0
    for i, line in enumerate(entries):
        if not line.startswith("#EXTINF:"):
            continue
        if i + 1 >= len(entries) or not entries[i+1].startswith("https://"):
            raise ValueError("Arva VOD playlist has an incomplete entry")
        new_uri = replay_uri(line, templates, now_epoch)
        if new_uri and new_uri != entries[i + 1]:
            entries[i + 1] = new_uri
            replacements += 1
    return entries, replacements


def main() -> None:
    playlist = PLAYLIST.read_text(encoding="utf-8-sig")
    entries, replacements = projected_entries(playlist)
    if not any(line.startswith("#EXTINF:") for line in entries):
        print("VOD source playlist empty; keeping previous FreeWiFi unchanged")
        return
    payload = START + "\n" + "\n".join(entries) + "\n" + END
    text = FREEWIFI.read_text(encoding="utf-8-sig")
    regex = re.compile(r"\n*" + re.escape(START) + r".*?" + re.escape(END), re.S)
    if regex.search(text):
        text = regex.sub(lambda _: "\n\n" + payload, text, count=1)
    else:
        marker = "# === VOD5_CATALOG_END ==="
        if marker not in text:
            raise RuntimeError("VOD5 boundary missing; refuse unsafe append")
        text = text.replace(marker, marker + "\n\n" + payload, 1)
    FREEWIFI.write_text(text.rstrip() + "\n", encoding="utf-8")
    print(f"VOD: {replacements} verified-programme newblog sources; "
          "Railway retained for unsupported/expired streams and 07:29-07:35 clips")


if __name__ == "__main__":
    main()
