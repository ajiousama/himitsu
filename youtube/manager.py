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
KANA_IPTV_OUT = ROOT / "output" / "kana_iptv.m3u"
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
KANA_IPTV_ID = "youtube.kana_tube_iptv"
KANA_9X_PROXY = "https://kana-iptv-fresh-production.up.railway.app/kana-9x.m3u8"
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
    """Try the original muxed live format first, then alternate YouTube clients.

    Never return a YouTube watch page or progressive video as IPTV HLS.
    """
    attempts = [
        [],
        ["--extractor-args", "youtube:player_client=android,web"],
        ["--extractor-args", "youtube:player_client=web_safari,web"],
    ]
    reasons = []
    for extra in attempts:
        try:
            p = run_ytdlp([
                "--no-playlist", "--match-filter", "is_live",
                *extra, "-f",
                "best[protocol^=m3u8]/best[protocol*=m3u8]",
                "-g", page,
            ], 40)
        except subprocess.TimeoutExpired:
            reasons.append("TIMEOUT")
            continue
        urls = [x.strip() for x in p.stdout.splitlines()
                if x.strip().startswith(("http://", "https://"))]
        hls = [u for u in urls if ".m3u8" in u or "manifest.googlevideo.com/" in u]
        if p.returncode == 0 and len(urls) == 1 and len(hls) == 1:
            return hls[0], "OK"
        reason = classify(p.stderr)
        reasons.append(reason)
        safe_lines = [line.strip() for line in (p.stderr or "").splitlines()
                      if any(term in line.lower() for term in
                             ("sign in", "bot", "403", "429", "po token", "nsig",
                              "signature", "format", "unavailable", "javascript",
                              "challenge", "error:"))]
        for line in safe_lines[-3:]:
            line = re.sub(r"https?://\\S+", "[URL_REDACTED]", line)
            print(f"KANA yt-dlp diagnostic: {line[:260]}")
        print(f"KANA HLS attempt client={extra[-1] if extra else 'default'} "
              f"exit={p.returncode} urls={len(urls)} reason={reason}")
    return None, (reasons[-1] if reasons else "OTHER")


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
        if video_id == "fZmyTwX05wY" or video_id == "KYieCkdLG60":
            formats = info.get("formats") or []
            hls = [f for f in formats if "m3u8" in str(f.get("protocol") or "")]
            muxed = [f for f in hls if f.get("vcodec") != "none" and f.get("acodec") != "none"]
            print(f"KANA format diagnostic video={video_id} formats={len(formats)} hls={len(hls)} muxed={len(muxed)} live_status={info.get('live_status')}")
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


def kana_managed_body(config=None):
    """One canonical two-slot Kana block for all FreeWiFi writers.

    Never reconstruct this block from the YouTube-only playlist alone.
    """
    cfg = config if config is not None else load_config()
    item = cfg["special"]["kana"]
    youtube_body = playlist_body(KANA_OUT)
    if not youtube_body:
        # No new confirmed stream is not permission to delete either FreeWiFi
        # channel. Reuse the last watch target as an explicitly unverified
        # placeholder; never advertise an old watch ID as a current LIVE.
        old_url = parse_m3u(FREEWIFI).get(item["id"], {}).get("url") if FREEWIFI.exists() else None
        state_url = read_json(KANA_STATE, {}).get("watch_url")
        watch = next((
            url for url in (old_url, state_url)
            if isinstance(url, str)
            and re.fullmatch(r"https://www\.youtube\.com/watch\?v=[A-Za-z0-9_-]{11}", url)
        ), None)
        if not watch:
            watch = item["channel"].rstrip("/") + "/live"
        youtube_body = entry(item, watch, item["name"] + "【配信確認中】")
    iptv_item = dict(item, id=KANA_IPTV_ID, name=item["name"] + " IPTV")
    iptv_body = entry(iptv_item, KANA_9X_PROXY, iptv_item["name"] + "【LIVE】")
    return (youtube_body + "\n\n" + iptv_body).strip()


