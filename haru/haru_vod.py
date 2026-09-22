#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import re
import unicodedata
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from xml.sax.saxutils import unescape
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "haru_vod_favorites.json"
OUT = ROOT / "haru_vod.m3u"
RAW = "https://raw.githubusercontent.com/ajiousama/himitsu/main/"
JST = ZoneInfo("Asia/Tokyo")
PAIR_RE = re.compile(r"<!--\s*(https://haru\.charandom\.blog/stream/jp/[^\s<]+?replay\.m3u8\?[^\s<]*?start=\d+)\s*-->\s*<programme\b([^>]*)>(.*?)</programme>", re.S | re.I)
TITLE_RE = re.compile(r"<title(?:\s+[^>]*)?>(.*?)</title>", re.S | re.I)
ATTR_RE = re.compile(r'([\w:-]+)="([^"]*)"')
TAG_RE = re.compile(r"<[^>]+>")


def norm(s: str) -> str:
    return unicodedata.normalize("NFKC", unescape(s or "")).strip()


def clean(s: str) -> str:
    return norm(TAG_RE.sub("", s or ""))


def get_text(url: str) -> str:
    if url.startswith("file://"):
        return Path(url[7:]).read_text(encoding="utf-8", errors="replace")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 HARU-VOD/4.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read(50_000_000).decode("utf-8", "replace")


def fetch_epg() -> tuple[str, str]:
    url = os.environ.get("HARU_EPG_URL", "").strip()
    if not url:
        raise RuntimeError("HARU_EPG_URL is required; build_haru_kai_epg.py must run first")
    text = get_text(url)
    if "haru.charandom.blog/stream/jp/" not in text:
        raise RuntimeError("generated HARU replay comments not found")
    print(f"HARU VOD: generated EPG OK {url} ({len(text):,} chars)")
    return text, url


def parse_time(raw: str) -> datetime | None:
    m = re.match(r"^(\d{14})\s*([+-]\d{4})?", raw or "")
    if not m:
        return None
    try:
        return datetime.strptime(m.group(1) + " " + (m.group(2) or "+0900"), "%Y%m%d%H%M%S %z")
    except ValueError:
        return None


def duration(attrs: dict[str, str]) -> int:
    a, b = parse_time(attrs.get("start", "")), parse_time(attrs.get("stop", ""))
    if a and b:
        sec = int((b - a).total_seconds())
        if 300 <= sec <= 8 * 3600:
            return sec
    return 3600


def title_matches(title: str, rule: dict) -> bool:
    t = norm(title)
    inc = [norm(x) for x in rule.get("include", [])]
    exc = [norm(x) for x in rule.get("exclude", [])]
    return bool(inc) and any(x in t for x in inc) and not any(x in t for x in exc)


def source_slug(url: str) -> str:
    m = re.search(r"/stream/jp/([^/]+)/replay\.m3u8", url)
    return m.group(1) if m else ""


def episode_number(text: str) -> int | None:
    for pat in (r"#\s*(\d{1,4})", r"第\s*(\d{1,4})\s*(?:回|話)"):
        m = re.search(pat, norm(text), re.I)
        if m:
            return int(m.group(1))
    return None


def parse_epg(text: str, rules: list[dict], max_age_days: int) -> list[dict]:
    now = int(datetime.now(timezone.utc).timestamp())
    oldest = now - max_age_days * 86400
    out = []
    for m in PAIR_RE.finditer(text):
        url = unescape(m.group(1))
        attrs = dict(ATTR_RE.findall(m.group(2)))
        tm = TITLE_RE.search(m.group(3))
        sm = re.search(r"[?&]start=(\d+)", url)
        if not tm or not sm:
            continue
        title, start = clean(tm.group(1)), int(sm.group(1))
        dur = duration(attrs)
        end = start + dur
        if end > now + 60 or end < oldest:
            continue
        slug = source_slug(url)
        for rule in rules:
            if not title_matches(title, rule):
                continue
            preferred = rule.get("preferred_source")
            if preferred and preferred != slug:
                continue
            out.append({"rule": rule, "title": title, "url": url, "start": start, "duration": dur})
            break
    seen, unique = set(), []
    for item in sorted(out, key=lambda x: x["start"], reverse=True):
        key = (item["rule"]["id"], item["url"])
        if key not in seen:
            seen.add(key)
            unique.append(item)
    return unique


