#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import threading
import time
import urllib.request
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from urllib.parse import quote, urlsplit
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config.json"
GENERAL_OUT = ROOT / "output" / "general.m3u"
KANA_OUT = ROOT / "output" / "kana.m3u"
MANDARIN_OUT = ROOT / "output" / "mandarin.m3u"
KANA_STATE = ROOT / "state" / "kana.json"
MANDARIN_STATE = ROOT / "state" / "mandarin.json"
FREEWIFI = Path("freewifi")
EPG_PATH = Path("public_sports_epg_local.xml")
COOKIES = Path("youtube_cookies.txt")

GENERAL_START = "# === GENERAL_YOUTUBE_MANAGED_START ==="
GENERAL_END = "# === GENERAL_YOUTUBE_MANAGED_END ==="
KANA_START = "# === KANA_TUBE_MANAGED_START ==="
KANA_END = "# === KANA_TUBE_MANAGED_END ==="
TODAY_START = "# === TODAY_PUBLIC_SPORTS_START ==="
TODAY_END = "# === TODAY_PUBLIC_SPORTS_END ==="
TODAY_HEADING = "## 今日の開催場"

JST = ZoneInfo("Asia/Tokyo")
CACHE_VERSION = "ytv3-20260922b"
GENERAL_PLAYBACK_PROXY = "https://iptv-9x-browser-proxy.onrender.com/yt-hls?id="
GENERAL_SEARCH_PROXY = "https://iptv-9x-browser-proxy.onrender.com/yt-live?q="
DEFAULT_YOUTUBE_LOGO = "https://www.gstatic.com/youtube/img/branding/favicon/favicon_144x144.png"
TRANSIENT = {"RATE_LIMIT", "BOT_CHECK", "COOKIE_ERROR", "TIMEOUT", "OTHER", "EXCEPTION"}
MAX_WORKERS = 4
MIN_CALL_INTERVAL = 1.20
_lock = threading.Lock()
_last_call = 0.0


def load_config():
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    general = data.get("general") or []
    ids = [x.get("id") for x in general]
    if data.get("version") != 2:
        raise SystemExit("youtube/config.json version must be 2")
    if not general or len(ids) != len(set(ids)):
        raise SystemExit("youtube/config.json general channel ids are invalid")
    return data


