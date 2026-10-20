#!/usr/bin/env python3
"""Keep FreeWiFi XMLTV channel icons identical to its M3U tvg-logo values.

The FreeWiFi M3U is the canonical channel-logo catalogue. EPG input feeds
can have different icons even for the same tvg-id; players may prefer those
EPG icons, making only some source variants appear to have wrong logos.
Run *after* all XMLTV merges and overlays, immediately before publishing.
No playback URL or programme data is modified.
"""

from __future__ import annotations

import re
from pathlib import Path
import xml.etree.ElementTree as ET

M3U_PATH = Path("freewifi")
XML_PATH = Path("guides.xml")
ID_RE = re.compile(r'\btvg-id="([^"]+)"')
LOGO_RE = re.compile(r'\btvg-logo="([^"]+)"')


def read_logo_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    entries = 0
    for line in M3U_PATH.read_text(encoding="utf-8-sig").splitlines():
        if not line.startswith("#EXTINF"):
            continue
        entries += 1
        match_id = ID_RE.search(line)
        match_logo = LOGO_RE.search(line)
        if not match_id or not match_logo or not match_logo.group(1):
            continue
        channel_id, logo = match_id.group(1), match_logo.group(1)
        if not logo.startswith(("https://", "http://")):
            raise SystemExit(f"Invalid logo URL for {channel_id}: {logo[:100]}")
        previous = mapping.setdefault(channel_id, logo)
        if previous != logo:
            raise SystemExit(
                f"Conflicting FreeWiFi tvg-logos for {channel_id}; "
                "refusing to choose silently"
            )
    if entries < 150 or len(mapping) < 100:
        raise SystemExit(
            f"FreeWiFi catalogue unexpectedly small: entries={entries}, ids={len(mapping)}"
        )
    return mapping


def main() -> None:
    logos = read_logo_map()
    if not XML_PATH.is_file() or XML_PATH.stat().st_size < 100_000:
        raise SystemExit("guides.xml is absent or suspiciously small")

    tree = ET.parse(XML_PATH)
    root = tree.getroot()
    channels = root.findall("channel")
    if len(channels) < 50 or len(root.findall("programme")) < 100:
        raise SystemExit("guides.xml is too sparse; refusing logo sync")

    changed = 0
    matched = 0
    for channel in channels:
        channel_id = channel.get("id", "")
        logo = logos.get(channel_id)
        if not logo:
            continue
        matched += 1
        icons = channel.findall("icon")
        if not icons:
            ET.SubElement(channel, "icon", {"src": logo})
            changed += 1
        else:
            if icons[0].get("src") != logo:
                icons[0].set("src", logo)
                changed += 1
            for extra in icons[1:]:
                channel.remove(extra)
                changed += 1

    if matched < 50:
        raise SystemExit(
            f"Only {matched} FreeWiFi channel IDs matched in XMLTV; "
            "refusing incomplete output"
        )
    if changed:
        temp_path = XML_PATH.with_suffix(".logos.tmp")
        tree.write(temp_path, encoding="utf-8", xml_declaration=True)
        if temp_path.stat().st_size < 100_000:
            temp_path.unlink(missing_ok=True)
            raise SystemExit("Refusing suspiciously small XMLTV output")
        temp_path.replace(XML_PATH)
    print(
        f"FreeWiFi XMLTV icon sync: catalogue={len(logos)}, "
        f"matched={matched}, changed={changed}; "
        "programme data and stream URLs preserved"
    )


if __name__ == "__main__":
    main()
