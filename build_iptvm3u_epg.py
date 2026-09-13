#!/usr/bin/env python3
from __future__ import annotations
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

SPORTS_EPG = "https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/epg.xml"
LOCAL_EPG = Path("guides.xml")
OUT = Path("iptvm3u_epg.xml")


def load_xml_bytes(src):
    if isinstance(src, Path):
        return src.read_bytes()
    req = urllib.request.Request(src, headers={"User-Agent": "IPTVM3U-EPG/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read()


def key_programme(el):
    return (
        el.get("channel", ""),
        el.get("start", ""),
        el.get("stop", ""),
        next((c.text or "" for c in el if c.tag == "title"), ""),
    )


def main():
    roots = [ET.fromstring(load_xml_bytes(LOCAL_EPG)), ET.fromstring(load_xml_bytes(SPORTS_EPG))]
    out_root = ET.Element("tv", {"generator-info-name": "IPTVM3U merged EPG"})

    seen_channels = set()
    seen_programmes = set()

    for root in roots:
        for ch in root.findall("channel"):
            cid = ch.get("id", "")
            if not cid or cid in seen_channels:
                continue
            seen_channels.add(cid)
            out_root.append(ch)

    for root in roots:
        for p in root.findall("programme"):
            k = key_programme(p)
            if k in seen_programmes:
                continue
            seen_programmes.add(k)
            out_root.append(p)

    tree = ET.ElementTree(out_root)
    ET.indent(tree, space="  ")
    tree.write(OUT, encoding="utf-8", xml_declaration=True)
    print(f"wrote {OUT}: {len(seen_channels)} channels, {len(seen_programmes)} programmes")


if __name__ == "__main__":
    main()
