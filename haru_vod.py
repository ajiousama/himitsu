#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import gzip
import json
import os
import re
import sys
import unicodedata
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from xml.sax.saxutils import unescape
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
DEFAULT_CONFIG = ROOT / "haru_vod_favorites.json"
OUT = ROOT / "haru_vod.m3u"
FREEWIFI = ROOT / "freewifi"
RAW = "https://raw.githubusercontent.com/ajiousama/himitsu/main/"
DISCOVERY = "https://raw.githubusercontent.com/TvJapan/iptv-jp/main/jp_relay.m3u"
FALLBACK_EPG = "https://akariko−bck1.sankuria.sbs/epg/kai-epg.xml"
JST = ZoneInfo("Asia/Tokyo")
START_MARKER = "# === HARU_VOD_START ==="
END_MARKER = "# === HARU_VOD_END ==="

PAIR_RE = re.compile(
    r"<!--\s*(https://haru\.charandom\.blog/stream/jp/[^\s<]+?replay\.m3u8\?[^\s<]*?start=\d+)\s*-->\s*"
    r"<programme\b([^>]*)>(.*?)</programme>",
    re.S | re.I,
)
TITLE_RE = re.compile(r"<title(?:\s+[^>]*)?>(.*?)</title>", re.S | re.I)
ATTR_RE = re.compile(r'([\w:-]+)="([^"]*)"')
TAG_RE = re.compile(r"<[^>]+>")


def norm(value: str) -> str:
    return unicodedata.normalize("NFKC", unescape(value or "")).strip()


def clean(value: str) -> str:
    return norm(TAG_RE.sub("", value or ""))


def idna_url(url: str) -> str:
    p = urlsplit(url)
    if not p.hostname:
        return url
    try:
        host = p.hostname.encode("idna").decode("ascii")
    except Exception:
        return url
    auth = ""
    if p.username:
        auth = p.username
        if p.password:
            auth += ":" + p.password
        auth += "@"
    port = f":{p.port}" if p.port else ""
    return urlunsplit((p.scheme, auth + host + port, p.path, p.query, p.fragment))


