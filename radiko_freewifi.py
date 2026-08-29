#!/usr/bin/env python3
import concurrent.futures
import os
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from radiko_epg import build_xmltv

FREEWIFI = Path("freewifi")
RADIO = Path("radio.m3u")
GUIDES = Path("guides.xml")
START = "# === RADIKO_MANAGED_START ==="
END = "# === RADIKO_MANAGED_END ==="
LOCAL_START = "# === LOCAL_RADIO_KEEP_START ==="
LOCAL_END = "# === LOCAL_RADIO_KEEP_END ==="
KICK_ANCHOR = "# === KICK_MANAGED_START ==="
YT_ANCHOR = "# === GENERAL_YOUTUBE_MANAGED_START ==="
UA = {"User-Agent": "Mozilla/5.0"}
BASE = os.environ.get("RADIKO_PUBLIC_BASE", "https://himitsu-six.vercel.app").rstrip("/")

FREEWIFI_IDS = {
    "RNB": "愛媛（ラジオ）",
    "JOEU-FM": "愛媛（ラジオ）",
    "ABC": "在阪（ラジオ）",
    "MBS": "在阪（ラジオ）",
    "OBC": "在阪（ラジオ）",
    "802": "在阪（ラジオ）",
    "CCL": "在阪（ラジオ）",
    "FMO": "在阪（ラジオ）",
    "KBS": "京都（ラジオ）",
    "ALPHA-STATION": "京都（ラジオ）",
    "E-RADIO": "滋賀（ラジオ）",
    "CRK": "兵庫（ラジオ）",
}


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
    area = f"JP{n}"
    try:
        with open_url(f"https://radiko.jp/v3/station/list/{area}.xml", 10) as r:
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
        out.append((sid, {"name": name, "logo": logo, "region": region_for_prefecture(n), "pref": n}))
    return out


def discover_stations():
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(fetch_area, n): n for n in range(1, 48)}
        for fut in concurrent.futures.as_completed(futs):
            n = futs[fut]
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
    n = (name or "").upper()
    return sid_u in {"RN1", "RN2"} or "ラジオNIKKEI" in name or "RADIO NIKKEI" in n


def freewifi_group(meta, sid):
    sid_u = (sid or "").upper()
    name = meta.get("name", "")
    upper = name.upper()
    if sid_u in FREEWIFI_IDS:
        return FREEWIFI_IDS[sid_u]
    if "南海放送" in name:
        return "愛媛（ラジオ）"
    if "FM愛媛" in name:
        return "愛媛（ラジオ）"
    if "ABCラジオ" in name or "MBSラジオ" in name or "ラジオ大阪" in name or "FM802" in upper or "FM COCOLO" in upper or "FM大阪" in name:
        return "在阪（ラジオ）"
    if "KBS京都" in name or "ALPHA-STATION" in upper or "Α-STATION" in upper or "α-STATION" in name:
        return "京都（ラジオ）"
    if "E-RADIO" in upper or "E RADIO" in upper or "FM滋賀" in name:
        return "滋賀（ラジオ）"
    if "ラジオ関西" in name or sid_u in {"CRK", "JOCR"}:
        return "兵庫（ラジオ）"
    return None


def strip_all_radiko_entries(text):
    lines = text.splitlines()
    out = []
    i = 0
    in_managed = False
    removed = 0
    while i < len(lines):
        line = lines[i]
        if line.strip() in {START, LOCAL_START}:
            in_managed = True
            i += 1
            continue
        if in_managed:
            if line.strip() in {END, LOCAL_END}:
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
        if line.strip().startswith("## RADIKO") or line.strip().startswith("## FreeWiFiに残すラジオ"):
            i += 1
            continue
        out.append(line)
        i += 1
    cleaned = "\n".join(out)
    cleaned = re.sub(r"\n{4,}", "\n\n\n", cleaned)
    return cleaned.rstrip() + "\n", removed


def insert_radiko_block(text, block):
    for anchor in (KICK_ANCHOR, YT_ANCHOR):
        if anchor in text:
            return text.replace(anchor, block.rstrip() + "\n\n" + anchor, 1)
    return text.rstrip() + "\n\n" + block.rstrip() + "\n"


def station_lines(sid, meta, group):
    name = meta["name"].replace("\n", " ").strip()
    if not name.endswith("（ラジオ）"):
        name += "（ラジオ）"
    logo = (meta.get("logo") or "").replace('"', "%22")
    station = urllib.parse.quote(sid, safe="")
    return [
        f'#EXTINF:-1 tvg-id="radiko.{sid}" tvg-logo="{logo}" group-title="{group}",{name}',
        f"{BASE}/api/radiko?station={station}",
    ]


def replace_radiko_block(stations):
    text = FREEWIFI.read_text(encoding="utf-8-sig")
    text, removed = strip_all_radiko_entries(text)
    items = [(sid, meta, freewifi_group(meta, sid)) for sid, meta in stations.items()]
    items = [(sid, meta, group) for sid, meta, group in items if group]
    items.sort(key=lambda x: (x[2], x[1].get("name", "")))

    lines = [START, "## 指定ラジオ局（FreeWiFiにもコピー）"]
    for sid, meta, group in items:
        lines.extend(station_lines(sid, meta, group))
    lines.append(END)
    FREEWIFI.write_text(insert_radiko_block(text, "\n".join(lines)), encoding="utf-8")
    return len(items), removed


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
        if is_shortwave_station(sid, meta.get("name", "")):
            group = "短波（ラジオ）"
        else:
            group = f'{meta.get("region", "その他")}（ラジオ）'
        all_radiko.append((meta.get("region", ""), meta.get("pref", 99), meta.get("name", ""), sid, meta, group))
    all_radiko.sort()

    kept.append("")
    kept.append("## RADIKO 全局")
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
    stations = discover_stations()
    if len(stations) < 100:
        raise SystemExit(f"radiko station discovery too small: {len(stations)}")
    freewifi_count, removed = replace_radiko_block(stations)
    radio_count = write_radio_playlist(stations)
    epg_channels, epg_programmes = merge_radiko_epg()
    print(f"old/duplicate radiko entries removed: {removed}")
    print(f"radiko FreeWiFi copied stations: {freewifi_count}")
    print(f"radiko radio.m3u all stations: {radio_count}")
    print(f"radiko public base: {BASE}")
    print(f"radiko EPG channels: {epg_channels}")
    print(f"radiko EPG programmes: {epg_programmes}")
    if freewifi_count < 8 or radio_count < 100:
        raise SystemExit("radiko catalog result too small")
    if epg_channels < 100 or epg_programmes < 500:
        raise SystemExit("radiko EPG result too small")


if __name__ == "__main__":
    main()
