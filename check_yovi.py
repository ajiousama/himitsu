#!/usr/bin/env python3
import concurrent.futures
import datetime as dt
import json
import re
import time
from collections import Counter, defaultdict
from urllib.parse import urlsplit

import requests

PLAYLIST = "yovi"
RESULT = "yovi_check_result.json"
MAX_WORKERS = 48
CONNECT_TIMEOUT = 4
READ_TIMEOUT = 8
MAX_BYTES = 65536

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/154 Safari/537.36",
    "Accept": "application/vnd.apple.mpegurl,application/x-mpegURL,text/plain,*/*",
    "Accept-Encoding": "gzip, deflate",
    "Connection": "close",
}

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
        title = re.sub(r"^🟢", "", title)
        entries.append({"line": i, "url_line": j, "url": url, "title": title})
    return entries

def probe(url):
    started = time.monotonic()
    last_error = None
    for attempt in range(2):
        try:
            with requests.get(
                url,
                headers=HEADERS,
                timeout=(CONNECT_TIMEOUT, READ_TIMEOUT),
                allow_redirects=True,
                stream=True,
            ) as r:
                status = r.status_code
                if status != 200:
                    return {
                        "ok": False,
                        "status": status,
                        "reason": f"http_{status}",
                        "elapsed_ms": round((time.monotonic() - started) * 1000),
                        "final_url": r.url,
                    }
                data = b""
                for chunk in r.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    data += chunk
                    if len(data) >= MAX_BYTES:
                        break
                text = data.decode("utf-8", "ignore")
                ok = "#EXTM3U" in text
                return {
                    "ok": ok,
                    "status": status,
                    "reason": "hls" if ok else "non_hls",
                    "elapsed_ms": round((time.monotonic() - started) * 1000),
                    "final_url": r.url,
                }
        except requests.RequestException as e:
            last_error = type(e).__name__
            if attempt == 0:
                time.sleep(0.15)
    return {
        "ok": False,
        "status": None,
        "reason": last_error or "request_error",
        "elapsed_ms": round((time.monotonic() - started) * 1000),
        "final_url": None,
    }

def host_of(url):
    try:
        return urlsplit(url).netloc
    except Exception:
        return ""

def main():
    with open(PLAYLIST, "r", encoding="utf-8-sig") as f:
        original = f.read()
    lines = original.splitlines()
    entries = parse_entries(lines)
    urls = list(dict.fromkeys(e["url"] for e in entries))

    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(probe, u): u for u in urls}
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
                }

    green_entries = 0
    for e in entries:
        i = e["line"]
        line = lines[i]
        if "," not in line:
            continue
        prefix, title = line.split(",", 1)
        title = re.sub(r"^🟢", "", title)
        if results.get(e["url"], {}).get("ok"):
            title = "🟢" + title
            green_entries += 1
        lines[i] = prefix + "," + title

    new_content = "\n".join(lines) + ("\n" if original.endswith("\n") else "")
    with open(PLAYLIST, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_content)

    host_stats = defaultdict(lambda: {"ok": 0, "fail": 0})
    reasons = Counter()
    for u, r in results.items():
        h = host_of(u)
        if r.get("ok"):
            host_stats[h]["ok"] += 1
        else:
            host_stats[h]["fail"] += 1
            reasons[r.get("reason", "unknown")] += 1

    report = {
        "checked_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "entries": len(entries),
        "unique_urls": len(urls),
        "green_entries": green_entries,
        "green_unique_urls": sum(1 for r in results.values() if r.get("ok")),
        "failed_unique_urls": sum(1 for r in results.values() if not r.get("ok")),
        "failure_reasons": dict(reasons.most_common()),
        "host_stats": dict(sorted(host_stats.items())),
        "results": results,
    }
    with open(RESULT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "entries": report["entries"],
        "unique_urls": report["unique_urls"],
        "green_entries": report["green_entries"],
        "green_unique_urls": report["green_unique_urls"],
        "failed_unique_urls": report["failed_unique_urls"],
        "failure_reasons": report["failure_reasons"],
        "host_stats": report["host_stats"],
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
