import datetime as dt
import json
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from flask import Flask, Response, jsonify, request

app = Flask(__name__)

CHANNEL_LIVE = os.environ.get("KANA_CHANNEL_LIVE", "https://www.youtube.com/@kana_tube/live")
DEFAULT_VIDEO_ID = os.environ.get("KANA_VIDEO_ID", "DAmfaJ-bGeg").strip()
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36"
CACHE_SECONDS = int(os.environ.get("CACHE_SECONDS", "90"))
KANA_IPTV_RAW = "https://raw.githubusercontent.com/ajiousama/himitsu/main/youtube/output/kana_iptv.m3u"
KANA_WATCH_RAW = "https://raw.githubusercontent.com/ajiousama/himitsu/main/youtube/output/kana.m3u"
KANA_STATE_RAW = "https://raw.githubusercontent.com/ajiousama/himitsu/main/youtube/state/kana.json"
PUBLIC_BASE = "https://kana-iptv-fresh-production.up.railway.app"
PROXY_ALLOWED_SUFFIXES = (
    "chocolatemoo53.com",
    "youtube.com",
    "youtube-nocookie.com",
    "googlevideo.com",
    "googleusercontent.com",
    "raw.githubusercontent.com",
)

_lock = threading.Lock()
_cache = {
    "checked": 0,
    "ok": False,
    "mode": None,
    "video_id": DEFAULT_VIDEO_ID,
    "error": "not_checked",
}


def _run(cmd, timeout=35):
    try:
        p = subprocess.run(cmd, text=True, capture_output=True, timeout=timeout)
        return p.returncode, p.stdout, p.stderr
    except Exception as e:
        return 999, "", repr(e)


def _fetch(url, limit=262144, method="GET", data=None, headers=None):
    hdr = {
        "User-Agent": UA,
        "Accept": "application/vnd.apple.mpegurl,application/x-mpegURL,text/plain,*/*",
        "Accept-Language": "en-US,en;q=0.9",
    }
    if headers:
        hdr.update(headers)
    req = urllib.request.Request(url, headers=hdr, data=data, method=method)
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status, r.geturl(), r.read(limit).decode("utf-8", "replace")


