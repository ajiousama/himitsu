#!/usr/bin/env python3
"""Build an isolated, short-lived Arva catch-up shelf from recorded XMLTV times.

Only programmes with a reachable HLS manifest are published in --probe mode.
This does NOT record television or copy/host its video.  Never print stream keys.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import time
import unicodedata
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
SOURCE = ROOT / "haru" / "haru_kai_epg_history.xml"
CONFIG = HERE / "programmes.json"
PLAYLIST = HERE / "playlist.m3u"
STATUS = HERE / "status.json"
JST = ZoneInfo("Asia/Tokyo")
RAW = "https://raw.githubusercontent.com/ajiousama/himitsu/main/"
LIVE_CONFIG = ROOT / "rakuten" / "freewifi_extra.m3u"
BASE_CHANNEL = re.compile(r"^[a-z0-9_-]+$")
VERSION = "1"


def normalized(value: str) -> str:
    return unicodedata.normalize("NFKC", value or "").casefold()


def asahi_allowed_dates(now: datetime) -> set:
    """Keep Fri+Sat across the weekend, but only the current weekday after 07:35 JST."""
    local = now.astimezone(JST)
    date = local.date()
    weekday = date.weekday()  # Mon=0, Sat=5, Sun=6
    after_clip = (local.hour, local.minute) >= (7, 35)
    if weekday == 6 or (weekday == 0 and not after_clip) or (weekday == 5 and after_clip):
        saturday = date - timedelta(days=(weekday - 5) % 7)
        return {saturday, saturday - timedelta(days=1)}
    if weekday == 5 and not after_clip:
        return {date - timedelta(days=1)}
    if not after_clip:
        return {date - timedelta(days=1)}
    return {date}


def timestamp(value: str) -> datetime:
    match = re.fullmatch(r"\s*(\d{14})\s*([+-]\d{4})\s*", value or "")
    if not match:
        raise ValueError("Invalid XMLTV datetime")
    return datetime.strptime(match.group(1) + " " + match.group(2), "%Y%m%d%H%M%S %z")


def bridge_config(path: Path) -> tuple[str, str]:
    content = path.read_text(encoding="utf-8")
    matches = re.findall(r"^https://nouvelle-paradise-bridge-production\.up\.railway\.app/playlist\.m3u8\?key=[A-Za-z0-9_-]{32,}$", content, re.M)
    if len(matches) != 1:
        raise RuntimeError("Expected exactly one canonical Railway bridge URL")
    address = urlparse(matches[0])
    token = parse_qs(address.query).get("key", [""])[0]
    return "https://" + address.netloc, token


def replay_link(base: str, key: str, slug: str, epoch: int) -> str:
    if not BASE_CHANNEL.fullmatch(slug):
        raise ValueError("Invalid channel slug")
    upstream = f"/stream/jp/{slug}/replay.m3u8?mode=hls&start={epoch}"
    encoded = base64.urlsafe_b64encode(upstream.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{base}/resource/{encoded}?key={key}"


def clip_link(base: str, key: str, slug: str, start: int, seconds: int) -> str:
    if not BASE_CHANNEL.fullmatch(slug) or not (30 <= seconds <= 3600):
        raise ValueError("Invalid clip parameters")
    return f"{base}/clip/{slug}/{start}/{seconds}.m3u8?key={key}"


def candidates(epg: Path, rules: list[dict], now: datetime, days: int) -> list[dict]:
    if not epg.is_file() or epg.stat().st_size < 256:
        raise RuntimeError("Rolling EPG history is unavailable or empty")
    root = ET.parse(epg).getroot()
    cutoff = now - timedelta(days=days)
    by_channel: dict[str, list[tuple[datetime, datetime, str]]] = defaultdict(list)
    wanted = {cid for r in rules for cid in r["channels"]}
    for p in root.iter("programme"):
        cid = p.get("channel", "")
        if cid not in wanted:
            continue
        try:
            start, end = timestamp(p.attrib["start"]), timestamp(p.attrib["stop"])
        except (ValueError, KeyError):
            continue
        if start > now or end > now or end < cutoff or end <= start:
            continue
        title = "".join(p.findtext("title", default="")).strip()
        if title:
            by_channel[cid].append((start, end, title))
    result = []
    seen = set()
    for rule in rules:
        found = []
        includes = [normalized(x) for x in rule["include"]]
        excludes = [normalized(x) for x in rule.get("exclude", [])]
        for cid, slug in rule["channels"].items():
            for start, end, title in by_channel.get(cid, []):
                t = normalized(title)
                if rule.get("retention_policy") == "asahi_latest" and start.astimezone(JST).date() not in asahi_allowed_dates(now):
                    continue
                if not any(x in t for x in includes) or any(x in t for x in excludes):
                    continue
                clip = rule.get("clip_start_jst")
                seconds = None
                if clip:
                    hour, minute = map(int, clip.split(":"))
                    local = start.astimezone(JST)
                    at = local.replace(hour=hour, minute=minute, second=0, microsecond=0)
                    clip_start = at.astimezone(timezone.utc)
                    seconds = int(rule["clip_duration_seconds"])
                    if not (start <= clip_start and clip_start + timedelta(seconds=seconds) <= end):
                        continue
                    epoch = int(clip_start.timestamp())
                else:
                    epoch = int(start.timestamp())
                signature = (rule["id"], epoch)
                if signature in seen:
                    continue
                seen.add(signature)
                found.append(dict(rule=rule, slug=slug, epoch=epoch, airtime=start, title=title, seconds=seconds))
        max_count = int(rule.get("max_per_program", 8))
        result.extend(sorted(found, key=lambda item: item["epoch"], reverse=True)[:max_count])
    return result


def verify_hls(url: str, timeout: float) -> bool:
    request = urllib.request.Request(url, headers={
        "User-Agent": "FreeWiFi-ArvaVOD/1.0",
        "Accept": "application/vnd.apple.mpegurl,application/x-mpegURL,*/*",
        "Cache-Control": "no-cache",
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            prefix = response.read(4096)
            return prefix.lstrip().startswith(b"#EXTM3U") and (
                b"#EXTINF:" in prefix or b"#EXT-X-STREAM-INF:" in prefix
            )
    except urllib.error.HTTPError as exc:
        if exc.code == 429:
            raise RuntimeError("Upstream rate-limited (HTTP 429); preserve previous shelf") from None
        return False
    except (urllib.error.URLError, TimeoutError):
        return False


def render(items: list[dict], group: str, base: str, key: str) -> str:
    lines = ["#EXTM3U", "# Arva catch-up: manifest checked; media playback is not certified. Short-lived links."]
    for item in items:
        rule, epoch = item["rule"], item["epoch"]
        slug = item["slug"]
        show_time = datetime.fromtimestamp(epoch, timezone.utc).astimezone(JST) if item["seconds"] else item["airtime"].astimezone(JST)
        label = f"📼 {rule['name']} {show_time:%m/%d %H:%M}｜{item['title']}"
        label = label.replace('"', "'").replace("\n", " ").replace("\r", " ")
        if item["seconds"]:
            url = clip_link(base, key, slug, epoch, item["seconds"])
        else:
            url = replay_link(base, key, slug, epoch)
        img = RAW + rule["logo"]
        lines.append(f'#EXTINF:-1 tvg-id="arva.vod.{rule["id"]}.{epoch}" tvg-name="{rule["name"]}" tvg-logo="{img}" group-title="{group}",{label}')
        lines.append(url)
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--epg", type=Path, default=SOURCE)
    parser.add_argument("--probe", action="store_true", help="Only include reachable HLS manifests")
    parser.add_argument("--timeout", type=float, default=10)
    parser.add_argument("--max-probes", type=int, default=80)
    args = parser.parse_args()
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    rules = config["programmes"]
    assert rules and len({r["id"] for r in rules}) == len(rules)
    days = min(6, max(1, int(config.get("catchup_days", 6))))
    now = datetime.now(timezone.utc)
    base, key = bridge_config(LIVE_CONFIG)
    found = candidates(args.epg, rules, now, days)
    accepted = []
    if args.probe:
        for item in found[:args.max_probes]:
            url = (clip_link(base, key, item["slug"], item["epoch"], item["seconds"])
                   if item["seconds"] else replay_link(base, key, item["slug"], item["epoch"]))
            if verify_hls(url, args.timeout):
                accepted.append(item)
            time.sleep(1.0)
        if found and not accepted:
            raise RuntimeError("No verified HLS manifests; preserving prior published VOD")
    else:
        accepted = found
    playlist = render(accepted, config.get("group_title", "VOD"), base, key)
    if accepted or not PLAYLIST.exists():
        PLAYLIST.write_text(playlist, encoding="utf-8")
    STATUS.write_text(json.dumps({
        "version": VERSION,
        "updated_at": now.isoformat(),
        "candidate_count": len(found),
        "manifest_confirmed_count": len(accepted),
        "per_program": {r["id"]: sum(x["rule"]["id"] == r["id"] for x in accepted) for r in rules},
        "playback_verified": False,
        "note": "VOD stream segments and clip boundaries still require player validation",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Arva VOD: {len(accepted)} manifest-checked entries from {len(found)} matching aired programmes")


if __name__ == "__main__":
    main()