def probe_direct_url(url, mode):
    """Verify volatile non-YouTube direct streams before publishing them."""
    if not mode:
        return True, "DIRECT"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152 Safari/537.36",
        "Accept": "multipart/x-mixed-replace,image/jpeg,image/*,video/*,*/*;q=.5",
        "Cache-Control": "no-cache",
    }
    try:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=15) as response:
            status = int(getattr(response, "status", 200) or 200)
            content_type = (response.headers.get("Content-Type") or "").lower()
            if status < 200 or status >= 300:
                return False, f"DIRECT_HTTP_{status}"
            if mode == "visual":
                if (
                    "multipart/x-mixed-replace" in content_type
                    or content_type.startswith("image/")
                    or content_type.startswith("video/")
                ):
                    return True, "DIRECT_OK"
                return False, "DIRECT_BAD_TYPE"
            return True, "DIRECT_OK"
    except Exception as exc:
        print(f"DIRECT probe failed: {url} [{type(exc).__name__}: {exc}]")
        return False, "DIRECT_DOWN"


def resolve_general_one(index, item, previous):
    page = (item.get("page") or "").strip()
    direct_url = (item.get("direct_url") or "").strip()
    try:
        if direct_url:
            ok, code = probe_direct_url(direct_url, item.get("probe"))
            return index, item, (direct_url if ok else None), code
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
    elif not url and item.get("persistent"):
        url = general_target(item)
        print(f'GENERAL keep persistent target: {item["id"]}')
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


