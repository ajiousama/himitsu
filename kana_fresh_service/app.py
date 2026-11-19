import json
import os
import re
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from flask import Flask, Response, jsonify

app = Flask(__name__)
VIDEO_ID = os.environ.get("KANA_VIDEO_ID", "DVL04eDdDIE").strip()
WATCH = "https://www.youtube.com/watch?v=" + VIDEO_ID
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36"
CACHE_SECONDS = int(os.environ.get("CACHE_SECONDS", "90"))
_lock = threading.Lock()
_cache = {"checked": 0, "ok": False, "play_url": None, "source": None, "error": "not_checked"}

def _run(cmd, timeout=35):
    try:
        p = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except Exception as e:
        return 999, "", repr(e)

def _fetch(url, limit=262144):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/vnd.apple.mpegurl,application/x-mpegURL,text/plain,*/*",
    })
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status, r.geturl(), r.read(limit).decode("utf-8", "replace")

def _add(candidates, url, source):
    if not isinstance(url, str):
        return
    url = url.strip()
    if not url.startswith("http"):
        return
    if "manifest.googlevideo.com/" not in url and ".m3u8" not in url:
        return
    if all(u != url for u, _ in candidates):
        candidates.append((url, source))

def _resolve():
    candidates = []
    notes = []

    # A: watch-page embedded manifest, independent of yt-dlp live_status.
    try:
        status, _, html = _fetch(WATCH, 2_000_000)
        notes.append(f"page:{status}:{len(html)}")
        for m in re.finditer(r'"hlsManifestUrl":"([^"]+)"', html):
            try:
                _add(candidates, json.loads('"' + m.group(1) + '"'), "page:hlsManifestUrl")
            except Exception:
                pass
    except Exception as e:
        notes.append("page_error:" + type(e).__name__)

    # B: Streamlink, separate extractor implementation.
    rc, out, err = _run(["streamlink", "--stream-url", WATCH, "best"], 35)
    notes.append(f"streamlink:{rc}:{err[-180:]}")
    for line in out.splitlines():
        _add(candidates, line, "streamlink")

    # C: fresh yt-dlp, no old manager.py and no is_live gate.
    clients = [None, "android_vr", "web_safari", "mweb"]
    for client in clients:
        label = client or "default"
        extra = [] if not client else ["--extractor-args", "youtube:player_client=" + client]
        rc, out, err = _run([
            "yt-dlp", "--no-playlist", "--ignore-no-formats-error",
            "--js-runtimes", "node", *extra, "--dump-single-json", WATCH
        ], 40)
        notes.append(f"ytdlp-json:{label}:{rc}:{err[-220:]}")
        if out.strip():
            try:
                data = json.loads(out)
                for key in ("hls_manifest_url", "hlsManifestUrl", "url"):
                    _add(candidates, data.get(key), f"yt-dlp:{label}:{key}")
                for fmt in data.get("formats") or []:
                    proto = str(fmt.get("protocol") or "").lower()
                    u = fmt.get("url")
                    if "m3u8" in proto or (isinstance(u, str) and "manifest.googlevideo.com/" in u):
                        _add(candidates, u, f"yt-dlp:{label}:format:{fmt.get('format_id')}")
            except Exception as e:
                notes.append("json_error:" + label + ":" + type(e).__name__)

        rc, out, err = _run([
            "yt-dlp", "--no-playlist", "--js-runtimes", "node", *extra,
            "-f", "best[protocol*=m3u8]/best", "-g", WATCH
        ], 40)
        notes.append(f"ytdlp-g:{label}:{rc}:{err[-220:]}")
        for line in out.splitlines():
            _add(candidates, line, "yt-dlp-g:" + label)

    verified = []
    i = 0
    while i < len(candidates):
        url, source = candidates[i]
        i += 1
        try:
            status, _, body = _fetch(url)
            if status != 200 or "#EXTM3U" not in body[:4096]:
                continue
            verified.append((url, source, body))
            if "#EXT-X-STREAM-INF" in body:
                lines = [x.strip() for x in body.splitlines() if x.strip()]
                for n, line in enumerate(lines):
                    if line.startswith("#EXT-X-STREAM-INF") and n + 1 < len(lines):
                        child = lines[n + 1]
                        if child and not child.startswith("#"):
                            _add(candidates, urllib.parse.urljoin(url, child), source + ":child")
        except Exception as e:
            notes.append("probe_error:" + source + ":" + type(e).__name__)

    media = [x for x in verified if "#EXT-X-STREAM-INF" not in x[2]]
    winner = media[0] if media else (verified[0] if verified else None)
    now = int(time.time())
    if not winner:
        return {
            "checked": now, "ok": False, "play_url": None, "source": None,
            "error": "no_verified_hls", "candidate_count": len(candidates),
            "notes": notes[-20:],
        }

    url, source, _ = winner
    m = re.search(r"/expire/(\d+)", url)
    return {
        "checked": now, "ok": True, "play_url": url, "source": source,
        "expire_epoch": int(m.group(1)) if m else None,
        "candidate_count": len(candidates), "notes": notes[-20:],
    }

def current(force=False):
    global _cache
    now = time.time()
    with _lock:
        if not force and _cache.get("checked") and now - _cache["checked"] < CACHE_SECONDS:
            return _cache
        _cache = _resolve()
        return _cache

@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "kana-iptv-fresh"})

@app.get("/status")
def status():
    return jsonify(current(force=True))

@app.get("/raw")
def raw():
    s = current(force=True)
    if not s.get("ok"):
        return Response("NO_VERIFIED_HLS\n", status=503, mimetype="text/plain")
    return Response(s["play_url"] + "\n", mimetype="text/plain")

@app.get("/kana.m3u")
def kana_m3u():
    s = current(force=True)
    if not s.get("ok"):
        return Response("#EXTM3U\n", status=503, mimetype="audio/x-mpegurl")
    body = (
        '#EXTM3U\n'
        '#EXTINF:-1 tvg-id="youtube.kana_tube_iptv" tvg-name="かなチューブ IPTV" '
        'group-title="今日の開催場",かなチューブ IPTV【LIVE】\n'
        + s["play_url"] + "\n"
    )
    return Response(body, mimetype="audio/x-mpegurl")

if __name__ == "__main__":
    current(force=True)
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
