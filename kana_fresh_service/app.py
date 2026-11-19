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
EMBED = "https://www.youtube.com/embed/" + VIDEO_ID + "?autoplay=1"
EMBED_NOCOOKIE = "https://www.youtube-nocookie.com/embed/" + VIDEO_ID + "?autoplay=1"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36"
CACHE_SECONDS = int(os.environ.get("CACHE_SECONDS", "90"))
_lock = threading.Lock()
_cache = {"checked": 0, "ok": False, "mode": None, "error": "not_checked"}

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

def _is_hls_url(url):
    return isinstance(url, str) and url.startswith("http") and (
        "manifest.googlevideo.com/" in url or ".m3u8" in url
    )

def _probe_hls(url):
    try:
        status, _, body = _fetch(url)
        return status == 200 and "#EXTM3U" in body[:4096], body
    except Exception:
        return False, ""

def _codec_ok(value):
    return bool(value) and str(value).lower() not in ("none", "unknown", "null")

def _fmt_summary(fmt):
    return {
        "format_id": fmt.get("format_id"),
        "vcodec": fmt.get("vcodec"),
        "acodec": fmt.get("acodec"),
        "height": fmt.get("height"),
        "width": fmt.get("width"),
        "fps": fmt.get("fps"),
        "tbr": fmt.get("tbr"),
        "abr": fmt.get("abr"),
        "protocol": fmt.get("protocol"),
    }

def _hls_formats_from_data(data, source):
    out = []
    for fmt in data.get("formats") or []:
        url = fmt.get("url")
        proto = str(fmt.get("protocol") or "").lower()
        if not ("m3u8" in proto or _is_hls_url(url)):
            continue
        if not _is_hls_url(url):
            continue
        item = dict(fmt)
        item["_source"] = source
        out.append(item)
    return out

def _score_video(fmt):
    vcodec = str(fmt.get("vcodec") or "")
    # Prefer broadly compatible H.264/AVC, then resolution/fps/bitrate.
    codec_pref = 2 if vcodec.startswith(("avc", "h264")) else 1
    height = int(fmt.get("height") or 0)
    # Avoid choosing extreme resolutions for IPTV stability; prefer <=1080p.
    capped = height if height <= 1080 else 0
    return (codec_pref, capped, int(fmt.get("fps") or 0), float(fmt.get("tbr") or 0))

def _score_audio(fmt):
    acodec = str(fmt.get("acodec") or "")
    codec_pref = 2 if acodec.startswith(("mp4a", "aac")) else 1
    return (codec_pref, float(fmt.get("abr") or fmt.get("tbr") or 0))

def _build_master(video, audio):
    vurl = video["url"]
    aurl = audio["url"]
    width = int(video.get("width") or 1280)
    height = int(video.get("height") or 720)
    fps = float(video.get("fps") or 30)
    vbw = int(float(video.get("tbr") or 2500) * 1000)
    abw = int(float(audio.get("abr") or audio.get("tbr") or 128) * 1000)
    bandwidth = max(256000, vbw + abw)
    vcodec = str(video.get("vcodec") or "avc1.4d401f").split(",")[0]
    acodec = str(audio.get("acodec") or "mp4a.40.2").split(",")[0]
    return (
        "#EXTM3U\n"
        "#EXT-X-VERSION:4\n"
        "#EXT-X-INDEPENDENT-SEGMENTS\n"
        '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="Default",DEFAULT=YES,AUTOSELECT=YES,'
        f'URI="{aurl}"\n'
        f'#EXT-X-STREAM-INF:BANDWIDTH={bandwidth},RESOLUTION={width}x{height},'
        f'FRAME-RATE={fps:.3f},CODECS="{vcodec},{acodec}",AUDIO="audio"\n'
        f"{vurl}\n"
    )

