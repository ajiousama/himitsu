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

    old_channels = {
        (node.get("id") or ""): node
        for node in main_root.findall("channel")
        if (node.get("id") or "") in wanted_set
    }
    old_programmes: dict[str, list[ET.Element]] = {tid: [] for tid in wanted}
    for node in main_root.findall("programme"):
        tid = node.get("channel") or ""
        if tid in wanted_set:
            old_programmes.setdefault(tid, []).append(node)

    fresh_channels = {
        (node.get("id") or ""): node
        for node in rad_root.findall("channel")
        if (node.get("id") or "") in wanted_set
    }
    fresh_programmes: dict[str, list[ET.Element]] = {tid: [] for tid in wanted}
    for node in rad_root.findall("programme"):
        tid = node.get("channel") or ""
        if tid in wanted_set:
            fresh_programmes.setdefault(tid, []).append(node)

    # A station is considered freshly usable only when both its channel metadata
    # and actual programme rows were fetched. Missing stations keep their last
    # known guide instead of causing every RADIO station to disappear.
    fresh_ok = [
        tid for tid in wanted
        if tid in fresh_channels and len(fresh_programmes.get(tid, [])) >= 2
    ]
    if not fresh_ok:
        raise RuntimeError(
            "Radiko EPG: no selected station returned usable fresh programme data; "
            "leaving existing guides.xml untouched"
        )

    fallback = [
        tid for tid in wanted
        if tid not in fresh_ok and tid in old_channels and old_programmes.get(tid)
    ]
    truly_missing = [tid for tid in wanted if tid not in fresh_ok and tid not in fallback]

    # Remove only the selected Radiko rows. Non-Radiko entries and unrelated
    # radio IDs stay completely untouched.
    for node in list(main_root.findall("channel")):
        if (node.get("id") or "") in wanted_set:
            main_root.remove(node)
    for node in list(main_root.findall("programme")):
        if (node.get("channel") or "") in wanted_set:
            main_root.remove(node)

    merged_programmes = 0
    for tid in wanted:
        if tid in fresh_ok:
            main_root.append(fresh_channels[tid])
            for node in fresh_programmes.get(tid, []):
                main_root.append(node)
                merged_programmes += 1
        elif tid in fallback:
            main_root.append(old_channels[tid])
            for node in old_programmes.get(tid, []):
                main_root.append(node)
                merged_programmes += 1

    ET.ElementTree(main_root).write(GUIDES, encoding="utf-8", xml_declaration=True)

    print(
        f"Radiko EPG merged: {len(fresh_ok)} fresh / {len(fallback)} preserved / "
        f"{len(truly_missing)} unavailable / {merged_programmes} programmes"
    )
    if fallback:
        print("Radiko EPG preserved stations: " + ", ".join(fallback))
    if truly_missing:
        print("Radiko EPG unavailable stations: " + ", ".join(truly_missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
