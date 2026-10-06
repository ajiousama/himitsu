#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

STATUS = Path("tver/live_status.json")
OVERLAY = Path("tver/tver_epg.xml")
GUIDES = Path("guides.xml")
JST = timezone(timedelta(hours=9))

STATIC_TVER_IDS = {
    "tver.news24",
    "tver.tbs_newsdig",
}
DYNAMIC_PREFIX = "tver.special."


def parse_iso(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)


def epoch_dt(value) -> datetime | None:
    try:
        n = int(value or 0)
    except (TypeError, ValueError):
        return None
    if n <= 0:
        return None
    return datetime.fromtimestamp(n, timezone.utc).astimezone(JST)


def xmltv(dt: datetime) -> str:
    return dt.astimezone(JST).strftime("%Y%m%d%H%M%S +0900")


def clean_title(value: str, fallback: str) -> str:
    title = re.sub(r"\s+", " ", str(value or "")).strip()
    return title or fallback


def build_overlay() -> None:
    data = json.loads(STATUS.read_text(encoding="utf-8"))
    generated = parse_iso(data.get("generated_at")).astimezone(JST)
    root = ET.Element("tv", {
        "generator-info-name": "TVer live EPG overlay",
        "generator-info-url": "https://github.com/ajiousama/himitsu",
    })

    count = 0
    for row in data.get("entries") or []:
        cid = str(row.get("tvg_id") or "").strip()
        title = clean_title(row.get("title"), cid)
        if not cid or not title or title in {"配信休止", "配信準備中"}:
            continue

        start = epoch_dt(row.get("start_at"))
        stop = epoch_dt(row.get("end_at"))
        if start is None:
            # Rolling slot for streams whose public metadata omits wall-clock times.
            minute = (generated.minute // 10) * 10
            start = generated.replace(minute=minute, second=0, microsecond=0)
        if stop is None or stop <= start:
            stop = start + timedelta(minutes=30)

        ch = ET.SubElement(root, "channel", {"id": cid})
        ET.SubElement(ch, "display-name", {"lang": "ja"}).text = title

        p = ET.SubElement(root, "programme", {
            "start": xmltv(start),
            "stop": xmltv(stop),
            "channel": cid,
        })
        ET.SubElement(p, "title", {"lang": "ja"}).text = title
        ET.SubElement(p, "desc", {"lang": "ja"}).text = (
            "TVer Special Live。配信一覧を10分ごとに更新し、再生時に最新ストリームへ解決します。"
        )
        ET.SubElement(p, "category", {"lang": "ja"}).text = "TVer LIVE"
        count += 1

    ET.indent(root, space="  ")
    OVERLAY.write_bytes(ET.tostring(root, encoding="utf-8", xml_declaration=True))
    print(f"TVer EPG overlay built: channels={count}")


def managed_id(cid: str) -> bool:
    return cid in STATIC_TVER_IDS or cid.startswith(DYNAMIC_PREFIX)


def merge_guides() -> None:
    if not GUIDES.is_file() or GUIDES.stat().st_size < 100_000:
        raise SystemExit(
            f"guides.xml missing or suspiciously small: "
            f"{GUIDES.stat().st_size if GUIDES.exists() else 0}"
        )
    if not OVERLAY.is_file():
        raise SystemExit("TVer EPG overlay missing")

    root = ET.parse(GUIDES).getroot()
    overlay = ET.parse(OVERLAY).getroot()

    # Remove the previous TVer-live overlay, including streams that have ended.
    for node in list(root.findall("programme")):
        if managed_id(str(node.get("channel") or "")):
            root.remove(node)
    for node in list(root.findall("channel")):
        if managed_id(str(node.get("id") or "")):
            root.remove(node)

    for node in overlay.findall("channel"):
        root.append(ET.fromstring(ET.tostring(node, encoding="unicode")))
    for node in overlay.findall("programme"):
        root.append(ET.fromstring(ET.tostring(node, encoding="unicode")))

    ET.ElementTree(root).write(GUIDES, encoding="utf-8", xml_declaration=True)
    channels = len(overlay.findall("channel"))
    programmes = len(overlay.findall("programme"))
    print(f"TVer EPG merged: channels={channels} programmes={programmes} guides_bytes={GUIDES.stat().st_size}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-only", action="store_true")
    parser.add_argument("--merge-only", action="store_true")
    args = parser.parse_args()

    if args.merge_only:
        merge_guides()
        return
    build_overlay()
    if not args.build_only:
        merge_guides()


if __name__ == "__main__":
    main()
