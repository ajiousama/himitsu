#!/usr/bin/env python3
"""Overlay today's verified KEIRIN race-by-race XMLTV onto ganble/epg.xml.

The ganble three-day generator can fall back to broad "開催予定（仮時間）"
blocks even when FreeWiFi has today's real race-card schedule. Do not publish
those fallback blocks for active venues when a complete local guide exists.
This script deliberately leaves other sports and future dates untouched.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = Path(__file__).resolve().parent / "epg.xml"
SOURCES = (ROOT / "guides.xml", ROOT / "public_sports_epg_local.xml")
STATUS = ROOT / "today_public_sports_status.json"
VERIFIED = ROOT / "verified_daily_status.json"
JST = timezone(timedelta(hours=9))
RACE_RE = re.compile(r"^【[０-９0-9]{1,2}[ＲR]】")
FIRST_RACE_RE = re.compile(r"^【[１1][ＲR]】")


def read_status(today: str) -> list[str]:
    verified = json.loads(VERIFIED.read_text(encoding="utf-8-sig"))
    if verified.get("date", "").replace("-", "") != today:
        raise RuntimeError("Verified sports status is not for today")
    expected = len((verified.get("public_sports") or {}).get("競輪") or [])
    data = json.loads(STATUS.read_text(encoding="utf-8-sig"))
    if not (data.get("generated_at") or "").startswith(
        f"{today[:4]}-{today[4:6]}-{today[6:]}"
    ):
        raise RuntimeError("Today sports status is stale")
    active = sorted(
        cid for cid in (data.get("channels") or {})
        if cid.startswith("keirin.")
    )
    if expected != len(active):
        raise RuntimeError(f"KEIRIN status mismatch: verified={expected}, mapped={len(active)}")
    return active


def source_rows(source: Path, today: str, active: list[str]):
    if not source.is_file() or not source.stat().st_size:
        return None
    root = ET.parse(source).getroot()
    channel_nodes = {c.get("id"): c for c in root.findall("channel")}
    programmes = root.findall("programme")
    selected = {}
    for cid in active:
        rows = [
            p for p in programmes
            if p.get("channel") == cid
            and (p.get("start") or "").startswith(today)
        ]
        races = [
            p for p in rows if RACE_RE.match((p.findtext("title") or "").strip())
        ]
        if (
            cid not in channel_nodes or
            len(races) < 2 or
            not any(FIRST_RACE_RE.match((p.findtext("title") or "").strip()) for p in races)
        ):
            return None
        selected[cid] = rows
    return channel_nodes, selected


def main() -> None:
    today = datetime.now(JST).strftime("%Y%m%d")
    active = read_status(today)
    if not active:
        print(f"GANBLE KEIRIN: no active venues for {today}")
        return

    selected = None
    used_source = None
    for source in SOURCES:
        selected = source_rows(source, today, active)
        if selected is not None:
            used_source = source
            break
    if selected is None:
        raise RuntimeError(
            "No complete verified race-by-race KEIRIN source available; "
            "refusing to publish broad provisional EPG"
        )

    src_channels, src_rows = selected
    tree = ET.parse(DEST)
    root = tree.getroot()
    active_set = set(active)
    for p in list(root.findall("programme")):
        if (
            p.get("channel") in active_set and
            (p.get("start") or "").startswith(today)
        ):
            root.remove(p)
    existing_ids = {ch.get("id") for ch in root.findall("channel")}
    for cid in active:
        if cid not in existing_ids:
            root.append(ET.fromstring(ET.tostring(src_channels[cid], encoding="utf-8")))
        for p in src_rows[cid]:
            root.append(ET.fromstring(ET.tostring(p, encoding="utf-8")))

    # Sort programmes; preserve channel definition nodes and all other sport data.
    programmes = list(root.findall("programme"))
    for p in programmes:
        root.remove(p)
    programmes.sort(key=lambda p: (p.get("start") or "", p.get("channel") or ""))
    root.extend(programmes)

    # Post-write guard: race-by-race titles must remain in today's ganble EPG.
    for cid in active:
        titles = [
            (p.findtext("title") or "").strip() for p in root.findall("programme")
            if p.get("channel") == cid and (p.get("start") or "").startswith(today)
        ]
        if sum(bool(RACE_RE.match(t)) for t in titles) < 2:
            raise RuntimeError(f"KEIRIN race titles disappeared: {cid}")
        if any("開催予定（仮時間）" in t for t in titles):
            raise RuntimeError(f"Provisional KEIRIN EPG still present: {cid}")

    ET.indent(tree, space="    ")
    with tempfile.NamedTemporaryFile(mode="wb", dir=DEST.parent, suffix=".xml", delete=False) as f:
        tmp_path = Path(f.name)
    try:
        tree.write(tmp_path, encoding="utf-8", xml_declaration=True)
        os.replace(tmp_path, DEST)
    finally:
        tmp_path.unlink(missing_ok=True)
    print(
        f"GANBLE KEIRIN LIVE RACES OK: date={today} "
        f"venues={len(active)} race_programmes={sum(len(v) for v in src_rows.values())} "
        f"source={used_source.name}"
    )


if __name__ == "__main__":
    main()