def _proxy_allowed(url):
    try:
        p = urllib.parse.urlparse(url)
    except Exception:
        return False
    if p.scheme not in ("http", "https") or p.username or p.password:
        return False
    host = (p.hostname or "").lower().rstrip(".")
    if not host:
        return False
    return any(host == suffix or host.endswith("." + suffix) for suffix in PROXY_ALLOWED_SUFFIXES)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _proxy_fetch(url, range_header=None, limit=32_000_000):
    if not _proxy_allowed(url):
        raise ValueError("upstream host not allowed")

    opener = urllib.request.build_opener(_NoRedirect)
    current = url
    for _ in range(6):
        headers = {
            "User-Agent": UA,
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
        if range_header:
            headers["Range"] = range_header
        req = urllib.request.Request(current, headers=headers)
        try:
            resp = opener.open(req, timeout=20)
            final = resp.geturl()
            if not _proxy_allowed(final):
                resp.close()
                raise ValueError("redirect target not allowed")
            body = resp.read(limit + 1)
            if len(body) > limit:
                resp.close()
                raise ValueError("upstream body too large")
            hdrs = dict(resp.headers.items())
            status = getattr(resp, "status", 200)
            resp.close()
            return status, final, hdrs, body
        except urllib.error.HTTPError as e:
            if e.code in (301, 302, 303, 307, 308):
                loc = e.headers.get("Location")
                if not loc:
                    raise
                nxt = urllib.parse.urljoin(current, loc)
                if not _proxy_allowed(nxt):
                    np = urllib.parse.urlparse(nxt)
                    raise ValueError(
                        "redirect target not allowed host="
                        + str(np.hostname)
                        + " url="
                        + nxt[:500]
                    )
                current = nxt
                continue
            raise
    raise ValueError("too many redirects")


def _invidious_origin():
    src = _current_iptv_source()
    p = urllib.parse.urlparse(src)
    if not p.scheme or not p.netloc:
        raise RuntimeError("invalid Kana IPTV source origin")
    return p.scheme + "://" + p.netloc


def _path_videoplayback_to_query(p):
    """Convert YouTube's HLS path-form /videoplayback/key/value/... URL
    into the query-form expected by Invidious/ytproxy-go.
    """
    pairs = []
    prefix = "/videoplayback/"
    if p.path.startswith(prefix):
        parts = p.path[len(prefix):].split("/")
        # HLS live segment URLs encode parameters as alternating key/value path parts.
        for i in range(0, len(parts) - 1, 2):
            key = urllib.parse.unquote(parts[i])
            val = urllib.parse.unquote(parts[i + 1])
            if key:
                pairs.append((key, val))

    # Preserve any real query parameters already present.
    pairs.extend(urllib.parse.parse_qsl(p.query, keep_blank_values=True))
    return pairs


def _route_upstream(url):
    """Route YouTube HLS through the Invidious instance that minted it.

    Invidious HLS children can contain path-form YouTube /videoplayback URLs.
    ytproxy-go only exposes GET /videoplayback?..., so normalize those path
    parameters back into a query string and attach the original YouTube host.
    """
    p = urllib.parse.urlparse(url)
    host = (p.hostname or "").lower()

    if host == "youtube.com" or host.endswith(".youtube.com"):
        origin = _invidious_origin()

        if p.path.startswith("/api/manifest/hls_playlist/"):
            return origin + p.path + (("?" + p.query) if p.query else "")

        if p.path == "/videoplayback" or p.path.startswith("/videoplayback/"):
            pairs = _path_videoplayback_to_query(p)
            if not any(k == "host" for k, _ in pairs):
                pairs.append(("host", host))
            query = urllib.parse.urlencode(pairs, doseq=True)
            return origin + "/videoplayback?" + query

    return url


def _proxy_url(url):
    return PUBLIC_BASE + "/hls-proxy?url=" + urllib.parse.quote(url, safe="")


def _rewrite_hls(text, base_url):
    out = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            out.append(raw)
            continue
        if line.startswith("#"):
            def repl(m):
                absolute = urllib.parse.urljoin(base_url, m.group(1))
                return 'URI="' + _proxy_url(absolute) + '"'
            out.append(re.sub(r'URI="([^"]+)"', repl, raw))
            continue
        absolute = urllib.parse.urljoin(base_url, line)
        out.append(_proxy_url(absolute))
    return "\n".join(out) + "\n"


_source_guard = threading.Lock()
_source_cache = {"checked": 0, "url": None, "video_id": None}


def _valid_current_source(url, video_id):
    if not _proxy_allowed(url):
        return False
    path = urllib.parse.unquote(urllib.parse.urlparse(url).path)
    low = path.lower()
    if "/force_finished/1" in low or "/playlist_type/clean" in low:
        return False
    expires = re.search(r"/expire/(\d+)", path)
    if expires and int(expires.group(1)) < time.time() + 900:
        return False
    source_id = re.search(r"/id/([a-z0-9_-]{11})(?:[./]|$)", path, re.I)
    if video_id and source_id and source_id.group(1) != video_id:
        return False
    return bool(source_id or ".m3u8" in path)


def _fresh_invidious_hls(video_id):
    if not video_id:
        return None
    for base in ("https://yt.chocolatemoo53.com", "https://eu.yt.chocolatemoo53.com"):
        try:
            status, _, content = _fetch(base + "/api/v1/videos/" + video_id, 350000)
            if status != 200:
                continue
            data = json.loads(content)
            if data.get("liveNow") is False or data.get("isLive") is False:
                # A finished replay must never be mistaken for a DAY/MID live.
                if not (data.get("liveNow") is True or data.get("isLive") is True):
                    continue
            url = data.get("hlsUrl") or data.get("hls")
            if not isinstance(url, str) or not _valid_current_source(url, video_id):
                continue
            ok, manifest = _probe_hls(url)
            if ok and _master_has_video(manifest) and _master_has_audio(manifest):
                print("KANA_9X_REFRESHED_LIVE " + video_id + " via " + base, flush=True)
                return url
        except Exception as ex:
            print("KANA_9X_REFRESH_ERROR " + base + " " + type(ex).__name__, flush=True)
    return None


def _current_iptv_source():
    """Choose today's active DAY/MID HLS; avoid stale IP-bound playlist URLs.

    Cache briefly so each media segment does not refetch GitHub/channel metadata.
    """
    now = time.time()
    with _source_guard:
        if _source_cache["url"] and now - _source_cache["checked"] < 60:
            return _source_cache["url"]

        notes = []
        latest_video_id, discovery = _discover_video_id(notes)
        source = None
        try:
            raw_url = KANA_IPTV_RAW + "?t=" + str(int(now))
            status, _, _, body = _proxy_fetch(raw_url, limit=1000000)
            if status == 200:
                urls = [line.strip() for line in body.decode("utf-8", "replace").splitlines()
                        if line.strip().startswith(("http://", "https://"))]
                if urls and _valid_current_source(urls[-1], latest_video_id):
                    source = urls[-1]
        except Exception as ex:
            print("KANA_9X_PLAYLIST_ERROR " + type(ex).__name__, flush=True)

        if not source:
            source = _fresh_invidious_hls(latest_video_id)
        if not source:
            raise RuntimeError("no current DAY/MID live HLS (source expired, mismatched, or unreachable)")
        _source_cache.update({"checked": now, "url": source, "video_id": latest_video_id})
        return source


def _video_id_from_url(text):
    patterns = [
        r"[?&]v=([A-Za-z0-9_-]{11})",
        r"/live/([A-Za-z0-9_-]{11})",
        r"/embed/([A-Za-z0-9_-]{11})",
    ]
    for pat in patterns:
        m = re.search(pat, text or "")
        if m:
            return m.group(1)
    return None


def _live_video_id_from_html(html):
    """Return a video ID only when the channel page marks it as live now."""
    text = html or ""
    patterns = [
        r'"videoId":"([A-Za-z0-9_-]{11})".{0,5000}"isLiveNow":true',
        r'"isLiveNow":true.{0,5000}"videoId":"([A-Za-z0-9_-]{11})"',
        r'"videoId":"([A-Za-z0-9_-]{11})".{0,5000}"style":"BADGE_STYLE_TYPE_LIVE_NOW"',
        r'"style":"BADGE_STYLE_TYPE_LIVE_NOW".{0,5000}"videoId":"([A-Za-z0-9_-]{11})"',
    ]
    for pat in patterns:
        m = re.search(pat, text, re.S)
        if m:
            return m.group(1)
    return None


def _published_watch_video_id(notes):
    """Use the currently published DAY/MID watch ID instead of a dated fallback."""
    try:
        url = KANA_WATCH_RAW + "?t=" + str(int(time.time()))
        status, _, body = _fetch(url, 40000)
        match = re.search(r"watch\?v=([A-Za-z0-9_-]{11})", body)
        if status == 200 and match:
            notes.append("latest_watch_id:" + match.group(1))
            return match.group(1)
    except Exception as exc:
        notes.append("latest_watch_error:" + type(exc).__name__)
    return None


def _started_reservation_video_id(notes, now=None):
    """Read the canonical manager's scheduled IDs; do not guess live status.

    Only an already-started reservation may beat a stale published watch.
    The HLS resolver still has to establish usable playback independently.
    """
    if now is None:
        now = int(time.time())
    try:
        status, _, body = _fetch(KANA_STATE_RAW + "?t=" + str(now), 100000)
        if status != 200:
            return None
        data = json.loads(body)
        candidates = []
        for row in data.get("reservations") or []:
            if not isinstance(row, dict):
                continue
            vid = row.get("video_id")
            if not isinstance(vid, str) or not re.fullmatch(r"[A-Za-z0-9_-]{11}", vid):
                continue
            try:
                start = int(row.get("start_timestamp") or 0)
            except (TypeError, ValueError):
                continue
            if start and now - 6 * 3600 <= start <= now:
                candidates.append((start, vid))
        if candidates:
            start, vid = max(candidates)
            notes.append("started_reservation:" + vid)
            return vid
    except Exception as exc:
        notes.append("reservation_error:" + type(exc).__name__)
    return None


def _discover_video_id(notes):
    try:
        status, final_url, html = _fetch(CHANNEL_LIVE, 2_000_000)
        notes.append(f"discover:{status}:{final_url[:100]}")
        vid = _video_id_from_url(final_url)
        if vid:
            return vid, "channel-live-redirect"

        # Prefer a canonical watch URL from the live page.
        m = re.search(
            r'<link[^>]+rel="canonical"[^>]+href="https://www\.youtube\.com/watch\?v=([A-Za-z0-9_-]{11})"',
            html,
            re.I,
        )
        if m:
            return m.group(1), "channel-live-canonical"

        vid = _live_video_id_from_html(html)
        if vid:
            return vid, "channel-live-now"
    except Exception as e:
        notes.append("discover_error:" + type(e).__name__ + ":" + str(e)[:120])

    reserved = _started_reservation_video_id(notes)
    if reserved:
        return reserved, "scheduled-reservation"

    published = _published_watch_video_id(notes)
    if published:
        return published, "published-current-watch"
    return DEFAULT_VIDEO_ID, "fallback-default"


def _watch_urls(video_id):
    watch = "https://www.youtube.com/watch?v=" + video_id
    embed = "https://www.youtube.com/embed/" + video_id + "?autoplay=1"
    nocookie = "https://www.youtube-nocookie.com/embed/" + video_id + "?autoplay=1"
    return watch, embed, nocookie


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


def _master_has_video(body):
    if "#EXTM3U" not in body:
        return False
    # A YouTube master/variant containing video advertises stream variants and
    # normally a resolution/codecs attribute. Do not accept an audio media list.
    return "#EXT-X-STREAM-INF" in body and (
        "RESOLUTION=" in body or "avc1" in body.lower() or "vp09" in body.lower() or "av01" in body.lower()
    )


def _master_has_audio(body):
    # Audio can be a separate rendition or muxed inside each variant.
    if '#EXT-X-MEDIA:TYPE=AUDIO' in body:
        return True
    lowered = body.lower()
    return "mp4a" in lowered or "opus" in lowered or "audio=" in lowered


def _decode_json_string(raw):
    try:
        return json.loads('"' + raw + '"')
    except Exception:
        return raw.replace("\/", "/")


def _extract_hls_urls_from_html(html, source):
    out = []
    for m in re.finditer(r'"hlsManifestUrl"\s*:\s*"([^"]+)"', html or ""):
        url = _decode_json_string(m.group(1))
        if _is_hls_url(url) and all(x["url"] != url for x in out):
            out.append({"url": url, "source": source + ":hlsManifestUrl"})
    return out


def _ytcfg_string(html, key):
    for pat in (
        rf'"{re.escape(key)}"\s*:\s*"([^"]+)"',
        rf'{re.escape(key)}\s*[:=]\s*"([^"]+)"',
    ):
        m = re.search(pat, html or "")
        if m:
            return _decode_json_string(m.group(1))
    return None


def _ytcfg_number(html, key):
    m = re.search(rf'"{re.escape(key)}"\s*:\s*(\d+)', html or "")
    return int(m.group(1)) if m else None


def _innertube_player(video_id, embed_url, embed_html, notes):
    api_key = _ytcfg_string(embed_html, "INNERTUBE_API_KEY")
    client_version = _ytcfg_string(embed_html, "INNERTUBE_CLIENT_VERSION")
    client_name_num = _ytcfg_number(embed_html, "INNERTUBE_CONTEXT_CLIENT_NAME")
    visitor = _ytcfg_string(embed_html, "VISITOR_DATA")

    if not api_key or not client_version:
        notes.append("innertube:missing_config")
        return None

    payload = {
        "context": {
            "client": {
                "clientName": "WEB_EMBEDDED_PLAYER",
                "clientVersion": client_version,
                "hl": "en",
                "gl": "US",
                "clientScreen": "EMBED",
            },
            "thirdParty": {"embedUrl": "https://www.youtube.com/"},
        },
        "videoId": video_id,
        "playbackContext": {
            "contentPlaybackContext": {
                "html5Preference": "HTML5_PREF_WANTS",
            }
        },
        "contentCheckOk": True,
        "racyCheckOk": True,
    }
    headers = {
        "Content-Type": "application/json",
        "Origin": "https://www.youtube.com",
        "Referer": embed_url,
        "X-Youtube-Client-Version": client_version,
    }
    if client_name_num:
        headers["X-Youtube-Client-Name"] = str(client_name_num)
    if visitor:
        headers["X-Goog-Visitor-Id"] = visitor

    try:
        status, _, text = _fetch(
            "https://www.youtube.com/youtubei/v1/player?prettyPrint=false&key=" + urllib.parse.quote(api_key),
            2_000_000,
            method="POST",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
        )
        data = json.loads(text)
        ps = data.get("playabilityStatus") or {}
        notes.append(
            "innertube:"
            + str(status)
            + ":"
            + str(ps.get("status"))
            + ":"
            + str(ps.get("reason") or "")[:100]
        )
        return data
    except Exception as e:
        notes.append("innertube_error:" + type(e).__name__ + ":" + str(e)[:120])
        return None


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
        "source": fmt.get("_source"),
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
    codec_pref = 3 if vcodec.startswith(("avc", "h264")) else 2 if vcodec.startswith("vp09") else 1
    height = int(fmt.get("height") or 0)
    # Fire TV/VLC stability: prefer 1080p or below.
    capped = height if 1 <= height <= 1080 else 0
    return (codec_pref, capped, int(fmt.get("fps") or 0), float(fmt.get("tbr") or 0))


def _score_audio(fmt):
    acodec = str(fmt.get("acodec") or "")
    codec_pref = 3 if acodec.startswith(("mp4a", "aac")) else 2 if acodec.startswith("opus") else 1
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
    master_candidates = []

    video_id, discovery_source = _discover_video_id(notes)
    watch, embed, nocookie = _watch_urls(video_id)
    notes.append("video_id:" + video_id + ":" + discovery_source)

    embed_html = None
    for page_url, page_label in ((watch, "page"), (embed, "embed"), (nocookie, "embed-nocookie")):
        try:
            status, _, html = _fetch(page_url, 2_000_000)
            notes.append(f"{page_label}:{status}:{len(html)}")
            master_candidates.extend(_extract_hls_urls_from_html(html, page_label))
            if page_label == "embed":
                embed_html = html
        except Exception as e:
            notes.append(page_label + "_error:" + type(e).__name__ + ":" + str(e)[:80])

    # Direct Innertube player route: independent of yt-dlp's live-status parsing.
    if embed_html:
        data = _innertube_player(video_id, embed, embed_html, notes)
        if isinstance(data, dict):
            sd = data.get("streamingData") or {}
            hls = sd.get("hlsManifestUrl")
            if _is_hls_url(hls):
                master_candidates.append({"url": hls, "source": "innertube:hlsManifestUrl"})

    # Prefer an official master HLS. This is the bugfix for the former itag=233
    # mistake: never descend to the first audio-only media playlist and call it success.
    seen_master = set()
    for cand in master_candidates:
        url = cand["url"]
        if url in seen_master:
            continue
        seen_master.add(url)
        ok, body = _probe_hls(url)
        if ok and _master_has_video(body):
            # Official YouTube master may use muxed variants or separate audio renditions.
            return {
                "checked": int(time.time()),
                "ok": True,
                "mode": "official-master",
                "video_id": video_id,
                "watch_url": watch,
                "play_url": url,
                "master_text": None,
                "source": cand["source"],
                "has_audio_rendition": _master_has_audio(body),
                "candidate_count": len(master_candidates),
                "notes": notes[-28:],
            }

    # Separate extractor implementation, kept as fallback only.
    rc, out, err = _run(["streamlink", "--stream-url", watch, "best"], 35)
    notes.append(f"streamlink:{rc}:{err[-180:]}")

    # Fresh yt-dlp fallback. No old manager.py and no is_live gate.
    clients = [None, "android_vr", "web_embedded", "tv", "web_safari", "mweb"]
    seen_urls = set()
    for client in clients:
        label = client or "default"
        extra = [] if not client else ["--extractor-args", "youtube:player_client=" + client]
        rc, out, err = _run([
            "yt-dlp", "--no-playlist", "--ignore-no-formats-error",
            "--js-runtimes", "node", *extra, "--dump-single-json", watch
        ], 45)
        notes.append(f"ytdlp-json:{label}:{rc}:{err[-260:]}")
        if not out.strip():
            continue
        try:
            data = json.loads(out)
        except Exception as e:
            notes.append("json_error:" + label + ":" + type(e).__name__)
            continue

        # yt-dlp's top-level hls_manifest_url is a master candidate. Prefer it.
        for key in ("hls_manifest_url", "hlsManifestUrl"):
            hls = data.get(key)
            if _is_hls_url(hls) and hls not in seen_master:
                seen_master.add(hls)
                ok, body = _probe_hls(hls)
                if ok and _master_has_video(body):
                    return {
                        "checked": int(time.time()),
                        "ok": True,
                        "mode": "official-master-ytdlp",
                        "video_id": video_id,
                        "watch_url": watch,
                        "play_url": hls,
                        "master_text": None,
                        "source": "yt-dlp:" + label + ":" + key,
                        "has_audio_rendition": _master_has_audio(body),
                        "candidate_count": len(master_candidates),
                        "notes": notes[-28:],
                    }

        for fmt in _hls_formats_from_data(data, label):
            if fmt["url"] in seen_urls:
                continue
            seen_urls.add(fmt["url"])
            formats.append(fmt)

    muxed = [f for f in formats if _codec_ok(f.get("vcodec")) and _codec_ok(f.get("acodec"))]
    videos = [f for f in formats if _codec_ok(f.get("vcodec")) and not _codec_ok(f.get("acodec"))]
    audios = [f for f in formats if not _codec_ok(f.get("vcodec")) and _codec_ok(f.get("acodec"))]

    # Accept a true muxed HLS only after its manifest is verified.
    for fmt in sorted(muxed, key=_score_video, reverse=True):
        ok, body = _probe_hls(fmt["url"])
        if ok:
            return {
                "checked": int(time.time()),
                "ok": True,
                "mode": "muxed",
                "video_id": video_id,
                "watch_url": watch,
                "play_url": fmt["url"],
                "master_text": None,
                "source": fmt.get("_source"),
                "format": _fmt_summary(fmt),
                "notes": notes[-28:],
            }

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
            "checked": int(time.time()),
            "ok": True,
            "mode": "synthetic-av-master",
            "video_id": video_id,
            "watch_url": watch,
            "play_url": "/master.m3u8",
            "master_text": master,
            "source": f'{valid_video.get("_source")}+{valid_audio.get("_source")}',
            "video_format": _fmt_summary(valid_video),
            "audio_format": _fmt_summary(valid_audio),
            "format_count": len(formats),
            "notes": notes[-28:],
        }

    return {
        "checked": int(time.time()),
        "ok": False,
        "mode": None,
        "video_id": video_id,
        "watch_url": watch,
        "play_url": None,
        "master_text": None,
        "source": None,
        "error": "no_verified_av_hls",
        "format_count": len(formats),
        "video_candidates": [_fmt_summary(x) for x in sorted(videos, key=_score_video, reverse=True)[:6]],
        "audio_candidates": [_fmt_summary(x) for x in sorted(audios, key=_score_audio, reverse=True)[:6]],
        "notes": notes[-28:],
    }


