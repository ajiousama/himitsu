#!/usr/bin/env python3
# final non-VOD rerun 2026-10-08
import concurrent.futures
import datetime as dt
import json
import re
import threading
import time
from collections import Counter, defaultdict
from urllib.parse import urljoin, urlsplit

import requests

PLAYLIST = "freewifi"
RESULT = "freewifi_check_result.json"
MAX_WORKERS = 32
CONNECT_TIMEOUT = 4
READ_TIMEOUT = 8
MAX_BYTES = 131072
PER_HOST = 4
SKIP_GROUPS = {"VOD"}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/154 Safari/537.36",
    "Accept": "application/vnd.apple.mpegurl,application/x-mpegURL,application/dash+xml,text/html,text/plain,*/*",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "close",
}

_host_lock = threading.Lock()
_host_semaphores = {}


def host_sem(url):
    host = urlsplit(url).netloc.lower()
    with _host_lock:
        sem = _host_semaphores.get(host)
        if sem is None:
            sem = threading.Semaphore(PER_HOST)
            _host_semaphores[host] = sem
        return sem


def parse_entries(lines):
    entries = []
    for i, line in enumerate(lines):
        if not line.startswith("#EXTINF"):
            continue
        j = i + 1
        while j < len(lines) and (not lines[j].strip() or lines[j].startswith("#")):
            j += 1
        if j >= len(lines):
            continue
        url = lines[j].strip()
        if not re.match(r"^https?://", url, re.I):
            continue
        title = line.split(",", 1)[1] if "," in line else ""
        title = re.sub(r"^🟢\s*", "", title)
        m = re.search(r'group-title="([^"]*)"', line)
        group = m.group(1) if m else ""
        mid = re.search(r'tvg-id="([^"]*)"', line)
        tvg_id = mid.group(1) if mid else ""
        entries.append({
            "line": i, "url_line": j, "url": url,
            "title": title, "group": group, "tvg_id": tvg_id,
        })
    return entries


def get_limited(url, max_bytes=MAX_BYTES, accept=None):
    headers = dict(HEADERS)
    if accept:
        headers["Accept"] = accept
    sem = host_sem(url)
    host = urlsplit(url).netloc.lower()
    read_timeout = 16 if host == "freewifi-radio-production.up.railway.app" else READ_TIMEOUT
    with sem:
        with requests.get(
            url,
            headers=headers,
            timeout=(CONNECT_TIMEOUT, read_timeout),
            allow_redirects=True,
            stream=True,
        ) as r:
            data = b""
            for chunk in r.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                data += chunk
                if len(data) >= max_bytes:
                    break
            return r, data


def looks_like_mpegts(data: bytes) -> bool:
    if len(data) < 188 * 3:
        return False
    # MPEG-TS packets are 188 bytes and start with sync byte 0x47.
    # Allow a small leading offset in case an upstream prepends a few bytes.
    for offset in range(min(188, len(data))):
        if data[offset] != 0x47:
            continue
        hits = 0
        pos = offset
        while pos < len(data) and hits < 5:
            if data[pos] != 0x47:
                break
            hits += 1
            pos += 188
        if hits >= 3:
            return True
    return False


def first_media_uri(text):
    lines = [x.strip() for x in text.splitlines() if x.strip()]
    for idx, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF"):
            for nxt in lines[idx + 1:]:
                if not nxt.startswith("#"):
                    return nxt, "child"
    for line in lines:
        if not line.startswith("#"):
            return line, "segment"
    return None, None


