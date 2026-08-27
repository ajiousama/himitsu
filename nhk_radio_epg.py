#!/usr/bin/env python3
from __future__ import annotations

import html
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

GUIDES = Path("guides.xml")
JST = timezone(timedelta(hours=9))

# らじる★らじるで採用している8地域とradikoエリアID。
AREAS = {
    "sapporo": ("札幌", "JP1"),
    "sendai": ("仙台", "JP4"),
    "tokyo": ("東京", "JP13"),
    "nagoya": ("名古屋", "JP23"),
    "osaka": ("大阪", "JP27"),
    "hiroshima": ("広島", "JP34"),
    "matsuyama": ("松山", "JP38"),
    "fukuoka": ("福岡", "JP40"),
}
SERVICES = {
    "r1": ("NHK AM", "NHKラジオ第1"),
    "fm": ("NHK FM", "NHK-FM"),
}


def fetch_xml(url: str) -> ET.Element:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 FreeWiFi-Radio-EPG/2.0",
            "Accept": "application/xml,text/xml,*/*",
        },
    )
    with urllib.request.urlopen(req, timeout=45) as r:
        return ET.fromstring(r.read())


def clean(s: str | None) -> str:
    if not s:
        return ""
    s = html.unescape(s)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    return re.sub(r"[ \t\r]+", " ", s).strip()


def parse_radiko_time(s: str) -> str:
    # ft/to は YYYYMMDDHHMMSS。radikoの25時以降表記も実値は翌日の日付で返る。
    dt = datetime.strptime(s, "%Y%m%d%H%M%S").replace(tzinfo=JST)
    return dt.strftime("%Y%m%d%H%M%S +0900")


def station_name(st: ET.Element) -> str:
    return clean(st.findtext("name"))


def find_station(root: ET.Element, needle: str) -> ET.Element | None:
    stations = root.find("stations")
    if stations is None:
        return None
    needle_n = needle.replace(" ", "").upper()
    for st in stations.findall("station"):
        name_n = station_name(st).replace(" ", "").upper()
        if needle_n in name_n:
            return st
    return None


def fetch_area_day(area_id: str, day: str) -> ET.Element:
    # radikoの番組表XML。APIキー不要。
    return fetch_xml(f"https://radiko.jp/v3/program/date/{day}/{area_id}.xml")


def extract_programmes(st: ET.Element) -> list[dict]:
    progs = st.find("progs")
    if progs is None:
        scd = st.find("scd")
        progs = scd.find("progs") if scd is not None else None
    if progs is None:
        return []
    out = []
    for p in progs.findall("prog"):
        ft, to = p.get("ft", ""), p.get("to", "")
        title = clean(p.findtext("title"))
        if not (re.fullmatch(r"\d{14}", ft) and re.fullmatch(r"\d{14}", to) and title):
            continue
        out.append({
            "ft": ft,
            "to": to,
            "title": title,
            "sub_title": clean(p.findtext("sub_title")),
            "desc": clean(p.findtext("desc")),
            "info": clean(p.findtext("info")),
            "pfm": clean(p.findtext("pfm")),
        })
    return out


def main() -> None:
    if not GUIDES.exists():
        raise SystemExit("guides.xml not found")
    tree = ET.parse(GUIDES)
    root = tree.getroot()

    target_ids = {f"nhk_{kind}_{slug}" for slug in AREAS for kind in SERVICES}

    # 先に取得してから置換する。全取得失敗時に既存EPGを消さないため。
    now = datetime.now(JST)
    days = [(now + timedelta(days=i)).strftime("%Y%m%d") for i in range(3)]
    fetched: dict[str, tuple[str, list[dict]]] = {}

    for slug, (area_name, area_id) in AREAS.items():
        day_roots = []
        for day in days:
            try:
                day_roots.append(fetch_area_day(area_id, day))
            except Exception as e:
                print(f"radiko failed {area_id}/{day}: {type(e).__name__}: {e}")
        for kind, (needle, label) in SERVICES.items():
            items: list[dict] = []
            actual_name = ""
            for day_root in day_roots:
                st = find_station(day_root, needle)
                if st is None:
                    continue
                actual_name = actual_name or station_name(st)
                items.extend(extract_programmes(st))
            uniq = {(x["ft"], x["to"], x["title"]): x for x in items}
            items = sorted(uniq.values(), key=lambda x: x["ft"])
            cid = f"nhk_{kind}_{slug}"
            if items:
                fetched[cid] = (actual_name or f"{label}（{area_name}）", items)
                print(f"OK {cid}: {len(items)} programmes")
            else:
                print(f"NO EPG: {label}（{area_name}）")

    if not fetched:
        raise SystemExit("NHK radio EPG: no programmes fetched from radiko")

    # 取得できた局だけ置換。局単位の一時障害なら既存EPGを残す。
    for cid in fetched:
        for el in list(root):
            if el.tag == "channel" and el.get("id") == cid:
                root.remove(el)
            elif el.tag == "programme" and el.get("channel") == cid:
                root.remove(el)

    total_programmes = 0
    for cid, (display_name, items) in fetched.items():
        ch = ET.SubElement(root, "channel", {"id": cid})
        ET.SubElement(ch, "display-name", {"lang": "ja"}).text = display_name
        for item in items:
            p = ET.SubElement(root, "programme", {
                "start": parse_radiko_time(item["ft"]),
                "stop": parse_radiko_time(item["to"]),
                "channel": cid,
            })
            ET.SubElement(p, "title", {"lang": "ja"}).text = item["title"]
            desc_parts = [item["sub_title"], item["desc"], item["pfm"], item["info"]]
            desc = "\n".join(x for x in desc_parts if x)
            if desc:
                ET.SubElement(p, "desc", {"lang": "ja"}).text = desc
            ET.SubElement(p, "category", {"lang": "ja"}).text = "ラジオ"
            total_programmes += 1

    ET.indent(tree, space="  ")
    tree.write(GUIDES, encoding="utf-8", xml_declaration=True)
    print(f"NHK radio EPG merged from radiko: {len(fetched)}/16 channels, {total_programmes} programmes")


if __name__ == "__main__":
    main()
