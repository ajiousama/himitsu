#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

GUIDES = Path("guides.xml")
JST = timezone(timedelta(hours=9))

# らじる★らじるの8地域。area はNHK番組表APIの地域ID。
AREAS = {
    "sapporo": ("札幌", "010"),
    "sendai": ("仙台", "040"),
    "tokyo": ("東京", "130"),
    "nagoya": ("名古屋", "230"),
    "osaka": ("大阪", "270"),
    "hiroshima": ("広島", "340"),
    "matsuyama": ("松山", "380"),
    "fukuoka": ("福岡", "400"),
}
SERVICES = {
    "r1": ("r1", "NHKラジオ第1"),
    "fm": ("r3", "NHK-FM"),
}


def fetch_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "FreeWiFi-NHK-Radio-EPG/1.0"})
    with urllib.request.urlopen(req, timeout=45) as r:
        return json.loads(r.read().decode("utf-8-sig"))


def fetch_day(area: str, service: str, day: str) -> list[dict]:
    # らじる★らじる向けのキー不要APIを優先。使えない場合は公式v2 APIへフォールバック。
    legacy = f"https://api.nhk.or.jp/r2/pg/list/4/{area}/{service}/{day}.json"
    try:
        data = fetch_json(legacy)
        items = (data.get("list") or {}).get(service)
        if isinstance(items, list) and items:
            return items
    except Exception as e:
        print(f"legacy failed {area}/{service}/{day}: {type(e).__name__}: {e}")

    key = os.environ.get("NHK_API_KEY", "").strip()
    if key:
        url = f"https://api.nhk.or.jp/v2/pg/list/{area}/{service}/{day}.json?key={key}"
        data = fetch_json(url)
        items = (data.get("list") or {}).get(service)
        if isinstance(items, list):
            return items
    return []


def dt_xml(s: str) -> str:
    dt = datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(JST)
    return dt.strftime("%Y%m%d%H%M%S +0900")


def text(v) -> str:
    return str(v or "").strip()


def main() -> None:
    if not GUIDES.exists():
        raise SystemExit("guides.xml not found")
    tree = ET.parse(GUIDES)
    root = tree.getroot()

    target_ids = {
        f"nhk_{kind}_{slug}"
        for slug in AREAS
        for kind in ("r1", "fm")
    }
    # 前回生成分/epg_buildのフォールバックを除去して実番組へ置換。
    for el in list(root):
        if el.tag == "channel" and el.get("id") in target_ids:
            root.remove(el)
        elif el.tag == "programme" and el.get("channel") in target_ids:
            root.remove(el)

    now = datetime.now(JST)
    days = [(now + timedelta(days=i)).date().isoformat() for i in range(3)]
    total_programmes = 0
    active_channels = 0

    for slug, (area_name, area_id) in AREAS.items():
        for kind, (service, label) in SERVICES.items():
            channel_id = f"nhk_{kind}_{slug}"
            programmes: list[dict] = []
            for day in days:
                programmes.extend(fetch_day(area_id, service, day))

            # 重複排除。
            unique = {}
            for item in programmes:
                key = (text(item.get("start_time")), text(item.get("end_time")), text(item.get("title")))
                if all(key):
                    unique[key] = item
            programmes = sorted(unique.values(), key=lambda x: text(x.get("start_time")))
            if not programmes:
                print(f"NO EPG: {label}（{area_name}）")
                continue

            ch = ET.SubElement(root, "channel", {"id": channel_id})
            ET.SubElement(ch, "display-name", {"lang": "ja"}).text = f"{label}（{area_name}）"
            active_channels += 1

            for item in programmes:
                start, stop = text(item.get("start_time")), text(item.get("end_time"))
                if not start or not stop:
                    continue
                p = ET.SubElement(root, "programme", {
                    "start": dt_xml(start),
                    "stop": dt_xml(stop),
                    "channel": channel_id,
                })
                ET.SubElement(p, "title", {"lang": "ja"}).text = text(item.get("title")) or f"{label}（{area_name}）"
                desc_parts = [text(item.get("subtitle")), text(item.get("content")), text(item.get("act"))]
                desc = "\n".join(x for x in desc_parts if x)
                if desc:
                    ET.SubElement(p, "desc", {"lang": "ja"}).text = desc
                genres = item.get("genres") or []
                if isinstance(genres, list) and genres:
                    ET.SubElement(p, "category", {"lang": "ja"}).text = text(genres[0])
                else:
                    ET.SubElement(p, "category", {"lang": "ja"}).text = "ラジオ"
                total_programmes += 1

    # 16局全部が一時的に取得不能なら、壊れたEPGをコミットしない。
    if active_channels == 0 or total_programmes == 0:
        raise SystemExit("NHK radio EPG: no programmes fetched")

    ET.indent(tree, space="  ")
    tree.write(GUIDES, encoding="utf-8", xml_declaration=True)
    print(f"NHK radio EPG merged: {active_channels}/16 channels, {total_programmes} programmes")


if __name__ == "__main__":
    main()