def _resolve():
    notes = []
    formats = []

    # Check pages only as diagnostics. Actual output below is built from fresh format JSON.
    for page_url, page_label in ((WATCH, "page"), (EMBED, "embed"), (EMBED_NOCOOKIE, "embed-nocookie")):
        try:
            status, _, html = _fetch(page_url, 2_000_000)
            notes.append(f"{page_label}:{status}:{len(html)}")
        except Exception as e:
            notes.append(page_label + "_error:" + type(e).__name__)

    rc, out, err = _run(["streamlink", "--stream-url", WATCH, "best"], 35)
    notes.append(f"streamlink:{rc}:{err[-180:]}")

    clients = [None, "android_vr", "web_embedded", "tv", "web_safari", "mweb"]
    seen_urls = set()
    for client in clients:
        label = client or "default"
        extra = [] if not client else ["--extractor-args", "youtube:player_client=" + client]
        rc, out, err = _run([
            "yt-dlp", "--no-playlist", "--ignore-no-formats-error",
            "--js-runtimes", "node", *extra, "--dump-single-json", WATCH
        ], 45)
        notes.append(f"ytdlp-json:{label}:{rc}:{err[-260:]}")
        if not out.strip():
            continue
        try:
            data = json.loads(out)
        except Exception as e:
            notes.append("json_error:" + label + ":" + type(e).__name__)
            continue
        for fmt in _hls_formats_from_data(data, label):
            if fmt["url"] in seen_urls:
                continue
            seen_urls.add(fmt["url"])
            formats.append(fmt)

    muxed = [
        f for f in formats
        if _codec_ok(f.get("vcodec")) and _codec_ok(f.get("acodec"))
    ]
    videos = [
        f for f in formats
        if _codec_ok(f.get("vcodec")) and not _codec_ok(f.get("acodec"))
    ]
    audios = [
        f for f in formats
        if not _codec_ok(f.get("vcodec")) and _codec_ok(f.get("acodec"))
    ]

    now = int(time.time())

    # First choice: a true muxed HLS stream, if YouTube exposes one.
    for fmt in sorted(muxed, key=_score_video, reverse=True):
        ok, _ = _probe_hls(fmt["url"])
        if ok:
            m = re.search(r"/expire/(\d+)", fmt["url"])
            return {
                "checked": now,
                "ok": True,
                "mode": "muxed",
                "play_url": fmt["url"],
                "master_text": None,
                "source": fmt.get("_source"),
                "format": _fmt_summary(fmt),
                "expire_epoch": int(m.group(1)) if m else None,
                "format_count": len(formats),
                "notes": notes[-24:],
            }

    # Current YouTube Live often exposes demuxed HLS: video-only + audio-only.
    valid_video = None
    valid_audio = None

    for fmt in sorted(videos, key=_score_video, reverse=True):
        ok, _ = _probe_hls(fmt["url"])
        if ok:
            valid_video = fmt
            break

    for fmt in sorted(audios, key=_score_audio, reverse=True):
        ok, _ = _probe_hls(fmt["url"])
        if ok:
            valid_audio = fmt
            break

    if valid_video and valid_audio:
        master = _build_master(valid_video, valid_audio)
        return {
            "checked": now,
            "ok": True,
            "mode": "synthetic-av-master",
            "play_url": "/master.m3u8",
            "master_text": master,
            "source": f'{valid_video.get("_source")}+{valid_audio.get("_source")}',
            "video_format": _fmt_summary(valid_video),
            "audio_format": _fmt_summary(valid_audio),
            "format_count": len(formats),
            "notes": notes[-24:],
        }

    return {
        "checked": now,
        "ok": False,
        "mode": None,
        "play_url": None,
        "master_text": None,
        "source": None,
        "error": "no_verified_av_hls",
        "format_count": len(formats),
        "video_candidates": [_fmt_summary(x) for x in sorted(videos, key=_score_video, reverse=True)[:6]],
        "audio_candidates": [_fmt_summary(x) for x in sorted(audios, key=_score_audio, reverse=True)[:6]],
        "notes": notes[-24:],
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
    s = current(force=True)
    public = {k: v for k, v in s.items() if k != "master_text"}
    return jsonify(public)

@app.get("/master.m3u8")
def master():
    s = current(force=False)
    if not s.get("ok"):
        return Response("#EXTM3U\n", status=503, mimetype="application/vnd.apple.mpegurl")
    if s.get("mode") == "muxed":
        # Redirect-free proxy manifest: return the upstream manifest body itself.
        ok, body = _probe_hls(s["play_url"])
        if not ok:
            s = current(force=True)
            if not s.get("ok"):
                return Response("#EXTM3U\n", status=503, mimetype="application/vnd.apple.mpegurl")
            if s.get("mode") != "muxed":
                return Response(s["master_text"], mimetype="application/vnd.apple.mpegurl")
            ok, body = _probe_hls(s["play_url"])
        return Response(body, mimetype="application/vnd.apple.mpegurl")
    return Response(s["master_text"], mimetype="application/vnd.apple.mpegurl")

@app.get("/raw")
def raw():
    s = current(force=True)
    if not s.get("ok"):
        return Response("NO_VERIFIED_AV_HLS\n", status=503, mimetype="text/plain")
    if s.get("mode") == "muxed":
        return Response(s["play_url"] + "\n", mimetype="text/plain")
    return Response("/master.m3u8\n", mimetype="text/plain")

@app.get("/kana.m3u")
def kana_m3u():
    s = current(force=False)
    if not s.get("ok"):
        return Response("#EXTM3U\n", status=503, mimetype="audio/x-mpegurl")
    body = (
        '#EXTM3U\n'
        '#EXTINF:-1 tvg-id="youtube.kana_tube_iptv" tvg-name="かなチューブ IPTV" '
        'group-title="今日の開催場",かなチューブ IPTV【LIVE】\n'
        '/master.m3u8\n'
    )
    return Response(body, mimetype="audio/x-mpegurl")

def _warm_resolver():
    try:
        result = current(force=True)
        safe = {k: v for k, v in result.items() if k != "master_text"}
        print("KANA_FRESH_WARM " + json.dumps(safe, ensure_ascii=False), flush=True)
    except Exception as e:
        print("KANA_FRESH_WARM_ERROR " + repr(e), flush=True)

threading.Thread(target=_warm_resolver, daemon=True).start()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