def update_general(config, only_ids=None):
    # Resolve playable HLS in GitHub Actions. Do not make every channel depend
    # on the Render resolver at playback time: a resolver outage would blank
    # the entire YouTube group at once.
    previous = parse_m3u(GENERAL_OUT)
    general = config["general"]
    selected = {x for x in (only_ids or []) if x}
    resolved = [None] * len(general)

    work = []
    for i, item in enumerate(general):
        if selected and item["id"] not in selected:
            old = previous.get(item["id"], {}).get("url")
            if old:
                # Preserve non-target rows while refreshing only urgent channels.
                # Rebuild EXTINF from current config so renamed channels update too.
                resolved[i] = entry(item, old)
            continue
        work.append((i, item))

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [
            pool.submit(resolve_general_one, i, item, previous)
            for i, item in work
        ]
        for future in as_completed(futures):
            i, item, url, code = future.result()

            # Never preserve the broken Render resolver as a fallback.
            if (
                url
                and "iptv-9x-browser-proxy.onrender.com/yt-" in url
                and not item.get("persistent")
            ):
                url = None

            if not url:
                old = previous.get(item["id"], {}).get("url")
                if (
                    code in TRANSIENT
                    and old
                    and (
                        "iptv-9x-browser-proxy.onrender.com/yt-" not in old
                        or item.get("persistent")
                    )
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
    print(f"GENERAL output: {len(blocks)}/{len(general)}" + (f" targeted={sorted(selected)}" if selected else ""))


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
    """Prefer a muxed A/V HLS *media* playlist for IPTV players.

    yt-dlp's manifest_url is the adaptive master (hls_variant). Some IPTV
    players cannot select the separate audio rendition correctly. Formats
    contain concrete hls_playlist URLs; require explicit video AND audio to
    avoid accidentally publishing a silent, video-only stream.
    """
    choices = []
    for fmt in info.get("formats") or []:
        url = (fmt.get("url") or "").strip()
        protocol = (fmt.get("protocol") or "").lower()
        if not url.startswith(("http://", "https://")) or "m3u8" not in protocol:
            continue
        video = str(fmt.get("vcodec") or "none").lower()
        audio = str(fmt.get("acodec") or "none").lower()
        if video == "none" or audio == "none":
            continue
        try:
            height = int(fmt.get("height") or 0)
            bitrate = float(fmt.get("tbr") or 0)
        except (ValueError, TypeError):
            continue
        # Prefer H.264 + AAC for broad APTV/VLC compatibility. Avoid 4K when
        # a normal 360-720p stream is available.
        avc = video.startswith(("avc", "h264"))
        aac = audio.startswith(("mp4a", "aac"))
        practical = 360 <= height <= 720
        choices.append(((int(avc and aac), int(practical), min(height, 720), bitrate), url))
    if choices:
        return max(choices, key=lambda row: row[0])[1]

    # The adaptive master is a fallback only when no confirmed muxed stream
    # exists (e.g. the livestream exclusively uses separate audio/video).
    manifest = (info.get("manifest_url") or "").strip()
    if manifest.startswith(("http://", "https://")) and ".m3u8" in manifest:
        return manifest
    return None


def kana_hls_still_usable(url, video_id):
    """Preserve verified-current HLS through temporary yt-dlp failures only."""
    if not isinstance(url, str) or ".m3u8" not in url or not url.startswith("https://"):
        return False
    parsed = urlsplit(url)
    path = parsed.path
    if "/force_finished/1" in path.lower() or "/playlist_type/clean" in path.lower():
        return False
    embedded_id = re.search(r"/id/([A-Za-z0-9_-]{11})(?:[./]|$)", path)
    if not embedded_id or embedded_id.group(1) != video_id:
        return False
    expiry = re.search(r"/expire/(\d+)", path)
    return bool(expiry and int(expiry.group(1)) > time.time() + 900)


def update_kana(config):
    item = config["special"]["kana"]
    previous = read_json(KANA_STATE, {})
    channel = item["channel"].rstrip("/")
    trouble = False
    confirmed = False
    live_candidates = []
    def live_rank(info):
        title = (info.get("title") or "").lower()
        vertical = "縦型" in title or "縦配信" in title or "vertical" in title or "shorts" in title
        return (int(vertical), -int(info.get("concurrent_view_count") or 0))


    def publish_selected(selected):
        status = (selected.get("live_status") or "").lower()
        vid = selected["id"]
        watch = "https://www.youtube.com/watch?v=" + vid
        start = info_start(selected, previous)
        play = selected.get("_resolved_hls") or info_hls(selected)
        if status == "is_live" and (not play or "/hls_variant/" in play):
            # Some yt-dlp JSON responses expose only an adaptive master.
            # Ask the single-format resolver for a muxed media playlist before
            # using the master as the last resort.
            alternate, _ = direct_hls(watch)
            if alternate and (not play or "/hls_playlist/" in alternate):
                play = alternate
        if status == "is_live" and not play:
            print(f"KANA HLS unavailable: {vid}; do not publish YouTube watch URL as IPTV")
        # Stable two-slot contract: Kana YouTube is ALWAYS a watch URL.
        # HLS (if any) belongs exclusively to Kana IPTV, never overwrite the watch slot.
        if status == "is_live":
            label = item["name"] + "【LIVE】"
        else:
            when = datetime.fromtimestamp(start, JST).strftime("%m/%d %H:%M") if start else ""
            label = item["name"] + (f"【配信予定 {when}】" if when else "【配信予定】")
        write_playlist(KANA_OUT, [entry(item, watch, label)])
        iptv_item = dict(item, id=KANA_IPTV_ID, name=item["name"] + " IPTV")
        iptv_url = play if status == "is_live" and play and (".m3u8" in play or "manifest.googlevideo.com/" in play) else None
        if not iptv_url and status == "is_live":
            old_iptv = parse_m3u(KANA_IPTV_OUT).get(KANA_IPTV_ID, {}).get("url")
            if kana_hls_still_usable(old_iptv, vid):
                iptv_url = old_iptv
                print(f"KANA preserve same-video unexpired HLS: {vid}")
        write_playlist(KANA_IPTV_OUT, [entry(iptv_item, iptv_url, iptv_item["name"] + "【LIVE】")] if iptv_url else [])
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
            "check_error": status == "is_live" and not bool(play),
            "hls_status": "OK" if play else ("UNAVAILABLE" if status == "is_live" else "NOT_STARTED"),
            "checked_at": datetime.now(JST).isoformat(timespec="seconds"),
        })
        print(f"KANA {status}: {vid}")

    # Fast path: the most common transition is the already-known reservation
    # changing from upcoming -> live. Check that exact video first instead of
    # crawling the whole channel before looking at it.
    # Published watch ID may have been advanced by the independent DAY/MID
    # resolver while kana.json lagged. Never roll that newer slot back to
    # the older state file's remembered stream.
    published_watch = parse_m3u(KANA_OUT).get(item["id"], {}).get("url") or ""
    published_match = re.search(r"^https://(?:www\.)?youtube\.com/watch\?v=([A-Za-z0-9_-]{11})(?:[&#]|$)", published_watch)
    published_id = published_match.group(1) if published_match else None
    previous_id = previous.get("video_id")
    previous_start = int(previous.get("start_timestamp") or 0)
    now_utc = int(datetime.now(timezone.utc).timestamp())
    if previous_id and previous_start and now_utc - previous_start > 24 * 3600:
        print(f"KANA old state ignored: {previous_id} (more than 24h old)")
        previous_id = None
    if published_id and published_id != previous_id:
        print(f"KANA current published watch takes precedence: {published_id} over {previous_id}")
        previous_id = None
    previous_info = None
    if previous_id:
        info, code = inspect_watch(previous_id)
        if info and official_youtube(info, item["channel_id"], item.get("handle")):
            status = (info.get("live_status") or "").lower()
            if status == "is_live":
                previous_info = info
            if status == "is_upcoming":
                previous_info = info
        elif code in TRANSIENT:
            trouble = True

    # Primary discovery is the official streams tab only. Keep the list small:
    # we only need current live/upcoming slots, not dozens of old broadcasts.
    candidates = [published_id] if published_id else []
    if previous_id and previous_id not in candidates:
        candidates.append(previous_id)
    # Confirmed 2026-11-21 normal-stream reservation, supplied by channel viewer.
    # Expire this one-day hint automatically; verify official channel ownership below.
    if datetime.now(JST).date().isoformat() == "2026-11-21":
        candidates.insert(0, "DAmfaJ-bGeg")
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
    official_stream_ids = {x["id"] for x in rows if x.get("id")}
    candidates += [x["id"] for x in ordered[:6]]

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
            # The metadata JSON endpoint may fail while the direct live HLS
            # endpoint still works. Only try IDs supplied by the official
            # channel streams listing (or the previously verified ID).
            if vid == previous_id or vid in official_stream_ids:
                live_url, live_code = direct_hls("https://www.youtube.com/watch?v=" + vid)
                if live_url and ("manifest.googlevideo.com/" in live_url or ".m3u8" in live_url):
                    write_playlist(KANA_OUT, [entry(item, "https://www.youtube.com/watch?v=" + vid, item["name"] + "【YouTube】")])
                    iptv_item = dict(item, id=KANA_IPTV_ID, name=item["name"] + " IPTV")
                    write_playlist(KANA_IPTV_OUT, [entry(iptv_item, live_url, iptv_item["name"] + "【LIVE】")])
                    write_json(KANA_STATE, {
                        "state": "is_live", "channel": item.get("handle"),
                        "channel_id": item["channel_id"], "video_id": vid,
                        "watch_url": "https://www.youtube.com/watch?v=" + vid,
                        "play_url": live_url, "direct_hls": True,
                        "title": item["name"], "check_error": False,
                        "checked_at": datetime.now(JST).isoformat(timespec="seconds"),
                    })
                    print(f"KANA direct HLS fallback succeeded: {vid}")
                    return
                print(f"KANA direct HLS fallback failed: {vid} reason={live_code}")
            if code in TRANSIENT:
                trouble = True
            print(f"KANA metadata inspection failed: {vid} reason={code}")
            continue
        if not official_youtube(info, item["channel_id"], item.get("handle")):
            continue
        status = (info.get("live_status") or "").lower()
        if status == "is_live":
            live_candidates.append(info)
        if status == "is_upcoming":
            chosen.append(info)

    # Search/live-page fallback is only needed when the official streams tab did
    # not produce ANY usable live/upcoming slot. Do not spend the whole worker
    # timeout crawling searches when we already found a running normal stream.
    if not chosen and not live_candidates:
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
                live_candidates.append(info)
            if status == "is_upcoming":
                chosen.append(info)

    if live_candidates:
        # Prefer the normal broadcast, but never publish a watch URL as a
        # playable IPTV stream when another official live has valid HLS.
        live_candidates.sort(key=live_rank)
        resolved = []
        for info in live_candidates:
            play = info_hls(info)
            if not play:
                play, reason = direct_hls("https://www.youtube.com/watch?v=" + info["id"])
                if not play:
                    print(f"KANA HLS unavailable: {info['id']} reason={reason}")
            if play:
                info = dict(info)
                info["_resolved_hls"] = play
                resolved.append(info)
        if resolved:
            publish_selected(resolved[0])
        else:
            publish_selected(live_candidates[0])
        return

    if chosen:
        now = int(datetime.now(timezone.utc).timestamp())
        chosen.sort(key=lambda x: info_start(x, previous) or now + 10**9)
        # yt-dlp metadata can lag behind the actual YouTube broadcast start.
        # Probe the HLS endpoint after the scheduled start, but never publish
        # a watch URL or claim a live IPTV stream without a real HLS manifest.
        upcoming = chosen[0]
        scheduled = info_start(upcoming, previous)
        if scheduled and now >= scheduled:
            vid = upcoming["id"]
            live_url, reason = direct_hls("https://www.youtube.com/watch?v=" + vid)
            if live_url and (".m3u8" in live_url or "manifest.googlevideo.com/" in live_url):
                live = dict(upcoming, live_status="is_live", _resolved_hls=live_url)
                print(f"KANA HLS resolved after scheduled start despite stale upcoming metadata: {vid}")
                publish_selected(live)
                return
            print(f"KANA started-time HLS probe unsuccessful video={vid} reason={reason}")
        publish_selected(upcoming)
        return

    if trouble or not confirmed:
        state = dict(previous)
        state["check_error"] = True
        state["checked_at"] = datetime.now(JST).isoformat(timespec="seconds")
        write_json(KANA_STATE, state)
        print("KANA check inconclusive; previous output preserved")
        return

    write_playlist(KANA_OUT, [])
    write_playlist(KANA_IPTV_OUT, [])
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

    # FreeWiFi contains exactly two managed Kana slots: YouTube watch and stable IPTV relay.
    # General live cameras and Mandarin Pirates remain available in youtube/output/
    # but must never be projected into the aggregate FreeWiFi playlist.
    block = GENERAL_START + "\n" + GENERAL_END
    pat = re.compile(re.escape(GENERAL_START) + r".*?" + re.escape(GENERAL_END), re.S)
    if not pat.search(text):
        raise SystemExit("GENERAL_YOUTUBE managed block missing from freewifi")
    text = pat.sub(lambda _m: block, text, count=1)

    kana_id = config["special"]["kana"]["id"]
    text = re.sub(re.escape(KANA_START) + r".*?" + re.escape(KANA_END) + r"\n?", "", text, flags=re.S)
    text = strip_entry(text, kana_id)
    text = strip_entry(text, KANA_IPTV_ID)
    kana_body = kana_managed_body(config)
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