def get_bytes(url: str, timeout: float = 25, limit: int = 40_000_000) -> bytes:
    req = urllib.request.Request(
        idna_url(url),
        headers={
            "User-Agent": "Mozilla/5.0 HARU-VOD/2.0",
            "Accept": "application/xml,text/xml,application/vnd.apple.mpegurl,application/x-mpegURL,*/*",
            "Accept-Encoding": "gzip",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(limit + 1)
        if len(data) > limit:
            raise RuntimeError("response too large")
        if (r.headers.get("Content-Encoding") or "").lower() == "gzip" or url.lower().endswith(".gz"):
            try:
                data = gzip.decompress(data)
            except OSError:
                pass
        return data


def get_text(url: str, timeout: float = 25, limit: int = 40_000_000) -> str:
    return get_bytes(url, timeout=timeout, limit=limit).decode("utf-8", "replace")


def discover_epg() -> str | None:
    try:
        text = get_text(DISCOVERY, timeout=15, limit=3_000_000)
        m = re.search(r'url-tvg="([^"]*kai-epg[^"]*)"', "\n".join(text.splitlines()[:8]), re.I)
        if m:
            return unescape(m.group(1).strip())
    except Exception as e:
        print("HARU VOD: EPG discovery failed:", e, file=sys.stderr)
    return None


def fetch_epg() -> tuple[str, str]:
    candidates: list[str] = []
    env = os.environ.get("HARU_EPG_URL", "").strip()
    if env:
        candidates.append(env)
    discovered = discover_epg()
    if discovered:
        candidates.append(discovered)
    candidates += [FALLBACK_EPG, "https://akariko-bck1.sankuria.sbs/epg/kai-epg.xml"]

    seen: set[str] = set()
    errors: list[str] = []
    for url in candidates:
        if not url or url in seen:
            continue
        seen.add(url)
        try:
            print("HARU VOD: trying EPG", url)
            text = get_text(url)
            if "haru.charandom.blog/stream/jp/" not in text:
                raise RuntimeError("HARU replay comments not found")
            print("HARU VOD: EPG OK", url, f"({len(text):,} chars)")
            return text, url
        except Exception as e:
            errors.append(f"{url}: {e}")
            print("HARU VOD: EPG failed", url, repr(e), file=sys.stderr)
    raise RuntimeError("no usable HARU EPG source\n" + "\n".join(errors))


def wall_duration(attrs: dict[str, str]) -> int:
    def parse(raw: str) -> datetime | None:
        m = re.match(r"^(\d{14})", raw or "")
        if not m:
            return None
        try:
            return datetime.strptime(m.group(1), "%Y%m%d%H%M%S")
        except ValueError:
            return None

    a = parse(attrs.get("start", ""))
    b = parse(attrs.get("stop", ""))
    if a and b:
        sec = int((b - a).total_seconds())
        if 300 <= sec <= 8 * 3600:
            return sec
    return 3600


def title_matches(title: str, rule: dict) -> bool:
    t = norm(title)
    includes = [norm(x) for x in rule.get("include", [])]
    excludes = [norm(x) for x in rule.get("exclude", [])]
    return bool(includes) and any(x in t for x in includes) and not any(x in t for x in excludes)


def episode_number(text: str) -> int | None:
    s = norm(text)
    for pat in (r"[#]\s*(\d{1,4})", r"第\s*(\d{1,4})\s*(?:回|話)"):
        m = re.search(pat, s, re.I)
        if m:
            return int(m.group(1))
    return None


def kick_gccx_numbers() -> set[int]:
    nums: set[int] = set()
    for path in (ROOT / "kick_replay.m3u", FREEWIFI):
        if not path.exists():
            continue
        text = norm(path.read_text(encoding="utf-8-sig", errors="replace"))
        for line in text.splitlines():
            if "ゲームセンターCX" not in line:
                continue
            for a, b in re.findall(r"#\s*(\d{1,4})\s*[-~〜～]\s*(\d{1,4})", line):
                lo, hi = sorted((int(a), int(b)))
                if hi - lo <= 100:
                    nums.update(range(lo, hi + 1))
            for n in re.findall(r"#\s*(\d{1,4})", line):
                nums.add(int(n))
            for n in re.findall(r"第\s*(\d{1,4})\s*(?:回|話)", line):
                nums.add(int(n))
    return nums


def parse_epg(text: str, rules: list[dict], max_age_days: int) -> list[dict]:
    now = int(datetime.now(timezone.utc).timestamp())
    oldest = now - max_age_days * 86400
    found: list[dict] = []

    for m in PAIR_RE.finditer(text):
        replay_url = unescape(m.group(1))
        attrs = dict(ATTR_RE.findall(m.group(2)))
        tm = TITLE_RE.search(m.group(3))
        sm = re.search(r"[?&]start=(\d+)", replay_url)
        if not tm or not sm:
            continue

        title = clean(tm.group(1))
        start = int(sm.group(1))
        duration = wall_duration(attrs)
        end = start + duration
        if end > now + 60 or end < oldest:
            continue

        for rule in rules:
            if title_matches(title, rule):
                found.append(
                    {
                        "rule": rule,
                        "title": title,
                        "url": replay_url,
                        "start": start,
                        "end": end,
                        "channel": attrs.get("channel", ""),
                    }
                )
                break

    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for item in sorted(found, key=lambda x: x["start"], reverse=True):
        key = (item["rule"]["id"], item["url"])
        if key not in seen:
            seen.add(key)
            out.append(item)
    return out


def prelimit(items: list[dict], max_per_program: int) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for item in items:
        grouped.setdefault(item["rule"]["id"], []).append(item)
    out: list[dict] = []
    cap = max(max_per_program * 3, max_per_program)
    for arr in grouped.values():
        out.extend(sorted(arr, key=lambda x: x["start"], reverse=True)[:cap])
    return sorted(out, key=lambda x: x["start"], reverse=True)


def probe(url: str, timeout: float) -> tuple[bool, str]:
    for use_range in (True, False):
        headers = {
            "User-Agent": "Mozilla/5.0 HARU-VOD/2.0",
            "Accept": "application/vnd.apple.mpegurl,application/x-mpegURL,*/*",
        }
        if use_range:
            headers["Range"] = "bytes=0-8191"
        req = urllib.request.Request(idna_url(url), headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                data = r.read(8192)
                if getattr(r, "status", 200) < 400 and b"#EXTM3U" in data:
                    return True, f"ok:{getattr(r, 'status', 200)}"
                return False, f"bad:{getattr(r, 'status', 0)}"
        except Exception as e:
            if not use_range:
                return False, f"{type(e).__name__}:{e}"
    return False, "unknown"


def probe_items(items: list[dict], timeout: float) -> tuple[list[dict], dict[str, int]]:
    if not items:
        return [], {}
    ok: list[dict] = []
    stats: dict[str, int] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(probe, item["url"], timeout): item for item in items}
        for future in concurrent.futures.as_completed(futures):
            item = futures[future]
            passed, status = future.result()
            key = status.split(":", 1)[0]
            stats[key] = stats.get(key, 0) + 1
            if passed:
                item["probe"] = status
                ok.append(item)
    return sorted(ok, key=lambda x: x["start"], reverse=True), stats


def suppress_kick_duplicates(items: list[dict]) -> list[dict]:
    kick_nums = kick_gccx_numbers()
    out: list[dict] = []
    for item in items:
        rule = item["rule"]
        if rule.get("prefer_kick"):
            ep = episode_number(item["title"])
            if ep is not None and ep in kick_nums:
                print("HARU VOD: KICK duplicate suppressed", ep, item["title"])
                continue
        out.append(item)
    return out


def limit_items(items: list[dict], rules: list[dict], max_per_program: int) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for item in items:
        grouped.setdefault(item["rule"]["id"], []).append(item)
    out: list[dict] = []
    for rule in rules:
        arr = sorted(grouped.get(rule["id"], []), key=lambda x: x["start"], reverse=True)
        out.extend(arr[:max_per_program])
    return out


def esc(value: str) -> str:
    return (value or "").replace('"', "'").replace("\r", " ").replace("\n", " ")


def build_m3u(items: list[dict], group: str, source: str) -> str:
    now = datetime.now(JST).isoformat(timespec="seconds")
    lines = ["#EXTM3U", f"# HARU VOD generated {now} source={source}"]
    for item in items:
        rule = item["rule"]
        dt = datetime.fromtimestamp(item["start"], timezone.utc).astimezone(JST)
        ep = episode_number(item["title"])
        short = f" #{ep}" if ep is not None else ""
        label = f"{rule['name']}{short} {dt:%m/%d %H:%M}｜{item['title']}"
        logo = RAW + rule["logo"]
        tvgid = f"haru.vod.{rule['id']}.{item['start']}"
        lines.append(
            f'#EXTINF:-1 tvg-id="{esc(tvgid)}" tvg-name="{esc(rule["name"])}" '
            f'tvg-logo="{esc(logo)}" group-title="{esc(group)}",{esc(label)}'
        )
        lines.append(item["url"])
    return "\n".join(lines) + "\n"


def merge_freewifi(vod: str) -> None:
    if not FREEWIFI.exists():
        return
    text = FREEWIFI.read_text(encoding="utf-8-sig", errors="replace")
    body = "\n".join(vod.splitlines()[2:]).strip()
    block = f"{START_MARKER}\n{body}\n{END_MARKER}"
    if START_MARKER in text and END_MARKER in text:
        text = re.sub(
            re.escape(START_MARKER) + r".*?" + re.escape(END_MARKER),
            block,
            text,
            flags=re.S,
        )
    else:
        text = text.rstrip() + "\n\n" + block + "\n"
    FREEWIFI.write_text(text, encoding="utf-8")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(DEFAULT_CONFIG))
    ap.add_argument("--check", action="store_true", help="probe replay URLs and publish only playable items")
    ap.add_argument("--probe-timeout", type=float, default=4.0)
    ap.add_argument("--max-age-days", type=int, default=14)
    ap.add_argument("--max-per-program", type=int, default=12)
    ap.add_argument("--check-limit", type=int, default=0, help="backward-compatible optional total probe cap")
    ap.add_argument("--merge-freewifi", action="store_true", help="explicitly merge into freewifi; off by default")
    args = ap.parse_args()

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    rules = cfg["programmes"]
    epg, source = fetch_epg()
    candidates = parse_epg(epg, rules, args.max_age_days)
    candidates = suppress_kick_duplicates(candidates)
    candidates = prelimit(candidates, args.max_per_program)
    if args.check_limit > 0:
        candidates = candidates[: args.check_limit]

    print("HARU VOD: matched ended candidates", len(candidates))
    if not candidates:
        raise SystemExit("HARU VOD: no favourite programmes found; preserving previous shelf")

    if args.check:
        playable, stats = probe_items(candidates, args.probe_timeout)
        print("HARU VOD: probe stats", stats, "playable", len(playable))
        if not playable:
            raise SystemExit("HARU VOD: all replay probes failed; preserving previous shelf")
    else:
        playable = candidates

    playable = limit_items(playable, rules, args.max_per_program)
    vod = build_m3u(playable, cfg.get("group_title", "HARU VOD"), source)
    OUT.write_text(vod, encoding="utf-8")
    if args.merge_freewifi:
        merge_freewifi(vod)

    counts = {r["name"]: 0 for r in rules}
    for item in playable:
        counts[item["rule"]["name"]] += 1
    print("HARU VOD:", len(playable), "entries", counts)


if __name__ == "__main__":
    main()
