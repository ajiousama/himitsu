#!/usr/bin/env python3
"""Publish verified today's KEIRIN race-by-race data on the 10-minute fast cycle.

Replace only today's KEIRIN rows for venues with a complete source race grid.
Never erase a last-known-good race grid when an upstream site is unavailable.
Both the dedicated ganble XMLTV and FreeWiFi's guides.xml are updated.
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
SOURCE = ROOT / "public_sports_epg_local.xml"
STATUS = ROOT / "today_public_sports_status.json"
VERIFIED = ROOT / "verified_daily_status.json"
DESTINATIONS = (ROOT / "ganble" / "epg.xml", ROOT / "guides.xml")
JST = timezone(timedelta(hours=9))
RACE = re.compile(r"^【[０-９0-9]{1,2}[ＲR]】")
FIRST_RACE = re.compile(r"^【[１1][ＲR]】")


def programme_signature(p: ET.Element) -> tuple[str, str, str, str]:
    return (
        p.get("start") or "",
        p.get("stop") or "",
        p.findtext("title") or "",
        p.findtext("desc") or "",
    )


def today_source() -> tuple[str, dict[str, ET.Element], dict[str, list[ET.Element]], list[str]]:
    today = datetime.now(JST).strftime("%Y%m%d")
    iso = f"{today[:4]}-{today[4:6]}-{today[6:]}"
    verified = json.loads(VERIFIED.read_text(encoding="utf-8-sig"))
    status = json.loads(STATUS.read_text(encoding="utf-8-sig"))
    if verified.get("date") != iso or not str(status.get("generated_at", "")).startswith(iso):
        raise ValueError("verified/status dates are stale; refusing any overlay")
    active = sorted(cid for cid in (status.get("channels") or {}) if cid.startswith("keirin."))
    declared = (verified.get("public_sports") or {}).get("競輪") or []
    if len(active) != len(declared):
        raise ValueError(f"active keirin count mismatch: status={len(active)} verified={len(declared)}")
    root = ET.parse(SOURCE).getroot()
    channels = {c.get("id"): c for c in root.findall("channel")}
    programmes = root.findall("programme")
    complete = {}
    incomplete = []
    for cid in active:
        rows = [p for p in programmes if p.get("channel") == cid and
                (p.get("start") or "").startswith(today)]
        races = [p for p in rows if RACE.match((p.findtext("title") or "").strip())]
        if (cid not in channels or len(races) < 2 or
                not any(FIRST_RACE.match((p.findtext("title") or "").strip()) for p in races)):
            incomplete.append(cid)
            continue
        complete[cid] = rows
    return today, channels, complete, incomplete


def publish_one(dest: Path, today: str, channels: dict, complete: dict) -> int:
    if not dest.is_file() or not dest.stat().st_size:
        print(f"::warning::KEIRIN FAST target missing: {dest}")
        return 0
    tree = ET.parse(dest)
    root = tree.getroot()
    existing = {c.get("id") for c in root.findall("channel")}
    changed = 0
    for cid, rows in complete.items():
        previous = [p for p in root.findall("programme") if p.get("channel") == cid and
                    (p.get("start") or "").startswith(today)]
        if [programme_signature(p) for p in previous] == [programme_signature(p) for p in rows]:
            continue
        for p in previous:
            root.remove(p)
        if cid not in existing:
            root.append(ET.fromstring(ET.tostring(channels[cid], encoding="utf-8")))
            existing.add(cid)
        for p in rows:
            root.append(ET.fromstring(ET.tostring(p, encoding="utf-8")))
        changed += 1

    if not changed:
        print(f"KEIRIN FAST current: {dest.name}, complete={len(complete)}")
        return 0

    # Only the small ganble EPG needs sorting. Do not reformat the large
    # FreeWiFi guide, which contains unrelated television and radio schedules.
    if dest == DESTINATIONS[0]:
        entries = list(root.findall("programme"))
        for p in entries:
            root.remove(p)
        root.extend(sorted(entries, key=lambda p: (p.get("start") or "", p.get("channel") or "")))
        ET.indent(tree, space="    ")

    for cid in complete:
        titles = [(p.findtext("title") or "").strip() for p in root.findall("programme")
                  if p.get("channel") == cid and (p.get("start") or "").startswith(today)]
        if not any(FIRST_RACE.match(t) for t in titles) or sum(bool(RACE.match(t)) for t in titles) < 2:
            raise ValueError(f"invalid race grid in {dest}: {cid}")
        if any("開催予定（仮時間）" in t for t in titles):
            raise ValueError(f"provisional KEIRIN survived in {dest}: {cid}")

    fd, pathname = tempfile.mkstemp(dir=dest.parent, suffix=".xml")
    tmp = Path(pathname)
    try:
        with os.fdopen(fd, "wb") as handle:
            tree.write(handle, encoding="utf-8", xml_declaration=True)
        os.replace(tmp, dest)
    finally:
        tmp.unlink(missing_ok=True)
    print(f"KEIRIN FAST published: {dest.name}, venues_changed={changed}")
    return changed


def main() -> int:
    try:
        today, channels, complete, incomplete = today_source()
    except (OSError, ValueError, json.JSONDecodeError, ET.ParseError) as exc:
        print(f"::warning::KEIRIN FAST source unavailable: {exc}; preserving existing EPG")
        return 0
    if incomplete:
        print(f"::warning::KEIRIN FAST incomplete source for {incomplete}; preserving those EPG rows")
    if not complete:
        print(f"::warning::KEIRIN FAST no complete race cards yet; keeping last-good EPG")
        return 0
    changed = {dest.name: publish_one(dest, today, channels, complete) for dest in DESTINATIONS}
    print(f"KEIRIN FAST result: verified={len(complete)} incomplete={len(incomplete)} changed={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