def update_kana_epg(config):
    """Publish verified Kana metadata independently of HLS availability."""
    state = read_json(KANA_STATE, {})
    item = config["special"]["kana"]
    title = (state.get("title") or "").strip()
    status = (state.get("state") or "").lower()
    stamp = state.get("start_timestamp")
    if status not in ("is_live", "is_upcoming") or not title or not stamp:
        return
    try:
        start = datetime.fromtimestamp(int(stamp), JST)
    except (ValueError, TypeError, OverflowError):
        return
    if start.date() != datetime.now(JST).date():
        return
    if not EPG_PATH.exists() or not EPG_PATH.stat().st_size:
        return
    tree = ET.parse(EPG_PATH)
    root = tree.getroot()
    cid = item["id"]
    if not any(ch.get("id") == cid for ch in root.findall("channel")):
        ch = ET.Element("channel", {"id": cid})
        ET.SubElement(ch, "display-name").text = item["name"]
        first = next((i for i, el in enumerate(root) if el.tag == "programme"), len(root))
        root.insert(first, ch)
    # Do not touch any other channel. The stop is an EPG display window,
    # not a claim that YouTube has published an actual end time.
    for p in list(root.findall("programme")):
        if p.get("channel") == cid:
            root.remove(p)
    stop = start + timedelta(hours=8)
    fmt = lambda d: d.strftime("%Y%m%d%H%M%S %z")
    p = ET.SubElement(root, "programme", {
        "channel": cid, "start": fmt(start), "stop": fmt(stop)
    })
    ET.SubElement(p, "title", {"lang": "ja"}).text = title
    ET.SubElement(p, "desc", {"lang": "ja"}).text = (
        "華奈tube公式 / " + ("ライブ配信中" if status == "is_live" else "配信予定")
        + " / 終了時刻未発表（EPG表示枠は暫定）"
    )
    ET.indent(tree, space="  ")
    tree.write(EPG_PATH, encoding="utf-8", xml_declaration=True)


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
    if kana_count > 1 or text.count(f'tvg-id="{KANA_IPTV_ID}"') > 1:
        raise SystemExit("duplicate Kana entry in freewifi")

    # FreeWiFi policy: KanaTube is the only YouTube entry allowed.
    stray_youtube = [
        line for line in text.splitlines()
        if line.startswith("#EXTINF:")
        and 'tvg-id="youtube.' in line
        and f'tvg-id="{kana_id}"' not in line
        and f'tvg-id="{KANA_IPTV_ID}"' not in line
    ]
    if stray_youtube:
        raise SystemExit("non-Kana YouTube entry remains in freewifi: " + stray_youtube[0])

    # Validate the one authoritative two-slot FreeWiFi projection. The IPTV
    # slot is ALWAYS the stable Railway relay; kana.json.play_url is an
    # upstream, expiring HLS and must never be compared to the relay URL.
    kana_entries = parse_m3u(FREEWIFI)
    kana_entry = kana_entries.get(kana_id)
    iptv_entry = kana_entries.get(KANA_IPTV_ID)
    if not kana_entry or not iptv_entry:
        raise SystemExit("both Kana YouTube and IPTV slots must remain in freewifi")
    if iptv_entry.get("url") != KANA_9X_PROXY:
        raise SystemExit("Kana IPTV must use the stable Railway relay")

    # The published YouTube playlist is the actual source of the YouTube
    # slot. kana.json is observational metadata and may lag when 429/403
    # blocks a refresh; an old state must not make unrelated FreeWiFi jobs fail.
    source_entry = parse_m3u(KANA_OUT).get(kana_id)
    if source_entry:
        if kana_entry.get("url") != source_entry.get("url"):
            raise SystemExit("Kana YouTube URL differs from canonical playlist")
        if kana_entry.get("ext") != source_entry.get("ext"):
            raise SystemExit("Kana YouTube label differs from canonical playlist")
        state_watch = read_json(KANA_STATE, {}).get("watch_url")
        if state_watch and state_watch != source_entry.get("url"):
            print("KANA warning: state watch URL is stale; source playlist takes precedence")
    else:
        # With no verified current broadcast, preserve both slots but
        # explicitly mark the YouTube watch target as unverified.
        if "【配信確認中】" not in (kana_entry.get("ext") or ""):
            raise SystemExit("Kana missing watch source must be labelled 配信確認中")

    print("YouTube v2 validation OK")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=("general", "special", "all"), default="all")
    parser.add_argument("--ids", default="", help="Comma-separated general channel ids to refresh first")
    parser.add_argument("--sync-only", action="store_true")
    parser.add_argument("--epg-only", action="store_true")
    args = parser.parse_args()
    config = load_config()

    if args.epg_only:
        update_kana_epg(config)
        update_mandarin_epg(config)
        return
    if args.sync_only:
        sync_freewifi(config)
        validate(config)
        return

    if args.scope in ("general", "all"):
        only_ids = [x.strip() for x in args.ids.split(",") if x.strip()]
        update_general(config, only_ids=only_ids)
    if args.scope in ("special", "all"):
        update_kana(config)
        update_kana_epg(config)
        update_mandarin(config)
        update_mandarin_epg(config)
    sync_freewifi(config)
    validate(config)


if __name__ == "__main__":
    main()