def probe_hls(url):
    r, data = get_limited(url)
    if r.status_code != 200:
        return False, r.status_code, f"http_{r.status_code}", r.url, None
    ctype = (r.headers.get("content-type") or "").lower()
    if "mp2t" in ctype or looks_like_mpegts(data):
        return True, r.status_code, "mpegts", r.url, None

    text = data.decode("utf-8", "ignore")
    if "#EXTM3U" not in text:
        return False, r.status_code, "non_hls", r.url, None

    media, kind = first_media_uri(text)
    if not media:
        return True, r.status_code, "hls_manifest_only", r.url, None

    media_url = urljoin(r.url, media)
    r2, data2 = get_limited(media_url, max_bytes=65536)
    if r2.status_code != 200:
        return False, r2.status_code, f"{kind}_http_{r2.status_code}", r2.url, media_url

    if kind == "child":
        child = data2.decode("utf-8", "ignore")
        if "#EXTM3U" not in child:
            return False, r2.status_code, "child_non_hls", r2.url, media_url
        seg, kind2 = first_media_uri(child)
        if not seg:
            return True, r2.status_code, "hls_child_manifest_only", r2.url, media_url
        seg_url = urljoin(r2.url, seg)
        r3, data3 = get_limited(seg_url, max_bytes=32768, accept="*/*")
        if r3.status_code == 200 and len(data3) > 0:
            return True, 200, "hls_segment", r3.url, seg_url
        return False, r3.status_code, f"segment_http_{r3.status_code}", r3.url, seg_url

    if len(data2) > 0:
        return True, 200, "hls_segment", r2.url, media_url
    return False, r2.status_code, "empty_segment", r2.url, media_url


def probe(url):
    started = time.monotonic()
    last_error = None

    for attempt in range(2):
        try:
            low = url.lower()
            if ".mpd" in low:
                r, data = get_limited(url)
                text = data.decode("utf-8", "ignore")
                ok = r.status_code == 200 and ("<mpd" in text.lower() or "urn:mpeg:dash" in text.lower())
                return {
                    "ok": ok,
                    "status": r.status_code,
                    "reason": "dash_mpd" if ok else (f"http_{r.status_code}" if r.status_code != 200 else "non_mpd"),
                    "elapsed_ms": round((time.monotonic() - started) * 1000),
                    "final_url": r.url,
                    "probe_url": None,
                }

            if "youtube.com/watch" in low or "youtu.be/" in low:
                r, data = get_limited(url, max_bytes=32768, accept="text/html,*/*")
                ok = r.status_code == 200 and len(data) > 0
                return {
                    "ok": ok,
                    "status": r.status_code,
                    "reason": "youtube_page" if ok else f"http_{r.status_code}",
                    "elapsed_ms": round((time.monotonic() - started) * 1000),
                    "final_url": r.url,
                    "probe_url": None,
                }

            ok, status, reason, final_url, probe_url = probe_hls(url)
            return {
                "ok": ok,
                "status": status,
                "reason": reason,
                "elapsed_ms": round((time.monotonic() - started) * 1000),
                "final_url": final_url,
                "probe_url": probe_url,
            }

        except requests.RequestException as e:
            last_error = type(e).__name__
            if attempt == 0:
                time.sleep(0.2)
        except Exception as e:
            last_error = f"error_{type(e).__name__}"
            break

    return {
        "ok": False,
        "status": None,
        "reason": last_error or "request_error",
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "final_url": None,
        "probe_url": None,
    }


def host_of(url):
    try:
        return urlsplit(url).netloc
    except Exception:
        return ""


def mark_prestart_pending(entries, results):
    """Do not call scheduled sports streams dead hours before their first race."""
    status_path = "today_public_sports_status.json"
    try:
        with open(status_path, "r", encoding="utf-8-sig") as f:
            status = json.load(f)
    except Exception:
        return

    JST = dt.timezone(dt.timedelta(hours=9))
    now = dt.datetime.now(JST)
    channels = status.get("channels") or {}
    for e in entries:
        if e.get("group") != "今日の開催場":
            continue
        r = results.get(e["url"]) or {}
        if r.get("ok"):
            continue
        info = channels.get(e.get("tvg_id")) or {}
        nr = info.get("next_race") or {}
        start = nr.get("start")
        if not isinstance(start, str) or not re.fullmatch(r"\d{1,2}:\d{2}", start):
            continue
        hh, mm = map(int, start.split(":"))
        race_dt = dt.datetime.combine(now.date(), dt.time(hh, mm), tzinfo=JST)
        if now < race_dt - dt.timedelta(minutes=90):
            r["pending"] = True
            r["reason"] = "scheduled_not_live_yet"
            r["scheduled_start"] = start
            results[e["url"]] = r


