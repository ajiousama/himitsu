from __future__ import annotations

import json
import re
import subprocess
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

SRC = Path("youtube_channels.json")
OUT = Path("general_youtube.m3u")
FREEWIFI = Path("freewifi")
COOKIES = Path("youtube_cookies.txt")
START = "# === GENERAL_YOUTUBE_MANAGED_START ==="
END = "# === GENERAL_YOUTUBE_MANAGED_END ==="
CACHE_VERSION = "20260921-clean1"
MAX_WORKERS = 4
MIN_CALL_INTERVAL = 1.25
TRANSIENT = {"RATE_LIMIT", "BOT_CHECK", "COOKIE_ERROR", "TIMEOUT", "OTHER", "EXCEPTION"}

_lock = threading.Lock()
_last_call = 0.0


def run(cmd, timeout):
    global _last_call
    safe = list(cmd)
    if safe and safe[0] == "yt-dlp":
        safe[1:1] = ["--socket-timeout", "10", "--retries", "1", "--fragment-retries", "1"]
        with _lock:
            wait = MIN_CALL_INTERVAL - (time.monotonic() - _last_call)
            if wait > 0:
                time.sleep(wait)
            _last_call = time.monotonic()
    return subprocess.run(safe, capture_output=True, text=True, timeout=timeout)


def base_cmd():
    cmd = ["yt-dlp", "--js-runtimes", "node", "--no-warnings", "--no-cache-dir"]
    if COOKIES.exists() and COOKIES.stat().st_size > 20:
        cmd += ["--cookies", str(COOKIES)]
    return cmd


def classify(stderr):
    s = (stderr or "").lower()
    if "429" in s or "too many requests" in s or "rate limit" in s:
        return "RATE_LIMIT"
    if "sign in to confirm you" in s or "not a bot" in s:
        return "BOT_CHECK"
    if "cookies" in s and ("expired" in s or "invalid" in s or "login" in s):
        return "COOKIE_ERROR"
    if "this live event will begin" in s or "premieres in" in s:
        return "NOT_STARTED"
    if "not currently live" in s or "not live" in s:
        return "NOT_LIVE"
    if "private video" in s:
        return "PRIVATE"
    if "unavailable" in s:
        return "UNAVAILABLE"
    return "OTHER"


def direct_url(page):
    try:
        p = run(base_cmd() + [
            "--no-playlist", "--match-filter", "is_live",
            "-f", "best[protocol^=m3u8]/best[protocol*=m3u8]/best",
            "-g", page,
        ], 35)
    except subprocess.TimeoutExpired:
        return None, "TIMEOUT"
    urls = [x.strip() for x in p.stdout.splitlines() if x.strip().startswith(("http://", "https://"))]
    if p.returncode == 0 and len(urls) == 1:
        return urls[0], "OK"
    return None, classify(p.stderr)


def channel_live(page):
    base = re.sub(r"/(?:live|streams|videos)/?$", "", page.rstrip("/"))
    reasons = []
    for listing in (base + "/streams", base + "/videos"):
        try:
            p = run(base_cmd() + ["--flat-playlist", "--dump-json", "--playlist-end", "30", listing], 40)
        except subprocess.TimeoutExpired:
            reasons.append("TIMEOUT")
            continue
        if p.returncode != 0:
            reasons.append(classify(p.stderr))
            continue
        live_ids = []
        for line in p.stdout.splitlines():
            try:
                item = json.loads(line)
            except Exception:
                continue
            if (item.get("live_status") or "").lower() == "is_live" and item.get("id"):
                live_ids.append(item["id"])
        for vid in live_ids:
            url, code = direct_url("https://www.youtube.com/watch?v=" + vid)
            if url:
                return url, "OK"
            reasons.append(code)
    if any(x in TRANSIENT for x in reasons):
        return None, next(x for x in reasons if x in TRANSIENT)
    return None, "NOT_LIVE"