def read_json(path, default=None):
    if default is None:
        default = {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def base_cmd():
    cmd = ["yt-dlp", "--js-runtimes", "node", "--no-warnings", "--no-cache-dir"]
    if COOKIES.exists() and COOKIES.stat().st_size > 20:
        cmd += ["--cookies", str(COOKIES)]
    return cmd


def run_ytdlp(args, timeout=40):
    global _last_call
    with _lock:
        wait = MIN_CALL_INTERVAL - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()
    return subprocess.run(
        base_cmd() + ["--socket-timeout", "10", "--retries", "1", "--fragment-retries", "1"] + list(args),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def classify(stderr):
    s = (stderr or "").lower()
    if "429" in s or "too many requests" in s or "rate limit" in s:
        return "RATE_LIMIT"
    if "sign in to confirm" in s or "not a bot" in s:
        return "BOT_CHECK"
    if "cookies" in s and ("expired" in s or "invalid" in s or "login" in s):
        return "COOKIE_ERROR"
    if "this live event will begin" in s or "premieres in" in s:
        return "NOT_STARTED"
    if "not currently live" in s or "is not live" in s:
        return "NOT_LIVE"
    if "private video" in s:
        return "PRIVATE"
    if "unavailable" in s:
        return "UNAVAILABLE"
    return "OTHER"


def direct_hls(page):
    try:
        p = run_ytdlp([
            "--no-playlist", "--match-filter", "is_live",
            "-f", "best[protocol^=m3u8]/best[protocol*=m3u8]/best", "-g", page,
        ], 35)
    except subprocess.TimeoutExpired:
        return None, "TIMEOUT"
    urls = [x.strip() for x in p.stdout.splitlines() if x.strip().startswith(("http://", "https://"))]
    if p.returncode == 0 and len(urls) == 1:
        return urls[0], "OK"
    return None, classify(p.stderr)


def flat_listing(url, limit=40):
    try:
        p = run_ytdlp(["--flat-playlist", "--dump-json", "--playlist-end", str(limit), url], 45)
    except subprocess.TimeoutExpired:
        return [], "TIMEOUT"
    items = []
    for line in p.stdout.splitlines():
        try:
            items.append(json.loads(line))
        except Exception:
            pass
    if p.returncode != 0 and not items:
        return [], classify(p.stderr)
    return items, ("PARTIAL" if p.returncode else "OK")


def inspect_watch(video_id):
    try:
        p = run_ytdlp([
            "--dump-single-json", "--no-playlist", "--ignore-no-formats-error",
            "https://www.youtube.com/watch?v=" + video_id,
        ], 40)
    except subprocess.TimeoutExpired:
        return None, "TIMEOUT"
    try:
        info = json.loads(p.stdout) if p.stdout.strip() else None
    except Exception:
        info = None
    if info:
        return info, "OK"
    return None, classify(p.stderr)


def channel_live(page, query=None, guard_terms=None):
    base = re.sub(r"/(?:live|streams|videos)/?$", "", page.rstrip("/"))
    reasons = []
    for listing in (base + "/streams", base + "/videos"):
        items, code = flat_listing(listing, 30)
        if code not in ("OK", "PARTIAL"):
            reasons.append(code)
            continue
        for item in items:
            if (item.get("live_status") or "").lower() != "is_live" or not item.get("id"):
                continue
            # A channel may run several simultaneous live cameras.  Never use
            # the first arbitrary /live result when we have location guards.
            if guard_terms and not _candidate_matches(item, query or "", guard_terms):
                print(
                    f'GENERAL reject channel mismatch: {item.get("id")} '
                    f'title={item.get("title")!r}'
                )
                continue
            url, result = direct_hls("https://www.youtube.com/watch?v=" + item["id"])
            if url:
                return url, "OK"
            reasons.append(result)
    if any(x in TRANSIENT for x in reasons):
        return None, next(x for x in reasons if x in TRANSIENT)
    return None, "NOT_LIVE"


def _candidate_matches(item, query, guard_terms=None):
    title = (item.get("title") or "").lower()
    channel = " ".join(str(item.get(k) or "") for k in ("channel", "uploader")).lower()
    hay = title + " " + channel

    # Explicit guard terms are strongest. At least one must match.
    terms = [str(x).strip().lower() for x in (guard_terms or []) if str(x).strip()]
    if terms:
        return any(t in hay for t in terms)

    # Generic safety net for search-based channels: require at least one
    # meaningful token from the query to appear in the candidate metadata.
    stop = {"live", "youtube", "camera", "stream", "ライブ", "ライブカメラ", "配信", "公式"}
    tokens = [t.lower() for t in re.split(r"\s+", query) if len(t) >= 2 and t.lower() not in stop]
    return any(t in hay for t in tokens[:4]) if tokens else False


def search_live(query, guard_terms=None):
    items, code = flat_listing("ytsearch8:" + query, 8)
    if code not in ("OK", "PARTIAL"):
        return None, code
    for item in items:
        if (item.get("live_status") or "").lower() != "is_live" or not item.get("id"):
            continue
        if not _candidate_matches(item, query, guard_terms):
            print(f'GENERAL reject mismatch: {item.get("id")} title={item.get("title")!r}')
            continue
        url, result = direct_hls("https://www.youtube.com/watch?v=" + item["id"])
        if url:
            return url, "OK"
        if result in TRANSIENT:
            return None, result
    return None, "NOT_LIVE"


def parse_m3u(path):
    result = {}
    if not path.exists():
        return result
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    for i, line in enumerate(lines):
        if not line.startswith("#EXTINF:"):
            continue
        m = re.search(r'tvg-id="([^"]+)"', line)
        if not m:
            continue
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j < len(lines) and lines[j].strip().startswith(("http://", "https://")):
            result[m.group(1)] = {"ext": line, "url": lines[j].strip()}
    return result


def logo_url(url):
    # Newly added channels may intentionally omit a dedicated logo while the
    # artwork is being prepared. Use the official YouTube icon temporarily
    # instead of crashing the whole playlist build.
    url = url or DEFAULT_YOUTUBE_LOGO
    return url + ("&" if "?" in url else "?") + "v=" + CACHE_VERSION


def entry(item, url, label=None):
    name = item["name"]
    shown = label or name
    return "\n".join([
        f'#EXTINF:-1 tvg-id="{item["id"]}" tvg-name="{name}" tvg-logo="{logo_url(item.get("logo"))}" group-title="{item["group"]}",{shown}',
        url,
    ])


def write_playlist(path, blocks):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "#EXTM3U\n\n" + "\n\n".join(x.strip() for x in blocks if x and x.strip())
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def playlist_body(path):
    if not path.exists():
        return ""
    lines = path.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    if lines and lines[0].startswith("#EXTM3U"):
        lines = lines[1:]
    return "\n".join(lines).strip()


def resolve_general_one(index, item, previous):
    page = (item.get("page") or "").strip()
    try:
        if page:
            is_watch = "watch?v=" in page or "youtu.be/" in page
            guards = item.get("guard_terms") or []
            if not is_watch and guards:
                # Multi-live channels must be resolved by matching the intended
                # location/title inside the channel, not by arbitrary /live.
                url, code = channel_live(
                    page,
                    item.get("query") or item["name"],
                    guards,
                )
            else:
                url, code = direct_hls(page)
                if not url and code not in TRANSIENT and not is_watch:
                    url, code = channel_live(
                        page,
                        item.get("query") or item["name"],
                        guards,
                    )
        else:
            url, code = search_live(
                item.get("query") or item["name"],
                item.get("guard_terms") or [],
            )
    except Exception:
        url, code = None, "EXCEPTION"

    old = previous.get(item["id"], {}).get("url")
    if not url and code in TRANSIENT and old and previous_safe_for_item(item, old):
        url = old
        print(f'GENERAL keep safe previous: {item["id"]} [{code}]')
    elif not url and old and code in TRANSIENT:
        print(f'GENERAL discard unsafe previous: {item["id"]} [{code}]')
    elif not url and item.get("persistent") and page:
        url = page
        print(f'GENERAL keep persistent page: {item["id"]}')
    return index, item, url, code


def video_key(url):
    if not url:
        return ""
    for pattern in (r"/id/([A-Za-z0-9_-]{11})(?:\.|/|$)", r"[?&]v=([A-Za-z0-9_-]{11})(?:&|$)", r"youtu\.be/([A-Za-z0-9_-]{11})"):
        m = re.search(pattern, url)
        if m:
            return "video:" + m.group(1)
    return url.split("?", 1)[0]


def stable_general_playback(url):
    key = video_key(url)
    if key.startswith("video:"):
        return GENERAL_PLAYBACK_PROXY + key.split(":", 1)[1]
    return url


def general_target(item):
    page = (item.get("page") or "").strip()
    key = video_key(page)
    if key.startswith("video:"):
        return GENERAL_PLAYBACK_PROXY + key.split(":", 1)[1]
    query = (item.get("query") or item["name"]).strip()
    return GENERAL_SEARCH_PROXY + quote(query, safe="")


def previous_safe_for_item(item, old_url):
    """Only retain a previous URL when it is provably the same target.

    A stale, wrongly-resolved YouTube URL is worse than a temporarily missing
    channel. Fixed watch URLs must keep the same video id. Search/channel
    targets are not retained unless explicitly opted in with retain_previous.
    """
    if not old_url:
        return False
    page = (item.get("page") or "").strip()
    page_key = video_key(page)
    old_key = video_key(old_url)
    if page_key.startswith("video:"):
        return old_key == page_key
    return bool(item.get("retain_previous"))


def update_general(config):
    # Resolve playable HLS in GitHub Actions. Do not make every channel depend
    # on the Render resolver at playback time: a resolver outage would blank
    # the entire YouTube group at once.
    previous = parse_m3u(GENERAL_OUT)
    resolved = [None] * len(config["general"])

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [
            pool.submit(resolve_general_one, i, item, previous)
            for i, item in enumerate(config["general"])
        ]
        for future in as_completed(futures):
            i, item, url, code = future.result()

            # Never preserve the broken Render resolver as a fallback.
            if url and "iptv-9x-browser-proxy.onrender.com/yt-" in url:
                url = None

            if not url:
                old = previous.get(item["id"], {}).get("url")
                if (
                    code in TRANSIENT
                    and old
                    and "iptv-9x-browser-proxy.onrender.com/yt-" not in old
                    and previous_safe_for_item(item, old)
                ):
                    url = old
                    print(f'GENERAL keep safe previous: {item["id"]} [{code}]')

            if url:
                resolved[i] = entry(item, url)
                print(f'GENERAL resolved: {item["id"]} [{code}]')
            else:
                print(f'GENERAL unavailable: {item["id"]} [{code}]')

    blocks = []
    seen_video_keys = {}
    for i, block in enumerate(resolved):
        if not block:
            continue
        url = block.rsplit("\n", 1)[-1].strip()
        key = video_key(url)
        if key.startswith("video:") and key in seen_video_keys:
            print(
                f'GENERAL drop duplicate video: {config["general"][i]["id"]} '
                f'== {seen_video_keys[key]} [{key}]'
            )
            continue
        if key.startswith("video:"):
            seen_video_keys[key] = config["general"][i]["id"]
        blocks.append(block)

    if not blocks:
        raise SystemExit("refusing to publish empty general YouTube output")
    write_playlist(GENERAL_OUT, blocks)
    print(f"GENERAL output: {len(blocks)}/{len(config['general'])}")


def official_youtube(info, channel_id, handle=None):
    cid = (info.get("channel_id") or "").strip()
    if cid:
        return cid == channel_id
    if handle:
        for key in ("channel_url", "uploader_url"):
            parsed = urlsplit(info.get(key) or "")
            if parsed.hostname in ("www.youtube.com", "youtube.com") and parsed.path.rstrip("/").lower() == "/" + handle.lower():
                return True
    return False


def info_start(info, previous=None):
    for key in ("release_timestamp",):
        try:
            value = int(info.get(key) or 0)
        except Exception:
            value = 0
        if value > 0:
            return value
    if previous and previous.get("video_id") == info.get("id"):
        try:
            value = int(previous.get("start_timestamp") or 0)
        except Exception:
            value = 0
        if value > 0:
            return value
    return None


def info_hls(info):
    manifest = (info.get("manifest_url") or "").strip()
    if manifest.startswith(("http://", "https://")):
        return manifest
    choices = []
    for fmt in info.get("formats") or []:
        url = (fmt.get("url") or "").strip()
        protocol = (fmt.get("protocol") or "").lower()
        if not url.startswith(("http://", "https://")) or "m3u8" not in protocol:
            continue
        both = int((fmt.get("vcodec") or "none") != "none" and (fmt.get("acodec") or "none") != "none")
        choices.append(((both, int(fmt.get("height") or 0), float(fmt.get("tbr") or 0)), url))
    if choices:
        choices.sort(key=lambda x: x[0], reverse=True)
        return choices[0][1]
    return None


def update_kana(config):
    item = config["special"]["kana"]
    previous = read_json(KANA_STATE, {})
    channel = item["channel"].rstrip("/")
    trouble = False
    confirmed = False

    def publish_selected(selected):
        status = (selected.get("live_status") or "").lower()
        vid = selected["id"]
        watch = "https://www.youtube.com/watch?v=" + vid
        start = info_start(selected, previous)
        play = info_hls(selected)
        if status == "is_live" and not play:
            play, _ = direct_hls(watch)
        url = play if status == "is_live" and play else watch
        if status == "is_live":
            label = item["name"] + "【LIVE】"
        else:
            when = datetime.fromtimestamp(start, JST).strftime("%m/%d %H:%M") if start else ""
            label = item["name"] + (f"【配信予定 {when}】" if when else "【配信予定】")
        write_playlist(KANA_OUT, [entry(item, url, label)])
        write_json(KANA_STATE, {
            "state": status,
            "channel": item.get("handle"),
            "channel_id": item["channel_id"],
            "video_id": vid,
            "watch_url": watch,
            "play_url": play,
            "direct_hls": bool(play),
            "title": selected.get("title") or item["name"],
            "start_timestamp": start,
            "start_jst": datetime.fromtimestamp(start, JST).isoformat(timespec="seconds") if start else None,
            "check_error": False,
            "checked_at": datetime.now(JST).isoformat(timespec="seconds"),
        })
        print(f"KANA {status}: {vid}")

    # Fast path: the most common transition is the already-known reservation
    # changing from upcoming -> live. Check that exact video first instead of
    # crawling the whole channel before looking at it.
    previous_id = previous.get("video_id")
    previous_info = None
    if previous_id:
        info, code = inspect_watch(previous_id)
        if info and official_youtube(info, item["channel_id"], item.get("handle")):
            status = (info.get("live_status") or "").lower()
            if status == "is_live":
                publish_selected(info)
                print("KANA fast-path: previous reservation is now live")
                return
            if status == "is_upcoming":
                previous_info = info
        elif code in TRANSIENT:
            trouble = True

    # Primary discovery is the official streams tab only. Keep the list small:
    # we only need current live/upcoming slots, not dozens of old broadcasts.
    candidates = [previous_id] if previous_id else []
    rows, code = flat_listing(channel + "/streams", 24)
    if code == "OK":
        confirmed = True
    elif code not in ("OK", "PARTIAL"):
        trouble = True

    ordered = sorted(
        [x for x in rows if x.get("id")],
        key=lambda x: 0 if (x.get("live_status") or "").lower() == "is_live"
        else 1 if (x.get("live_status") or "").lower() == "is_upcoming"
        else 2,
    )
    candidates += [x["id"] for x in ordered[:12]]

    chosen = []
    seen = set()
    for vid in candidates:
        if not vid or vid in seen:
            continue
        seen.add(vid)
        if previous_info is not None and vid == previous_id:
            info, code = previous_info, "OK"
        else:
            info, code = inspect_watch(vid)
        if not info:
            if code in TRANSIENT:
                trouble = True
            continue
        if not official_youtube(info, item["channel_id"], item.get("handle")):
            continue
        status = (info.get("live_status") or "").lower()
        if status == "is_live":
            publish_selected(info)
            return
        if status == "is_upcoming":
            chosen.append(info)

    # Search/live-page fallback is only needed when the official streams tab did
    # not produce a usable live/upcoming slot.
    if not chosen:
        fallback_ids = []
        for url, limit in ((channel + "/live", 8), (channel + "/videos", 12)):
            rows, code = flat_listing(url, limit)
            if code not in ("OK", "PARTIAL"):
                trouble = True
            fallback_ids += [x["id"] for x in rows if x.get("id")]
        for query in item.get("search") or []:
            rows, code = flat_listing("ytsearchdate6:" + query, 6)
            if code not in ("OK", "PARTIAL"):
                trouble = True
            fallback_ids += [x["id"] for x in rows if x.get("id")]

        for vid in fallback_ids:
            if not vid or vid in seen:
                continue
            seen.add(vid)
            info, code = inspect_watch(vid)
            if not info:
                if code in TRANSIENT:
                    trouble = True
                continue
            if not official_youtube(info, item["channel_id"], item.get("handle")):
                continue
            status = (info.get("live_status") or "").lower()
            if status == "is_live":
                publish_selected(info)
                return
            if status == "is_upcoming":
                chosen.append(info)

    if chosen:
        now = int(datetime.now(timezone.utc).timestamp())
        chosen.sort(key=lambda x: info_start(x, previous) or now + 10**9)
        publish_selected(chosen[0])
        return

    if trouble or not confirmed:
        state = dict(previous)
        state["check_error"] = True
        state["checked_at"] = datetime.now(JST).isoformat(timespec="seconds")
        write_json(KANA_STATE, state)
        print("KANA check inconclusive; previous output preserved")
        return

    write_playlist(KANA_OUT, [])
    write_json(KANA_STATE, {
        "state": "offline",
        "channel": item.get("handle"),
        "channel_id": item["channel_id"],
        "check_error": False,
        "checked_at": datetime.now(JST).isoformat(timespec="seconds"),
    })
    print("KANA offline")

def update_mandarin(config):
    item = config["special"]["mandarin"]
    previous = parse_m3u(MANDARIN_OUT).get(item["id"], {}).get("url")
    channel = item["channel"].rstrip("/")
    url, code = direct_hls(channel + "/live")
    if not url and code not in TRANSIENT:
        url, code = channel_live(channel)
    if not url and code in TRANSIENT and previous:
        url = previous
        state = "unknown-preserved"
    elif url:
        state = "live"
    else:
        state = "offline"

    write_playlist(MANDARIN_OUT, [entry(item, url)] if url else [])
    write_json(MANDARIN_STATE, {
        "state": state,
        "url": url,
        "checked_at": datetime.now(JST).isoformat(timespec="seconds"),
    })
    print(f"MANDARIN {state}")


def strip_entry(text, tvg_id):
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#EXTINF:") and f'tvg-id="{tvg_id}"' in line:
            i += 1
            while i < len(lines) and not lines[i].startswith("#EXTINF:"):
                if lines[i].strip().startswith(("http://", "https://")):
                    i += 1
                    break
                i += 1
            continue
        out.append(line)
        i += 1
    return "\n".join(out).rstrip() + "\n"


def sync_freewifi(config):
    if not FREEWIFI.exists():
        raise SystemExit("freewifi missing")
    text = FREEWIFI.read_text(encoding="utf-8-sig", errors="replace")

    general_parts = [playlist_body(GENERAL_OUT), playlist_body(MANDARIN_OUT)]
    body = "\n\n".join(x for x in general_parts if x).strip()
    block = GENERAL_START + "\n" + body + "\n" + GENERAL_END
    pat = re.compile(re.escape(GENERAL_START) + r".*?" + re.escape(GENERAL_END), re.S)
    if not pat.search(text):
        raise SystemExit("GENERAL_YOUTUBE managed block missing from freewifi")
    text = pat.sub(lambda _m: block, text, count=1)

    kana_id = config["special"]["kana"]["id"]
    text = re.sub(re.escape(KANA_START) + r".*?" + re.escape(KANA_END) + r"\n?", "", text, flags=re.S)
    text = strip_entry(text, kana_id)
    kana_body = playlist_body(KANA_OUT)
    if kana_body:
        kana_block = KANA_START + "\n" + kana_body + "\n" + KANA_END + "\n"
        start = text.find(TODAY_START)
        end = text.find(TODAY_END, start + len(TODAY_START)) if start >= 0 else -1
        heading = text.find(TODAY_HEADING, start, end) if start >= 0 and end >= 0 else -1
        if heading >= 0:
            pos = text.find("\n", heading)
            pos = len(text) if pos < 0 else pos + 1
            text = text[:pos] + kana_block + text[pos:]
        else:
            pos = text.find(GENERAL_START)
            if pos < 0:
                raise SystemExit("no safe Kana insertion anchor")
            text = text[:pos].rstrip() + "\n\n" + kana_block + "\n" + text[pos:]

    FREEWIFI.write_text(text.rstrip() + "\n", encoding="utf-8")


def fetch_text(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read().decode("utf-8", "replace")


def mandarin_game(item):
    html = fetch_text(item["schedule_url"])
    html = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    text = re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html)))
    now = datetime.now(JST)
    pos = text.find(now.strftime("%Y.%m.%d"))
    if pos < 0:
        return None
    segment = text[pos:pos + 700]
    tm = re.search(r"\b([0-2]\d:[0-5]\d)\b", segment)
    if not tm:
        return None
    opponents = (
        "福岡ソフトバンクホークス（三軍）", "福岡ソフトバンクホークス(三軍)",
        "徳島インディゴソックス", "高知ファイティングドッグス", "香川オリーブガイナーズ",
    )
    opponent = next((x for x in opponents if x in segment), None)
    if not opponent:
        return None
    hour, minute = map(int, tm.group(1).split(":"))
    start = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    stop = start + timedelta(hours=4)
    after = segment[tm.end():]
    op = after.find(opponent)
    venue = re.sub(r"\s+", " ", after[:op]).strip(" -|・") if op >= 0 else ""
    return start, stop, venue[:80] or "愛媛県内球場", opponent