def current(force=False):
    global _cache
    now = time.time()
    with _lock:
        if not force and _cache.get("checked") and now - _cache["checked"] < CACHE_SECONDS:
            return _cache
        previous = _cache
        latest = _resolve()
        if latest.get("ok"):
            _cache = latest
        elif (
            previous.get("ok")
            and previous.get("mode") == "muxed"
            and previous.get("video_id") == latest.get("video_id")
            and _valid_current_source(previous.get("play_url"), latest.get("video_id"))
        ):
            # A transient YouTube 429/BOT_CHECK must not destroy a still-live
            # muxed stream obtained earlier from this same Railway instance.
            valid, _ = _probe_hls(previous["play_url"])
            if valid:
                _cache = dict(previous, checked=int(now),
                              revalidated_at=int(now),
                              transient_resolver_error=latest.get("error"))
            else:
                _cache = latest
        else:
            _cache = latest
        return _cache


@app.after_request
def add_cors_headers(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET,HEAD,OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Range,Content-Type,Accept"
    resp.headers["Access-Control-Expose-Headers"] = "Content-Length,Content-Range,Accept-Ranges,Content-Type"
    resp.headers["Cross-Origin-Resource-Policy"] = "cross-origin"
    return resp


@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "kana-iptv-fresh", "player9x_proxy": True})


