from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import epg_build

# Public-sports EPG is generated locally in this repository and merged later by
# public_sports_epg_merge.py. Never fetch the retired external public-sports repo
# from the base EPG builder.
epg_build.SOURCES = [(name, url) for name, url in epg_build.SOURCES if name != "public_sports"]
epg_build.SOURCE_PRIORITY = {name: i for i, (name, _) in enumerate(epg_build.SOURCES)}

epg_build.main()

out = Path("guides.xml")
if not out.is_file() or out.stat().st_size < 100_000:
    raise SystemExit(f"guides.xml suspiciously small: {out.stat().st_size if out.exists() else 0} bytes")

root = ET.parse(out).getroot()
channels = len(root.findall("channel"))
programmes = len(root.findall("programme"))
if channels < 50 or programmes < 100:
    raise SystemExit(f"guides.xml suspiciously sparse: channels={channels} programmes={programmes}")

print(f"SAFE EPG OK: bytes={out.stat().st_size} channels={channels} programmes={programmes}")
