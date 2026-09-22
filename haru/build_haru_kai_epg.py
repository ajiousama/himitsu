#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

GUIDES = "https://raw.githubusercontent.com/karenda-jp/etc/main/guides.xml"
COMMITS = "https://api.github.com/repos/karenda-jp/etc/commits?path=guides.xml&per_page=30"
RAW_AT = "https://raw.githubusercontent.com/karenda-jp/etc/{sha}/guides.xml"
OUT = Path(__file__).with_name("haru_kai_epg.xml")
HISTORY = Path(__file__).with_name("haru_kai_epg_history.xml")
BACKFILL_DAYS = 14

# guides.xml channel id -> HARU replay source.
CHANNELS = {
    "NHK東京・教育_jp": "nhk_e",
    "NHK大阪・教育_jp": "nhk_e",
    "日本テレビ_jp": "ntv",
    "テレビ朝日_jp": "tv_asahi",
    "TBS_jp": "tbs",
    "テレ東_jp": "tv_tokyo",
    "フジテレビ_jp": "fuji_tv",
    "毎日テレビ_jp": "mbs",
    "ABCテレビ_jp": "abc",
    "テレビ大阪_jp": "tv_osaka",
    "関西テレビ_jp": "kansai_tv",
    "読売テレビ_jp": "ytv",
    "KBS京都_jp": "kbs",
    "サンテレビ_jp": "sun",
}


def fetch(url: str, limit: int = 50_000_000) -> bytes:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 HARU-KAI-EPG/2.0",
            "Accept": "application/vnd.github+json, application/xml, text/xml, */*",
        },
    )
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read(limit)


def parse_xmltv_time(raw: str) -> datetime:
    return datetime.strptime(raw.strip(), "%Y%m%d%H%M%S %z")


def title_of(p: ET.Element) -> str:
    t = p.find("title")
    return "" if t is None else "".join(t.itertext()).strip()


def add_snapshot(
    data: bytes,
    programmes: dict[tuple[str, str, str, str], tuple[datetime, str, ET.Element]],
    channels: dict[str, ET.Element],
    cutoff: datetime,
    future_limit: datetime,
) -> int:
    root = ET.fromstring(data)
    for c in root.findall("channel"):
        cid = c.attrib.get("id", "")
        if cid in CHANNELS and cid not in channels:
            channels[cid] = c

    added = 0
    for p in root.findall("programme"):
        ch = p.attrib.get("channel", "")
        source = CHANNELS.get(ch)
        if not source:
            continue
        try:
            start = parse_xmltv_time(p.attrib.get("start", ""))
        except Exception:
            continue
        if start < cutoff or start > future_limit:
            continue
        stop_raw = p.attrib.get("stop", "")
        title = title_of(p)
        key = (ch, p.attrib.get("start", ""), stop_raw, title)
        if key in programmes:
            continue
        epoch = int(start.astimezone(timezone.utc).timestamp())
        replay = f"https://haru.charandom.blog/stream/jp/{source}/replay.m3u8?mode=hls&start={epoch}"
        programmes[key] = (start, replay, p)
        added += 1
    return added


def oldest_start(programmes: dict) -> datetime | None:
    past = [v[0] for v in programmes.values() if v[0] <= datetime.now(timezone.utc)]
    return min(past) if past else None


def backfill_from_git(
    programmes: dict,
    channels: dict,
    cutoff: datetime,
    future_limit: datetime,
) -> int:
    rows = json.loads(fetch(COMMITS, 2_000_000).decode("utf-8", "replace"))
    total = 0
    seen_sha: set[str] = set()
    for row in rows:
        sha = str(row.get("sha") or "").strip()
        if not sha or sha in seen_sha:
            continue
        seen_sha.add(sha)
        try:
            stamp = row["commit"]["committer"]["date"]
            commit_dt = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        except Exception:
            commit_dt = None
        if commit_dt is not None and commit_dt < cutoff - timedelta(days=2):
            break
        try:
            n = add_snapshot(fetch(RAW_AT.format(sha=sha)), programmes, channels, cutoff, future_limit)
            total += n
            print(f"HARU KAI EPG backfill {sha[:7]}: +{n}")
        except Exception as e:
            print(f"HARU KAI EPG backfill {sha[:7]} failed: {type(e).__name__}: {e}")
    return total


def render(
    programmes: dict[tuple[str, str, str, str], tuple[datetime, str, ET.Element]],
    channels: dict[str, ET.Element],
) -> str:
    used = {k[0] for k in programmes}
    out = ['<?xml version="1.0" encoding="UTF-8"?>', '<tv generator-info-name="himitsu HARU replay EPG history">']
    for cid in CHANNELS:
        c = channels.get(cid)
        if c is not None and cid in used:
            out.append(ET.tostring(c, encoding="unicode"))
    for _, replay, p in sorted(programmes.values(), key=lambda x: x[0]):
        out.append(f"<!-- {html.escape(replay)} -->")
        out.append(ET.tostring(p, encoding="unicode"))
    out.append("</tv>")
    return "\n".join(out) + "\n"


def main() -> None:
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=BACKFILL_DAYS)
    future_limit = now + timedelta(days=7)
    programmes: dict[tuple[str, str, str, str], tuple[datetime, str, ET.Element]] = {}
    channels: dict[str, ET.Element] = {}

    # Keep the persisted rolling history first, then add the newest EPG snapshot.
    if HISTORY.exists() and HISTORY.stat().st_size > 100:
        try:
            n = add_snapshot(HISTORY.read_bytes(), programmes, channels, cutoff, future_limit)
            print(f"HARU KAI EPG history cache: {n} programmes")
        except Exception as e:
            print(f"HARU KAI EPG history cache ignored: {type(e).__name__}: {e}")

    current = fetch(GUIDES)
    n_current = add_snapshot(current, programmes, channels, cutoff, future_limit)
    print(f"HARU KAI EPG current snapshot: +{n_current}")

    # The first run (or a damaged/thin cache) walks daily guides.xml commits so
    # programmes already aired during the last two weeks can still become VOD.
    oldest = oldest_start(programmes)
    if oldest is None or oldest > now - timedelta(days=10):
        added = backfill_from_git(programmes, channels, cutoff, future_limit)
        print(f"HARU KAI EPG historical backfill: +{added}")

    text = render(programmes, channels)
    OUT.write_text(text, encoding="utf-8")
    HISTORY.write_text(text, encoding="utf-8")
    oldest = oldest_start(programmes)
    oldest_s = oldest.isoformat() if oldest else "none"
    print(f"HARU KAI EPG: {len(programmes)} programmes / {len({k[0] for k in programmes})} channels / oldest={oldest_s}")
    print(f"HARU KAI EPG -> {OUT} and {HISTORY}")


if __name__ == "__main__":
    main()