@app.get("/kana-9x.m3u8")
def kana_9x():
    # Use the original LIVE muxed H.264/AAC itag-96 format when Railway can
    # resolve it from its own egress IP. This avoids fragile split renditions
    # and makes both audio and video available to IPTV players in one playlist.
    try:
        resolved = current(force=False)
        muxed = resolved.get("play_url") if resolved.get("ok") and resolved.get("mode") == "muxed" else None
        if muxed and _proxy_allowed(muxed):
            status, final, headers, body = _proxy_fetch(muxed, limit=2_000_000)
            manifest = body.decode("utf-8", "replace")
            if status == 200 and "#EXTM3U" in manifest[:8192]:
                print("KANA_9X_MUXED " + str(resolved.get("video_id")) + " " + str(resolved.get("format",{}).get("format_id")), flush=True)
                return Response(
                    _rewrite_hls(manifest, final),
                    status=200,
                    mimetype="application/vnd.apple.mpegurl",
                    headers={"Cache-Control": "no-store"},
                )
    except Exception as exc:
        print("KANA_9X_MUXED_ERROR " + type(exc).__name__ + " " + str(exc)[:150], flush=True)

    # Only then fall back to an independently renewed Invidious A/V master.
    try:
        src = _current_iptv_source()
        status, final, headers, body = _proxy_fetch(src, limit=2_000_000)
        text = body.decode("utf-8", "replace")
        if status != 200 or "#EXTM3U" not in text[:8192]:
            return Response("#EXTM3U\n", status=502, mimetype="application/vnd.apple.mpegurl")
        rewritten = _rewrite_hls(text, final)
        return Response(
            rewritten,
            status=200,
            mimetype="application/vnd.apple.mpegurl",
            headers={"Cache-Control": "no-store"},
        )
    except Exception as e:
        print("KANA_9X_ERROR " + repr(e), flush=True)
        return Response("#EXTM3U\n", status=502, mimetype="application/vnd.apple.mpegurl")