def main():
    with open(PLAYLIST, "r", encoding="utf-8-sig") as f:
        original = f.read()
    lines = original.splitlines()
    entries = parse_entries(lines)
    check_entries = [e for e in entries if e.get("group") not in SKIP_GROUPS]
    playlist_urls = list(dict.fromkeys(e["url"] for e in check_entries))

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(probe, u): u for u in playlist_urls}
        for fut in concurrent.futures.as_completed(futs):
            u = futs[fut]
            try:
                results[u] = fut.result()
            except Exception as e:
                results[u] = {
                    "ok": False,
                    "status": None,
                    "reason": f"worker_{type(e).__name__}",
                    "elapsed_ms": None,
                    "final_url": None,
                    "probe_url": None,
                }

    mark_prestart_pending(check_entries, results)

    green_entries = 0
    for e in entries:
        if e.get("group") in SKIP_GROUPS:
            continue
        i = e["line"]
        line = lines[i]
        if "," not in line:
            continue
        prefix, title = line.split(",", 1)
        title = re.sub(r"^🟢\s*", "", title)
        if results.get(e["url"], {}).get("ok"):
            title = "🟢" + title
            green_entries += 1
        lines[i] = prefix + "," + title

    new_content = "\n".join(lines) + ("\n" if original.endswith("\n") else "")
    with open(PLAYLIST, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_content)

    host_stats = defaultdict(lambda: {"ok": 0, "fail": 0, "pending": 0})
    group_stats = defaultdict(lambda: {"ok": 0, "fail": 0, "pending": 0, "total": 0})
    reasons = Counter()

    for e in check_entries:
        r = results[e["url"]]
        h = host_of(e["url"])
        g = e["group"] or "(none)"
        group_stats[g]["total"] += 1
        if r.get("ok"):
            host_stats[h]["ok"] += 1
            group_stats[g]["ok"] += 1
        elif r.get("pending"):
            host_stats[h]["pending"] += 1
            group_stats[g]["pending"] += 1
        else:
            host_stats[h]["fail"] += 1
            group_stats[g]["fail"] += 1
            reasons[r.get("reason", "unknown")] += 1

    report = {
        "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "entries": len(check_entries),
        "skipped_entries": len(entries) - len(check_entries),
        "skipped_groups": sorted(SKIP_GROUPS),
        "unique_urls": len(playlist_urls),
        "green_entries": green_entries,
        "green_unique_urls": sum(1 for r in results.values() if r.get("ok")),
        "pending_unique_urls": sum(1 for r in results.values() if r.get("pending")),
        "failed_unique_urls": sum(
            1 for r in results.values() if not r.get("ok") and not r.get("pending")
        ),
        "failure_reasons": dict(reasons.most_common()),
        "group_stats": dict(sorted(group_stats.items())),
        "host_stats": dict(sorted(host_stats.items())),
        "results": results,
    }
    with open(RESULT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    failed_entries = []
    pending_entries = []
    for e in check_entries:
        r = results[e["url"]]
        item = {
            "group": e["group"],
            "tvg_id": e["tvg_id"],
            "title": e["title"],
            "reason": r.get("reason"),
            "status": r.get("status"),
            "url": e["url"],
        }
        if r.get("pending"):
            item["scheduled_start"] = r.get("scheduled_start")
            pending_entries.append(item)
        elif not r.get("ok"):
            failed_entries.append(item)

    print(json.dumps({
        "entries": report["entries"],
        "unique_urls": report["unique_urls"],
        "green_entries": report["green_entries"],
        "green_unique_urls": report["green_unique_urls"],
        "pending_unique_urls": report["pending_unique_urls"],
        "failed_unique_urls": report["failed_unique_urls"],
        "failure_reasons": report["failure_reasons"],
        "group_stats": report["group_stats"],
        "host_stats": report["host_stats"],
        "failed_entries": failed_entries,
        "pending_entries": pending_entries,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
