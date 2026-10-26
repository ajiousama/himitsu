#!/usr/bin/env python3
"""Keep yovi's ABEMA系 group in sync with karenda-jp/AbemaTV.

Only the explicitly marked karenda ABEMA block and an existing RavenTV
ABEMA promotional entry may be modified. Never change other sources.
"""
from __future__ import annotations

import re
import urllib.request
from pathlib import Path

SOURCE_URL = (
    "https://raw.githubusercontent.com/karenda-jp/AbemaTV/"
    "main/abema240P.m3u"
)
PLAYLIST = Path("yovi")
BEGIN = "# === YOVI_KARENDA_ABEMA_BEGIN ==="
END = "# === YOVI_KARENDA_ABEMA_END ==="
GROUP = "ABEMA系"
STREAM_RE = re.compile(
    r"https://linear-abematv\.akamaized\.net/preview/channel/"
    r"([a-z0-9_-]+)/playlist\.m3u8\Z"
)
GROUP_RE = re.compile(r"Abema_[A-Za-z0-9_-]+\Z")
RE_SOURCE = re.compile(r'group-title="(Abema_[A-Za-z0-9_-]+)"')


def parse_source(source: str, *, min_channels: int = 40) -> list[tuple[str, str]]:
    """Validate the upstream source before updating any local file."""
    if not source.lstrip("\ufeff").startswith("#EXTM3U"):
        raise ValueError("Upstream is not an M3U")
    lines = source.splitlines()
    entries: list[tuple[str, str]] = []
    seen: set[str] = set()
    for i, ext in enumerate(lines):
        if not ext.startswith("#EXTINF:"):
            continue
        if i + 1 >= len(lines):
            raise ValueError("Truncated upstream entry")
        url = lines[i + 1].strip()
        match = STREAM_RE.fullmatch(url)
        tvg_id = re.search(r'tvg-id="([^"]+)"', ext)
        group = re.search(r'group-title="([^"]+)"', ext)
        logo = re.search(r'tvg-logo="([^"]+)"', ext)
        if (
            not match or not tvg_id or tvg_id.group(1) != match.group(1)
            or not group or not GROUP_RE.fullmatch(group.group(1))
            or not logo or not logo.group(1).startswith(
                "https://image.p-c2-x.abema-tv.com/image/channels/"
                + match.group(1) + "/logo.png"
            )
        ):
            raise ValueError("Unrecognized upstream ABEMA entry")
        if match.group(1) in seen:
            raise ValueError("Duplicate upstream ABEMA channel")
        seen.add(match.group(1))
        # Retain upstream ID, logo and title, but group all ABEMA entries together.
        ext = RE_SOURCE.sub('group-title="ABEMA系"', ext, count=1)
        entries.append((ext, url))
    if not min_channels <= len(entries) <= 150:
        raise ValueError("Unexpected ABEMA channel count")
    return entries


def update_yovi(original: str, entries: list[tuple[str, str]]) -> str:
    """Replace only the managed ABEMA block, leaving everything else intact."""
    if not original.lstrip("\ufeff").startswith("#EXTM3U"):
        raise ValueError("yovi is not an M3U playlist")
    if original.count(BEGIN) != original.count(END) or original.count(BEGIN) > 1:
        raise ValueError("Malformed ABEMA markers in yovi")

    lines = [
        BEGIN,
        "# Upstream: https://github.com/karenda-jp/AbemaTV/blob/main/abema240P.m3u",
        "# Managed automatically; other yovi channels must remain unchanged.",
    ]
    for ext, url in entries:
        lines.extend((ext, url, ""))
    lines.append(END)
    block = "\n".join(lines) + "\n"

    # Put the pre-existing ABEMA promotional feed in the same group, but
    # leave its URL, metadata and position otherwise unchanged.
    body = re.sub(
        r'(?m)^(#EXTINF:[^\n]*tvg-id="commercial"[^\n]*'
        r'group-title=")RavenTV-JP("[^\n]*AbemaTV Promo \(VPN\)[^\n]*)$',
        lambda m: m.group(1) + GROUP + m.group(2),
        original,
    )

    if BEGIN not in body:
        spacer = "" if body.endswith("\n\n") else "\n" if body.endswith("\n") else "\n\n"
        return body + spacer + block

    marker = re.compile(
        r"^" + re.escape(BEGIN) + r"\r?\n"
        r".*?^" + re.escape(END) + r"(?:\r?\n)?",
        re.MULTILINE | re.DOTALL,
    )
    m = marker.search(body)
    if not m:
        raise ValueError("ABEMA marker block cannot be parsed")
    return body[:m.start()] + block + body[m.end():]


def download_source() -> str:
    request = urllib.request.Request(
        SOURCE_URL,
        headers={"User-Agent": "yovi-abema-sync/1.0", "Accept": "text/plain,*/*"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.geturl() != SOURCE_URL:
            raise ValueError("Unexpected upstream redirect")
        data = response.read(300_001)
    if len(data) > 300_000:
        raise ValueError("Upstream ABEMA M3U too large")
    return data.decode("utf-8-sig")


def main() -> None:
    entries = parse_source(download_source())
    original = PLAYLIST.read_text(encoding="utf-8-sig")
    updated = update_yovi(original, entries)
    if updated != original:
        PLAYLIST.write_text(updated, encoding="utf-8")
        print(f"Updated yovi ABEMA系: {len(entries)} upstream channels")
    else:
        print(f"yovi ABEMA系 is current: {len(entries)} upstream channels")


if __name__ == "__main__":
    main()