@app.route("/hls-proxy", methods=["GET", "HEAD", "OPTIONS"])
def hls_proxy():
    if request.method == "OPTIONS":
        return Response("", status=204)

    target = (request.args.get("url") or "").strip()
    if not _proxy_allowed(target):
        try:
            print(
                "HLS_PROXY_REJECT "
                + json.dumps({
                    "target": target[:500],
                    "host": urllib.parse.urlparse(target).hostname if target else None,
                    "raw_query": request.query_string.decode("utf-8", "replace")[:700],
                }, ensure_ascii=False),
                flush=True,
            )
        except Exception:
            pass
        return Response("bad upstream\n", status=400, mimetype="text/plain")

    try:
        routed = _route_upstream(target)
        status, final, headers, body = _proxy_fetch(
            routed,
            range_header=request.headers.get("Range"),
            limit=32_000_000,
        )
    except urllib.error.HTTPError as e:
        return Response("upstream " + str(e.code) + "\n", status=e.code, mimetype="text/plain")
    except Exception as e:
        print("HLS_PROXY_ERROR " + repr(e), flush=True)
        return Response("proxy error\n", status=502, mimetype="text/plain")

    ctype = (headers.get("Content-Type") or "").lower()
    path = urllib.parse.urlparse(final).path.lower()
    if "mpegurl" in ctype or path.endswith(".m3u8"):
        text = body.decode("utf-8", "replace")
        if "#EXTM3U" not in text[:8192]:
            return Response("invalid hls\n", status=502, mimetype="text/plain")
        return Response(
            _rewrite_hls(text, final),
            status=status,
            mimetype="application/vnd.apple.mpegurl",
            headers={"Cache-Control": "no-store"},
        )

    resp = Response(body if request.method != "HEAD" else b"", status=status)
    if headers.get("Content-Type"):
        resp.headers["Content-Type"] = headers["Content-Type"]
    if headers.get("Content-Range"):
        resp.headers["Content-Range"] = headers["Content-Range"]
    if headers.get("Accept-Ranges"):
        resp.headers["Accept-Ranges"] = headers["Accept-Ranges"]
    if headers.get("Content-Length") and request.method == "HEAD":
        resp.headers["Content-Length"] = headers["Content-Length"]
    resp.headers["Cache-Control"] = headers.get("Cache-Control") or "public,max-age=3"
    return resp


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

    if s.get("mode") == "synthetic-av-master":
        return Response(s["master_text"], mimetype="application/vnd.apple.mpegurl")

    ok, body = _probe_hls(s["play_url"])
    if not ok:
        s = current(force=True)
        if not s.get("ok"):
            return Response("#EXTM3U\n", status=503, mimetype="application/vnd.apple.mpegurl")
        if s.get("mode") == "synthetic-av-master":
            return Response(s["master_text"], mimetype="application/vnd.apple.mpegurl")
        ok, body = _probe_hls(s["play_url"])
        if not ok:
            return Response("#EXTM3U\n", status=503, mimetype="application/vnd.apple.mpegurl")

    return Response(body, mimetype="application/vnd.apple.mpegurl")


