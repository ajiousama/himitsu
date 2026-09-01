#!/usr/bin/env python3
import concurrent.futures
import os
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from radiko_epg import build_xmltv

RADIO = Path("radio.m3u")
GUIDES = Path("guides.xml")
UA = {"User-Agent": "Mozilla/5.0"}
RADIO_TV_BASE = os.environ.get(
    "RADIO_TV_BASE",
    "https://raw.githubusercontent.com/ajiousama/himitsu/radio-ts-assets",
).rstrip("/")


def region_for_prefecture(n):
    if n == 1:
        return "北海道"
    if 2 <= n <= 7:
        return "東北"
    if 8 <= n <= 14:
        return "関東"
    if 15 <= n <= 20:
        return "甲信越"
    if 21 <= n <= 24:
        return "東海"
    if 25 <= n <= 30:
        return "近畿"
    if 31 <= n <= 35:
        return "中国"
    if 36 <= n <= 39:
        return "四国"
    return "九州沖縄"


def open_url(url, timeout=12):
    return urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=timeout)


def fetch_area(n):
    try:
        with open_url(f"https://radiko.jp/v3/station/list/JP{n}.xml", 10) as r:
            root = ET.fromstring(r.read())
    except Exception:
        return []
    out = []
    for st in root.findall("station"):
        sid = (st.findtext("id") or "").strip()
        if not sid:
            continue
        name = (st.findtext("name") or sid).strip()
        logos = []
        for node in st.findall("logo"):
            text = (node.text or "").strip()
            if not text:
                continue
            try:
                score = int(node.get("width") or 0) * int(node.get("height") or 0)
            except ValueError:
                score = 0
            logos.append((score, text))
        logo = max(logos, default=(0, ""), key=lambda x: x[0])[1]
        if not logo:
            for tag in ("logo_large", "logo_medium", "logo_small", "logo_xsmall"):
                logo = (st.findtext(tag) or "").strip()
                if logo:
                    break
        out.append((sid, {"name": name, "logo": logo, "region": region_for_prefecture(n), "pref": n}))
    return out


def discover_stations():
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        futures = {ex.submit(fetch_area, n): n for n in range(1, 48)}
        for fut in concurrent.futures.as_completed(futures):
            n = futures[fut]
            try:
                results[n] = fut.result()
            except Exception:
                results[n] = []
    stations = {}
    for n in range(1, 48):
        for sid, meta in results.get(n, []):
            stations.setdefault(sid, meta)
    return stations


def is_shortwave_station(sid, name):
    sid_u = (sid or "").upper()
    name_u = (name or "").upper()
    return sid_u in {"RN1", "RN2"} or "ラジオNIKKEI" in (name or "") or "RADIO NIKKEI" in name_u


def station_lines(sid, meta, group):
    name = meta["name"].replace("\n", " ").strip()
    if not name.endswith("（ラジオ）"):
        name += "（ラジオ）"
    logo = (meta.get("logo") or "").replace('"', "%22")
    station = urllib.parse.quote(sid, safe="")
    return [
        f'#EXTINF:-1 tvg-id="radiko.{sid}" tvg-logo="{logo}" group-title="{group}",{name}',
        f"{RADIO_TV_BASE}/{station}/master.m3u8",
    ]


def write_radio_playlist(stations):
    old = RADIO.read_text(encoding="utf-8-sig") if RADIO.exists() else "#EXTM3U\n"
    lines = old.splitlines()
    kept = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#EXTM3U"):
            if not kept:
                kept.append("#EXTM3U")
            i += 1
            continue
        if line.lstrip().startswith("#EXTINF:") and 'tvg-id="radiko.' in line:
            i += 2
            continue
        if line.strip() in {"## RADIKO その他局", "## RADIKO 全局"}:
            i += 1
            continue
        kept.append(line)
        i += 1
    while kept and not kept[-1].strip():
        kept.pop()

    all_radiko = []
    for sid, meta in stations.items():
        group = "短波（ラジオ）" if is_shortwave_station(sid, meta.get("name", "")) else f'{meta.get("region", "その他")}（ラジオ）'
        all_radiko.append((meta.get("region", ""), meta.get("pref", 99), meta.get("name", ""), sid, meta, group))
    all_radiko.sort()

    kept.extend(["", "## RADIKO 全局"])
    for _, _, _, sid, meta, group in all_radiko:
        kept.extend(station_lines(sid, meta, group))
    RADIO.write_text("\n".join(kept).rstrip() + "\n", encoding="utf-8")
    return len(all_radiko)


def merge_radiko_epg():
    main_root = ET.parse(GUIDES).getroot()
    rad_root = ET.fromstring(build_xmltv(3))
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
    playlist_only = "--playlist-only" in sys.argv[1:]
    stations = discover_stations()
    if len(stations) < 100:
        raise SystemExit(f"radiko station discovery too small: {len(stations)}")
    radio_count = write_radio_playlist(stations)
    print(f"radio.m3u stable TS Radiko stations: {radio_count}")
    print("FreeWiFi untouched")
    if radio_count < 100:
        raise SystemExit("Radiko catalog result too small")

    if playlist_only:
        return

    epg_channels, epg_programmes = merge_radiko_epg()
    print(f"Radiko EPG channels: {epg_channels}; programmes: {epg_programmes}")
    if epg_channels < 100 or epg_programmes < 500:
        raise SystemExit("Radiko EPG result too small")


if __name__ == "__main__":
    main()