def search_live(query):
    try:
        p = run(base_cmd() + ["--flat-playlist", "--dump-json", "--playlist-end", "8", "ytsearch8:" + query], 40)
    except subprocess.TimeoutExpired:
        return None, "TIMEOUT"
    if p.returncode != 0:
        return None, classify(p.stderr)
    candidates = []
    for line in p.stdout.splitlines():
        try:
            item = json.loads(line)
        except Exception:
            continue
        if (item.get("live_status") or "").lower() == "is_live" and item.get("id"):
            candidates.append(item["id"])
    for vid in candidates[:3]:
        url, code = direct_url("https://www.youtube.com/watch?v=" + vid)
        if url:
            return url, "OK"
        if code in TRANSIENT:
            return None, code
    return None, "NOT_LIVE"


def old_urls():
    result = {}
    if not OUT.exists():
        return result
    lines = OUT.read_text(encoding="utf-8-sig", errors="replace").splitlines()
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
            result[m.group(1)] = lines[j].strip()
    return result


def resolve(index, item):
    page = (item.get("page") or "").strip()
    try:
        if page:
            if "watch?v=" in page or "youtu.be/" in page:
                url, code = direct_url(page)
            else:
                url, code = direct_url(page)
                if not url and code not in TRANSIENT:
                    url, code = channel_live(page)
        else:
            url, code = search_live(item.get("query") or item["name"])
        return index, item, url, code
    except Exception:
        return index, item, None, "EXCEPTION"


def video_key(url):
    if not url:
        return ""
    m = re.search(r"/id/([A-Za-z0-9_-]{11})(?:\.|/|$)", url)
    if m:
        return "video:" + m.group(1)
    m = re.search(r"[?&]v=([A-Za-z0-9_-]{11})(?:&|$)", url)
    if m:
        return "video:" + m.group(1)
    return url.split("?", 1)[0]


def logo_url(item):
    logo = (item.get("logo") or "").strip()
    if not logo:
        raise RuntimeError("missing logo for " + item["id"])
    return logo + ("&" if "?" in logo else "?") + "v=" + CACHE_VERSION


def render_entry(item, url):
    name = item["name"]
    return [
        f'#EXTINF:-1 tvg-id="{item["id"]}" tvg-name="{name}" tvg-logo="{logo_url(item)}" group-title="{item["group"]}",{name}',
        url,
        "",
    ]


def sync_freewifi(general):
    if not FREEWIFI.exists():
        raise SystemExit("freewifi missing")
    text = FREEWIFI.read_text(encoding="utf-8-sig", errors="replace")
    body = "\n".join(general.splitlines()[1:]).strip()
    block = START + "\n" + body + "\n" + END
    pat = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if not pat.search(text):
        raise SystemExit("GENERAL_YOUTUBE managed block missing")
    text = pat.sub(lambda _m: block, text, count=1)
    FREEWIFI.write_text(text.rstrip() + "\n", encoding="utf-8")


def main():
    items = json.loads(SRC.read_text(encoding="utf-8"))
    ids = [x.get("id") for x in items]
    if len(items) != 71 or len(set(ids)) != len(ids):
        raise SystemExit(f"youtube_channels.json invalid: count={len(items)} unique={len(set(ids))}")

    previous = old_urls()
    results = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = [pool.submit(resolve, i, item) for i, item in enumerate(items)]
        for f in as_completed(futures):
            results.append(f.result())
    results.sort(key=lambda x: x[0])

    out = ["#EXTM3U", ""]
    seen = set()
    kept = 0
    for _, item, url, code in results:
        cid = item["id"]
        old = previous.get(cid)

        if not url and code in TRANSIENT and old:
            url = old
            print(f"KEEP previous URL: {cid} [{code}]")
        elif not url and item.get("persistent") and item.get("page"):
            url = item["page"]
            print(f"KEEP persistent page: {cid}")
        elif not url:
            print(f"SKIP offline: {cid} [{code}]")
            continue

        key = video_key(url)
        if key and key in seen:
            if old and video_key(old) not in seen:
                url = old
                key = video_key(old)
                print(f"REPAIR duplicate with previous URL: {cid}")
            else:
                print(f"SKIP duplicate: {cid}")
                continue

        seen.add(key)
        out += render_entry(item, url)
        kept += 1

    general = "\n".join(out).rstrip() + "\n"
    if kept == 0:
        raise SystemExit("refusing to publish empty YouTube playlist")
    OUT.write_text(general, encoding="utf-8")
    sync_freewifi(general)
    print(f"YouTube LIVE rebuilt: {kept}/{len(items)}")


if __name__ == "__main__":
    main()
