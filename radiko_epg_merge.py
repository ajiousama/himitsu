from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from pathlib import Path

from radiko_epg import build_xmltv

GUIDES = Path("guides.xml")
FREEWIFI = Path("freewifi")


def wanted_radiko_ids() -> list[str]:
    text = FREEWIFI.read_text(encoding="utf-8-sig", errors="replace")
    ids = []
    seen = set()
    for line in text.splitlines():
        if not line.startswith("#EXTINF:"):
            continue
        m = re.search(r'tvg-id="(radiko\.[^"]+)"', line)
        if not m:
            continue
        tid = m.group(1).strip()
        if tid not in seen:
            seen.add(tid)
            ids.append(tid)
    return ids


def main() -> int:
    wanted = wanted_radiko_ids()
    if not wanted:
        print("Radiko EPG: no selected FreeWiFi stations; nothing to merge")
        return 0

    main_root = ET.parse(GUIDES).getroot()
    rad_root = ET.fromstring(build_xmltv(3))
    wanted_set = set(wanted)

    available_channels = {
        (node.get("id") or ""): node
        for node in rad_root.findall("channel")
        if (node.get("id") or "") in wanted_set
    }
    programmes = [
        node
        for node in rad_root.findall("programme")
        if (node.get("channel") or "") in wanted_set
    ]

    missing = [tid for tid in wanted if tid not in available_channels]
    if missing:
        raise RuntimeError(
            "Radiko EPG missing selected stations; refusing to publish partial guide: "
            + ", ".join(missing)
        )
    if len(programmes) < len(wanted) * 6:
        raise RuntimeError(
            f"Radiko EPG programme count too small ({len(programmes)} for {len(wanted)} stations); "
            "refusing to overwrite a good guide"
        )

    for node in list(main_root.findall("channel")):
        if (node.get("id") or "").startswith("radiko."):
            main_root.remove(node)
    for node in list(main_root.findall("programme")):
        if (node.get("channel") or "").startswith("radiko."):
            main_root.remove(node)

    for tid in wanted:
        main_root.append(available_channels[tid])
    for node in programmes:
        main_root.append(node)

    ET.ElementTree(main_root).write(GUIDES, encoding="utf-8", xml_declaration=True)
    print(f"Radiko EPG merged: {len(wanted)} selected stations / {len(programmes)} programmes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
