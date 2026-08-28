#!/usr/bin/env python3
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from radiko_epg import build_xmltv

FREEWIFI = Path("freewifi")
GUIDES = Path("guides.xml")
START = "# === RADIKO_MANAGED_START ==="
END = "# === RADIKO_MANAGED_END ==="
KICK_ANCHOR = "# === KICK_MANAGED_START ==="
YT_ANCHOR = "# === GENERAL_YOUTUBE_MANAGED_START ==="
UA = {"User-Agent": "Mozilla/5.0"}
BASE = os.environ.get("RADIKO_PUBLIC_BASE", "https://himitsu-six.vercel.app").rstrip("/")
PREF = 13
AREA = "JP13"


def open_url(url, timeout=12):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout)


def discover_stations():
    with open_url(f"https://radiko.jp/v3/station/list/{AREA}.xml", 12) as r:
        root = ET.fromstring(r.read())
    stations = {}
    for st in root.findall("station"):
        sid = (st.findtext("id") or "").strip()
        if not sid:
            continue
        name = (st.findtext("name") or sid).strip()
        logos = []
        for node in st.findall("logo"):
            if not (node.text or "").strip():
                continue
            try:
                score = int(node.get("width") or 0) * int(node.get("height") or 0)
            except ValueError:
                score = 0
            logos.append((score, node.text.strip()))
        logo = max(logos, default=(0, ""), key=lambda x: x[0])[1]
        if not logo:
            for tag in ("logo_large", "logo_medium", "logo_small", "logo_xsmall"):
                logo = (st.findtext(tag) or "").strip()
                if logo:
                    break
        stations[sid] = {"name": name, "logo": logo}
    return stations


def is_shortwave_station(sid, name):
    sid_u = (sid or "").upper()
    n = (name or "").upper()
    return sid_u in {"RN1", "RN2"} or "ラジオNIKKEI" in name or "RADIO NIKKEI" in n


def strip_all_radiko_entries(text):
    lines = text.splitlines()
    out = []
    i = 0
    in_managed = False
    removed = 0
    while i < len(lines):
        line = lines[i]
        if line.strip() == START:
            in_managed = True
            i += 1
            continue
        if in_managed:
            if line.strip() == END:
                in_managed = False
            i += 1
            continue
        if 'tvg-id="radiko.' in line and line.lstrip().startswith("#EXTINF:"):
            removed += 1
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i < len(lines) and not lines[i].lstrip().startswith("#"):
                i += 1
            continue
        if line.strip().startswith("## RADIKO"):
            i += 1
            continue
        out.append(line)
        i += 1
    cleaned = "\n".join(out)
    cleaned = re.sub(r"\n{4,}", "\n\n\n", cleaned)
    return cleaned.rstrip() + "\n", removed


def insert_radiko_block(text, block):
    # Radio belongs after the normal/backup groups but before KICK and final YouTube.
    for anchor in (KICK_ANCHOR, YT_ANCHOR):
        if anchor in text:
            return text.replace(anchor, block.rstrip() + "\n\n" + anchor, 1)
    return text.rstrip() + "\n\n" + block.rstrip() + "\n"


def replace_radiko_block(stations):
    text = FREEWIFI.read_text(encoding="utf-8-sig")
    text, removed = strip_all_radiko_entries(text)

    items = sorted(stations.items(), key=lambda kv: kv[1]["name"])
    lines = [START, "## RADIKO（Vercel東京 / JP13）"]
    for sid, meta in items:
        name = meta["name"].replace("\n", " ").strip()
        if not name.endswith("（ラジオ）"):
            name += "（ラジオ）"
        logo = meta["logo"].replace('"', "%22")
        group = "短波（ラジオ）" if is_shortwave_station(sid, meta["name"]) else "関東（ラジオ）"
        lines.append(f'#EXTINF:-1 tvg-id="radiko.{sid}" tvg-logo="{logo}" group-title="{group}",{name}')
        lines.append(f"{BASE}/api/radiko?station={urllib.parse.quote(sid)}")
    lines.append(END)

    updated = insert_radiko_block(text, "\n".join(lines))
    FREEWIFI.write_text(updated, encoding="utf-8")
    return len(items), removed


def merge_radiko_epg():
    main_root = ET.parse(GUIDES).getroot()
    rad_root = ET.fromstring(build_xmltv(3, prefs=(PREF,)))

    for node in list(main_root.findall("channel")):
        if (node.get("id") or "").startswith("radiko."):
            main_root.remove(node)
    for node in list(main_root.findall("programme")):
        if (node.get("channel") or "").startswith("radiko."):
            main_root.remove(node)

    for ch in rad_root.findall("channel"):
        main_root.append(ch)
    for pr in rad_root.findall("programme"):
        main_root.append(pr)

    ET.indent(main_root, space="  ")
    ET.ElementTree(main_root).write(GUIDES, encoding="utf-8", xml_declaration=True)
    return len(rad_root.findall("channel")), len(rad_root.findall("programme"))


def main():
    stations = discover_stations()
    if len(stations) < 10:
        raise SystemExit(f"Tokyo Radiko station discovery too small: {len(stations)}")
    m3u_count, removed = replace_radiko_block(stations)
    epg_channels, epg_programmes = merge_radiko_epg()
    print(f"old/duplicate radiko entries removed: {removed}")
    print(f"Tokyo Radiko FreeWiFi stations: {m3u_count}")
    print(f"radiko public base: {BASE}")
    print(f"Tokyo Radiko EPG channels: {epg_channels}")
    print(f"Tokyo Radiko EPG programmes: {epg_programmes}")
    if epg_channels < 10 or epg_programmes < 200:
        raise SystemExit("Tokyo Radiko EPG result too small")


if __name__ == "__main__":
    main()