@app.get("/raw")
def raw():
    s = current(force=True)
    if not s.get("ok"):
        return Response("NO_VERIFIED_AV_HLS\n", status=503, mimetype="text/plain")
    if s.get("mode") == "synthetic-av-master":
        return Response("/master.m3u8\n", mimetype="text/plain")
    return Response(s["play_url"] + "\n", mimetype="text/plain")


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


def _seconds_until_jst(hour, minute):
    tz = dt.timezone(dt.timedelta(hours=9))
    now = dt.datetime.now(tz)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += dt.timedelta(days=1)
    return max(1, int((target - now).total_seconds()))


def _twice_daily_refresh_loop():
    # User requirement: obtain a fresh HLS at least twice per day.
    # Two fixed acquisition windows in JST, plus on-demand stale refreshes above.
    schedule = [(13, 5), (20, 40)]
    while True:
        waits = [(_seconds_until_jst(h, m), h, m) for h, m in schedule]
        wait_s, hour, minute = min(waits, key=lambda x: x[0])
        time.sleep(wait_s)
        try:
            result = current(force=True)
            safe = {k: v for k, v in result.items() if k != "master_text"}
            print(
                "KANA_FRESH_TWICE_DAILY "
                + f"{hour:02d}:{minute:02d} JST "
                + json.dumps(safe, ensure_ascii=False),
                flush=True,
            )
        except Exception as e:
            print("KANA_FRESH_TWICE_DAILY_ERROR " + repr(e), flush=True)
        time.sleep(65)


