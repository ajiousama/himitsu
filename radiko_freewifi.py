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
GUIDES = Path("guides.xml")
START = "# === RADIKO_MANAGED_START ==="
END = "# === RADIKO_MANAGED_END ==="
UA = {"User-Agent": "Mozilla/5.0"}
BASE = os.environ.get("RADIKO_PUBLIC_BASE", "https://desktop-h41fq90.tailde6548.ts.net").rstrip("/")


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


def replace_radiko_block(stations):
    text = FREEWIFI.read_text(encoding="utf-8-sig")
    pattern = re.compile(r"\n?" + re.escape(START) + r".*?" + re.escape(END) + r"\n?", re.S)
    text = pattern.sub("\n", text)

    order_names = ("北海道", "東北", "関東", "甲信越", "東海", "近畿", "中国", "四国", "九州沖縄")
    order = {name: i for i, name in enumerate(order_names)}
    items = sorted(stations.items(), key=lambda kv: (order.get(kv[1]["region"], 99), kv[1]["pref"], kv[1]["name"]))

    lines = ["", START, "## RADIKO（地域別＋短波）"]
    for sid, meta in items:
        name = meta["name"].replace("\n", " ").strip()
        if not name.endswith("（ラジオ）"):
            name += "（ラジオ）"
        logo = meta["logo"].replace('"', "%22")
        if is_shortwave_station(sid, meta["name"]):
            group = "短波（ラジオ）"
        else:
            group = f'{meta["region"]}（ラジオ）'
        lines.append(f'#EXTINF:-1 tvg-id="radiko.{sid}" tvg-logo="{logo}" group-title="{group}",{name}')
        lines.append(f"{BASE}/live/{urllib.parse.quote(sid)}")
    lines.extend([END, ""])

    FREEWIFI.write_text(text.rstrip() + "\n" + "\n".join(lines), encoding="utf-8")
    return len(items)


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

    ET.ElementTree(main_root).write(GUIDES, encoding="utf-8", xml_declaration=True)
    return len(rad_root.findall("channel")), len(rad_root.findall("programme"))


def main():
    stations = discover_stations()
    if len(stations) < 100:
        raise SystemExit(f"radiko station discovery too small: {len(stations)}")
    m3u_count = replace_radiko_block(stations)
    epg_channels, epg_programmes = merge_radiko_epg()
    print(f"radiko FreeWiFi stations: {m3u_count}")
    print(f"radiko public base: {BASE}")
    print(f"radiko EPG channels: {epg_channels}")
    print(f"radiko EPG programmes: {epg_programmes}")
    if epg_channels < 100 or epg_programmes < 500:
        raise SystemExit("radiko EPG result too small")


if __name__ == "__main__":
    main()