def update_mandarin_epg(config):
    item = config["special"]["mandarin"]
    live = item["id"] in parse_m3u(MANDARIN_OUT)
    try:
        game = mandarin_game(item) if live else None
    except Exception as e:
        print(f"MANDARIN EPG fetch failed; preserving current programme: {e}")
        return

    if EPG_PATH.exists() and EPG_PATH.stat().st_size:
        tree = ET.parse(EPG_PATH)
        root = tree.getroot()
    else:
        root = ET.Element("tv", {"generator-info-name": "ajiousama/himitsu local public sports EPG"})
        tree = ET.ElementTree(root)

    if not any(x.get("id") == item["id"] for x in root.findall("channel")):
        ch = ET.Element("channel", {"id": item["id"]})
        ET.SubElement(ch, "display-name").text = item["name"]
        first_prog = next((i for i, x in enumerate(list(root)) if x.tag == "programme"), len(root))
        root.insert(first_prog, ch)

    for prog in list(root.findall("programme")):
        if prog.get("channel") == item["id"]:
            root.remove(prog)

    if game:
        start, stop, venue, opponent = game
        fmt = lambda d: d.strftime("%Y%m%d%H%M%S %z")
        prog = ET.SubElement(root, "programme", {"start": fmt(start), "stop": fmt(stop), "channel": item["id"]})
        ET.SubElement(prog, "title", {"lang": "ja"}).text = f"愛媛MP vs {opponent}"
        ET.SubElement(prog, "desc", {"lang": "ja"}).text = f"{venue} / 愛媛マンダリンパイレーツ公式YouTube LIVE"
        ET.SubElement(prog, "category", {"lang": "ja"}).text = "野球"

    ET.indent(tree, space="  ")
    tree.write(EPG_PATH, encoding="utf-8", xml_declaration=True)