def _warm_9x_proxy():
    try:
        src = _current_iptv_source()
        status, final, headers, body = _proxy_fetch(src, limit=2_000_000)
        text = body.decode("utf-8", "replace")
        rewritten = _rewrite_hls(text, final) if status == 200 and "#EXTM3U" in text[:8192] else ""

        raw_child_urls = []
        raw_children = []
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            if line.startswith("#"):
                for m in re.finditer(r'URI=["\']([^"\']+)["\']', line):
                    absu = urllib.parse.urljoin(final, m.group(1))
                    raw_child_urls.append(absu)
                    raw_children.append({
                        "host": urllib.parse.urlparse(absu).hostname,
                        "url": absu[:220],
                    })
            else:
                absu = urllib.parse.urljoin(final, line)
                raw_child_urls.append(absu)
                raw_children.append({
                    "host": urllib.parse.urlparse(absu).hostname,
                    "url": absu[:220],
                })

        child_result = None
        segment_result = None

        if raw_child_urls:
            child_target = raw_child_urls[0]
            child_host = urllib.parse.urlparse(child_target).hostname
            child_allowed = _proxy_allowed(child_target)
            if child_allowed:
                try:
                    routed_child = _route_upstream(child_target)
                    cs, cf, ch, cb = _proxy_fetch(routed_child, limit=2_000_000)
                    ctext = cb.decode("utf-8", "replace")
                    child_hls = "#EXTM3U" in ctext[:8192]
                    child_result = {
                        "host": child_host,
                        "allowed": True,
                        "routed_host": urllib.parse.urlparse(routed_child).hostname,
                        "status": cs,
                        "hls": child_hls,
                        "bytes": len(cb),
                    }

                    if child_hls:
                        segment_url = None
                        for cline_raw in ctext.splitlines():
                            cline = cline_raw.strip()
                            if cline and not cline.startswith("#"):
                                segment_url = urllib.parse.urljoin(cf, cline)
                                break
                        if segment_url:
                            routed_segment = _route_upstream(segment_url)
                            try:
                                ss, sf, sh, sb = _proxy_fetch(routed_segment, limit=4_000_000)
                                ctype = sh.get("Content-Type") or ""
                                preview = ""
                                if "text/" in ctype.lower() or len(sb) < 1024:
                                    preview = sb[:500].decode("utf-8", "replace")
                                media_ok = (
                                    ss in (200, 206)
                                    and len(sb) > 1024
                                    and "text/plain" not in ctype.lower()
                                    and "text/html" not in ctype.lower()
                                )
                                segment_result = {
                                    "host": urllib.parse.urlparse(segment_url).hostname,
                                    "routed_host": urllib.parse.urlparse(routed_segment).hostname,
                                    "status": ss,
                                    "bytes": len(sb),
                                    "content_type": ctype,
                                    "media_ok": media_ok,
                                    "preview": preview,
                                }
                            except Exception as se:
                                segment_result = {
                                    "host": urllib.parse.urlparse(segment_url).hostname,
                                    "routed_host": urllib.parse.urlparse(routed_segment).hostname,
                                    "error": repr(se)[:220],
                                }
                except Exception as ce:
                    child_result = {
                        "host": child_host,
                        "allowed": True,
                        "error": repr(ce)[:220],
                    }
            else:
                child_result = {
                    "host": child_host,
                    "allowed": False,
                }

        ok = bool(
            rewritten
            and "/hls-proxy?url=" in rewritten
            and child_result
            and child_result.get("status") == 200
            and child_result.get("hls")
            and segment_result
            and segment_result.get("media_ok") is True
        )

        print(
            "KANA_9X_WARM "
            + json.dumps({
                "ok": ok,
                "status": status,
                "source_host": urllib.parse.urlparse(src).hostname,
                "bytes": len(rewritten),
                "raw_children": raw_children[:8],
                "child": child_result,
                "segment": segment_result,
            }, ensure_ascii=False),
            flush=True,
        )
    except Exception as e:
        print("KANA_9X_WARM_ERROR " + repr(e), flush=True)


threading.Thread(target=_warm_resolver, daemon=True).start()
threading.Thread(target=_warm_9x_proxy, daemon=True).start()
threading.Thread(target=_twice_daily_refresh_loop, daemon=True).start()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