def probe(url: str, timeout: float) -> bool:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 HARU-VOD/4.0",
            "Referer": "https://haru.charandom.blog/",
            "Accept": "application/vnd.apple.mpegurl, application/x-mpegURL, text/plain, */*",
            "Cache-Control": "no-cache",
            "Range": "bytes=0-8191",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return b"#EXTM3U" in r.read(8192)
    except Exception as e:
        print("HARU VOD probe failed:", type(e).__name__, e, url)
        return False


def probe_items(items: list[dict], timeout: float) -> list[dict]:
    if not items:
        return []
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        results = list(ex.map(lambda x: probe(x["url"], timeout), items))
    return [x for x, ok in zip(items, results) if ok]


def limit_items(items: list[dict], rules: list[dict], cap: int) -> list[dict]:
    grouped = {}
    for item in items:
        grouped.setdefault(item["rule"]["id"], []).append(item)
    out = []
    for rule in rules:
        out.extend(sorted(grouped.get(rule["id"], []), key=lambda x: x["start"], reverse=True)[:cap])
    return out


def esc(s: str) -> str:
    return (s or "").replace('"', "'").replace("\n", " ").replace("\r", " ")


def build_m3u(items: list[dict], group: str, source: str) -> str:
    lines = ["#EXTM3U", f"# HARU VOD generated {datetime.now(JST).isoformat(timespec='seconds')} source={source}"]
    for item in items:
        rule = item["rule"]
        dt = datetime.fromtimestamp(item["start"], timezone.utc).astimezone(JST)
        ep = episode_number(item["title"])
        short = f" #{ep}" if ep is not None else ""
        label = f"📼 {rule['name']}{short} {dt:%m/%d %H:%M}｜{item['title']}"
        logo = RAW + rule["logo"]
        tvgid = f"haru.vod.{rule['id']}.{item['start']}"
        dur = max(30, min(int(item.get("duration") or 3600), 8 * 3600))
        lines.append(f'#EXTINF:{dur} tvg-id="{esc(tvgid)}" tvg-name="{esc(rule["name"])}" tvg-logo="{esc(logo)}" group-title="{esc(group)}",{esc(label)}')
        lines.append(item["url"])
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(DEFAULT_CONFIG))
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--probe-timeout", type=float, default=4.0)
    ap.add_argument("--max-age-days", type=int, default=14)
    ap.add_argument("--max-per-program", type=int, default=12)
    args = ap.parse_args()
    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    rules = cfg["programmes"]
    epg, source = fetch_epg()
    items = parse_epg(epg, rules, args.max_age_days)
    print(f"HARU VOD: matched {len(items)} candidates")

    # The HARU origin sometimes rejects a GitHub runner probe even though the same
    # replay works through the Render media resolver. Never wipe a populated shelf
    # just because every origin probe failed at once.
    if args.check and items:
        checked = probe_items(items, args.probe_timeout)
        print(f"HARU VOD: playable {len(checked)}/{len(items)} candidates by origin probe")
        if checked:
            items = checked
        else:
            print("HARU VOD: all origin probes failed; keeping matched candidates for Render proxy")

    items = limit_items(items, rules, args.max_per_program)
    vod = build_m3u(items, cfg.get("group_title", "VOD"), source)
    OUT.write_text(vod, encoding="utf-8")
    print(f"HARU VOD: wrote {OUT} with {len(items)} entries")


if __name__ == "__main__":
    main()