def validate(config):
    if not config["general"]:
        raise SystemExit("general YouTube channel list is empty")
    for item in config["general"]:
        rel = item["logo"].replace("https://raw.githubusercontent.com/ajiousama/himitsu/main/", "")
        if not Path(rel).exists():
            raise SystemExit(f"missing logo: {item['id']} -> {rel}")
    for key in ("kana", "mandarin"):
        item = config["special"][key]
        rel = item["logo"].replace("https://raw.githubusercontent.com/ajiousama/himitsu/main/", "")
        if not Path(rel).exists():
            raise SystemExit(f"missing special logo: {rel}")

    text = FREEWIFI.read_text(encoding="utf-8-sig", errors="replace")
    if "/logos/youtube/" in text or "/logos/youtube_live/" in text or "/logos/youtube_special/" in text:
        bad = [x for x in text.splitlines() if 'tvg-id="youtube.' in x and ("/logos/youtube/" in x or "/logos/youtube_live/" in x or "/logos/youtube_special/" in x)]
        if bad:
            raise SystemExit("legacy YouTube logo path remains in freewifi: " + bad[0])
    if text.count(GENERAL_START) != 1 or text.count(GENERAL_END) != 1:
        raise SystemExit("general YouTube managed block count invalid")
    kana_id = config["special"]["kana"]["id"]
    kana_count = text.count(f'tvg-id="{kana_id}"')
    if kana_count > 1:
        raise SystemExit("duplicate Kana entry in freewifi")

    # Reservation/LIVE publication is an invariant, not best-effort. Once the
    # official channel has been resolved, FreeWiFi must contain the exact same
    # Kana slot immediately.
    kana_state = read_json(KANA_STATE, {})
    kana_entry = parse_m3u(FREEWIFI).get(kana_id)
    kana_mode = (kana_state.get("state") or "").lower()
    if kana_mode in ("is_upcoming", "is_live"):
        if not kana_entry:
            raise SystemExit(f"Kana {kana_mode} detected but missing from freewifi")
        expected = (
            kana_state.get("play_url")
            if kana_mode == "is_live" and kana_state.get("play_url")
            else kana_state.get("watch_url")
        )
        if expected and kana_entry.get("url") != expected:
            raise SystemExit(
                f"Kana {kana_mode} URL mismatch: freewifi={kana_entry.get('url')} state={expected}"
            )
        ext = kana_entry.get("ext") or ""
        if kana_mode == "is_upcoming" and "配信予定" not in ext:
            raise SystemExit("Kana reservation detected but freewifi is not labelled 配信予定")
        if kana_mode == "is_live" and "【LIVE】" not in ext:
            raise SystemExit("Kana live detected but freewifi is not labelled LIVE")
    elif kana_mode == "offline" and kana_entry:
        raise SystemExit("Kana is offline but stale entry remains in freewifi")

    print("YouTube v2 validation OK")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=("general", "special", "all"), default="all")
    parser.add_argument("--sync-only", action="store_true")
    parser.add_argument("--epg-only", action="store_true")
    args = parser.parse_args()
    config = load_config()

    if args.epg_only:
        update_mandarin_epg(config)
        return
    if args.sync_only:
        sync_freewifi(config)
        validate(config)
        return

    if args.scope in ("general", "all"):
        update_general(config)
    if args.scope in ("special", "all"):
        update_kana(config)
        update_mandarin(config)
        update_mandarin_epg(config)
    sync_freewifi(config)
    validate(config)


if __name__ == "__main__":
    main()
