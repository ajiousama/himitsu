#!/usr/bin/env python3
"""EPG-driven, opt-in video catalog for keirin and local horse racing.

Never mistake a scheduled race for a playable video. Videos are exposed only
when a separately checked, explicitly approved HTTPS media URL is supplied.
This module does not copy, scrape, download or proxy source videos.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import unicodedata
from urllib.parse import urlsplit
import xml.etree.ElementTree as ET

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
KINDS = {"keirin.": ("keirin", "競輪", "TIPSTAR", "https://tipstar.com/"),
         "chihou.": ("nar", "地方競馬", "楽天競馬", "https://keiba.rakuten.co.jp/archivemovie/searchDate")}
RACE = re.compile(r"^\s*【\s*(\d{1,2})\s*R\s*】")
CLOCK = re.compile(r"(\d{1,2}):([0-5]\d)\s*発走")


def normalized(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").strip()


def timestamp(value: str) -> datetime:
    return datetime.strptime(value, "%Y%m%d%H%M%S %z").astimezone(JST)


def race_start(programme: ET.Element, title: str) -> tuple[datetime, str] | None:
    """Use advertised race time, not XMLTV's programme lead-in time."""
    match = CLOCK.search(title)
    if not match:
        return None
    hour, minute = map(int, match.groups())
    if hour > 47:
        return None
    try:
        anchor = timestamp(programme.attrib["start"])
    except (ValueError, KeyError):
        return None
    candidates = [anchor.replace(hour=hour % 24, minute=minute, second=0)
                  + timedelta(days=day) for day in (-1, 0, 1)]
    actual = min(candidates, key=lambda d: abs((d - anchor).total_seconds()))
    meeting_day = actual.date() - timedelta(days=hour // 24)
    return actual, meeting_day.isoformat()


def extract(xml_path: Path) -> list[dict]:
    root = ET.parse(xml_path).getroot()
    names = {e.attrib["id"]: e.findtext("display-name") or e.attrib["id"]
             for e in root.findall("channel") if "id" in e.attrib}
    races: dict[str, dict] = {}
    for item in root.iter("programme"):
        channel = item.get("channel", "")
        matching = next((kind for prefix, kind in KINDS.items()
                         if channel.startswith(prefix)), None)
        if matching is None:
            continue
        title = normalized(item.findtext("title") or "")
        match = RACE.match(title)
        if not match:
            continue
        number = int(match.group(1))
        if not 1 <= number <= 12:
            continue
        start = race_start(item, title)
        if start is None:
            continue
        dt, day = start
        kind, kind_name, provider, page = matching
        name = normalized(names.get(channel, channel))
        desc = normalized(item.findtext("desc") or "")
        ident = f"{kind}:{day.replace('-', '')}:{channel}:{number:02d}"
        races[ident] = {
            "id": ident, "sport": kind, "sport_name": kind_name,
            "channel_id": channel, "venue": name, "date": day,
            "race": number, "scheduled_at": dt.isoformat(timespec="seconds"),
            "title": title, "description": desc,
            "provider": provider, "archive_search_url": page,
            "video_status": "not_verified", "video_url": None,
        }
    return sorted(races.values(), key=lambda x: (x["date"], x["sport"], x["venue"], x["race"]))


def safe_video_url(value: str) -> bool:
    """Only explicit HTTPS direct media URLs; no fabricated/catchup links."""
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return (parsed.scheme == "https" and bool(parsed.hostname)
            and not parsed.username and not parsed.password
            and parsed.path.lower().endswith((".m3u8", ".mp4")))


def assemble(epg: list[dict], previous: list[dict], approved: dict,
             now: datetime, keep_days: int = 45) -> list[dict]:
    now = now.astimezone(JST)
    minimum = (now.date() - timedelta(days=keep_days)).isoformat()
    history = {rec["id"]: rec for rec in previous
               if rec.get("sport") in {"keirin", "nar"}
               and isinstance(rec.get("date"), str) and rec["date"] >= minimum}
    for rec in epg:
        history[rec["id"]] = rec
    result = []
    for ident, record in history.items():
        row = dict(record)
        row["video_status"] = "not_verified"
        row["video_url"] = None
        source = approved.get(ident)
        if isinstance(source, dict) and source.get("playback_verified") is True:
            value = source.get("url")
            if isinstance(value, str) and safe_video_url(value):
                row["video_status"] = "verified"
                row["video_url"] = value
        try:
            when = datetime.fromisoformat(row["scheduled_at"])
        except (ValueError, KeyError):
            continue
        row["race_status"] = "scheduled" if when > now else "finished_or_started"
        if row["date"] >= minimum:
            result.append(row)
    return sorted(result, key=lambda x: (x["date"], x["sport"], x["venue"], x["race"]), reverse=True)


def read_json(path: Path, default):
    if not path.is_file():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def m3u(rows: list[dict]) -> str:
    lines = ["#EXTM3U"]
    for row in rows:
        if row["video_status"] != "verified" or not row["video_url"]:
            continue
        label = f'📼 {row["sport_name"]} {row["date"]} {row["venue"]} {row["race"]}R'
        lines.append(f'#EXTINF:-1 group-title="公営競技VOD" tvg-id="{row["id"]}",{label}')
        lines.append(row["video_url"])
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--epg", type=Path, default=ROOT / "public_sports_epg_local.xml")
    parser.add_argument("--catalog", type=Path, default=OUT / "catalog.json")
    parser.add_argument("--sources", type=Path, default=OUT / "verified_sources.json")
    parser.add_argument("--playlist", type=Path, default=OUT / "playlist.m3u")
    parser.add_argument("--now", help="ISO-8601 override for tests")
    args = parser.parse_args()
    now = datetime.fromisoformat(args.now) if args.now else datetime.now(JST)
    previous = read_json(args.catalog, {"races": []}).get("races", [])
    sources = read_json(args.sources, {})
    rows = assemble(extract(args.epg), previous, sources, now)
    args.catalog.parent.mkdir(parents=True, exist_ok=True)
    payload = {"schema_version": 1, "sources": ["TIPSTAR", "楽天競馬"], "races": rows,
               "warning": "No video is playable until its direct URL has been independently verified."}
    args.catalog.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    args.playlist.write_text(m3u(rows), encoding="utf-8")
    print(f"EPG races: {len(rows)}; verified playable sources: "
          f"{sum(r['video_status'] == 'verified' for r in rows)}")


if __name__ == "__main__":
    main()
