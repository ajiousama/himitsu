#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

CHANNELS = {
    "town_news24": "hc_town_news_24",
    "machicam24": "hc_machi_cam_24",
    "event_selection": "hc_eventsel_channel",
    "ehime_channel": "hc_ehime_channel",
    "bousai": "hc_bousai_channel",
    "igo_shogi": "hc_gosho_channel",
    "ainan": "hc_ainan_live_cam",
}

BASE = "https://cdn.e-catv.ne.jp/mpeg-dash/"
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
KEEP_SEGMENTS = 18


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _children(node, name: str):
    return [x for x in list(node) if _local(x.tag) == name]


def _first(node, name: str):
    for x in list(node):
        if _local(x.tag) == name:
            return x
    return None


def _fetch_xml(source: str):
    mpd_url = f"{BASE}{source}/dash.mpd"
    req = urllib.request.Request(
        mpd_url,
        headers={
            "User-Agent": UA,
            "Accept": "application/dash+xml,application/xml,text/xml,*/*",
            "Cache-Control": "no-cache",
        },
    )
    with urllib.request.urlopen(req, timeout=8) as r:
        data = r.read()
    root = ET.fromstring(data)
    base_node = _first(root, "BaseURL")
    base = urllib.parse.urljoin(mpd_url, (base_node.text or "").strip()) if base_node is not None else mpd_url.rsplit("/", 1)[0] + "/"
    return root, base, mpd_url


def _timeline(st):
    scale = max(1, int(st.attrib.get("timescale", "1")))
    tl = _first(st, "SegmentTimeline")
    if tl is None:
        return []
    out = []
    cur = None
    for s in _children(tl, "S"):
        if "t" in s.attrib:
            cur = int(s.attrib["t"])
        d = int(s.attrib.get("d", "0"))
        r = int(s.attrib.get("r", "0"))
        if cur is None or d <= 0:
            continue
        if r < 0:
            r = 0
        r = min(r, 1000)
        for _ in range(r + 1):
            out.append((cur, d, scale))
            cur += d
    return out


def _track(aset, base: str):
    rep = _first(aset, "Representation")
    st = _first(aset, "SegmentTemplate")
    if rep is None or st is None:
        return None
    repid = rep.attrib.get("id", "")
    media = st.attrib.get("media", "")
    init = st.attrib.get("initialization", "")
    if not repid or not media or not init:
        return None

    all_segments = _timeline(st)
    if not all_segments:
        return None
    start_index = max(0, len(all_segments) - KEEP_SEGMENTS)
    chosen = all_segments[start_index:]
    start_number = int(st.attrib.get("startNumber", "1"))
    uses_number = "$Number$" in media
    uses_time = "$Time$" in media

    segments = []
    for pos, (t, d, scale) in enumerate(chosen, start=start_index):
        name = media.replace("$RepresentationID$", repid)
        if uses_time:
            name = name.replace("$Time$", str(t))
        if uses_number:
            name = name.replace("$Number$", str(start_number + pos))
        segments.append({"url": urllib.parse.urljoin(base, name), "duration": d / scale, "t": t, "d": d})

    if uses_number:
        sequence = start_number + start_index
    else:
        t, d, _ = chosen[0]
        sequence = max(0, t // d)

    init_name = init.replace("$RepresentationID$", repid)
    return {
        "rep": dict(rep.attrib),
        "init": urllib.parse.urljoin(base, init_name),
        "segments": segments,
        "sequence": sequence,
    }


def load_channel(source: str):
    root, base, mpd_url = _fetch_xml(source)
    period = _first(root, "Period")
    if period is None:
        raise RuntimeError("Period not found")

    video = None
    audio = None
    for aset in _children(period, "AdaptationSet"):
        rep = _first(aset, "Representation")
        ctype = (aset.attrib.get("contentType") or "").lower()
        mime = ((rep.attrib.get("mimeType") if rep is not None else "") or aset.attrib.get("mimeType") or "").lower()
        track = _track(aset, base)
        if track is None:
            continue
        if video is None and (ctype == "video" or mime.startswith("video/")):
            video = track
        if audio is None and (ctype == "audio" or mime.startswith("audio/")):
            audio = track

    if video is None:
        raise RuntimeError("video track not found")
    return {"video": video, "audio": audio, "mpd": mpd_url}


def media_playlist(track) -> bytes:
    target = max(3, math.ceil(max(x["duration"] for x in track["segments"])))
    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:7",
        f"#EXT-X-TARGETDURATION:{target}",
        f"#EXT-X-MEDIA-SEQUENCE:{track['sequence']}",
        f'#EXT-X-MAP:URI="{track["init"]}"',
    ]
    for seg in track["segments"]:
        lines.append(f'#EXTINF:{seg["duration"]:.6f},')
        lines.append(seg["url"])
    return ("\n".join(lines) + "\n").encode()


def master_playlist(video, audio, channel: str) -> bytes:
    vr = video["rep"]
    ar = audio["rep"] if audio else {}
    vbw = int(vr.get("bandwidth", "4000000"))
    abw = int(ar.get("bandwidth", "0"))
    width = vr.get("width", "1920")
    height = vr.get("height", "1080")
    vcodec = vr.get("codecs", "avc1.640028")
    acodec = ar.get("codecs", "mp4a.40.2")
    q = urllib.parse.quote(channel, safe="")
    lines = ["#EXTM3U", "#EXT-X-VERSION:7", "#EXT-X-INDEPENDENT-SEGMENTS"]
    if audio:
        lines.append(f'#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aud",NAME="stereo",DEFAULT=YES,AUTOSELECT=YES,URI="?ch={q}&kind=audio"')
        lines.append(f'#EXT-X-STREAM-INF:BANDWIDTH={vbw + abw},RESOLUTION={width}x{height},CODECS="{vcodec},{acodec}",AUDIO="aud"')
    else:
        lines.append(f'#EXT-X-STREAM-INF:BANDWIDTH={vbw},RESOLUTION={width}x{height},CODECS="{vcodec}"')
    lines.append(f"?ch={q}&kind=video")
    return ("\n".join(lines) + "\n").encode()


def _select_channel(raw: str):
    key = (raw or "").strip()
    if key in CHANNELS:
        return key, CHANNELS[key]
    if key in CHANNELS.values():
        for alias, source in CHANNELS.items():
            if source == key:
                return alias, source
    return None


def _channel_from_path(path: str):
    m = re.fullmatch(r"/ehime-catv/([A-Za-z0-9_]+)\.m3u8", path)
    return m.group(1) if m else ""


def handle_request(handler) -> bool:
    parsed = urllib.parse.urlsplit(handler.path)
    if parsed.path != "/ehime-catv.m3u8" and not parsed.path.startswith("/ehime-catv/"):
        return False

    qs = urllib.parse.parse_qs(parsed.query)
    raw = (qs.get("ch") or qs.get("channel") or [_channel_from_path(parsed.path)])[0]
    selected = _select_channel(raw)
    if not selected:
        body = ("unknown channel; use: " + ",".join(CHANNELS) + "\n").encode()
        handler.send_bytes(400, body, "text/plain; charset=utf-8")
        return True

    alias, source = selected
    try:
        data = load_channel(source)
        if (qs.get("debug") or [""])[0] == "1":
            obj = {
                "ok": True,
                "channel": alias,
                "source": source,
                "mpd": data["mpd"],
                "video": {"rep": data["video"]["rep"], "segments": len(data["video"]["segments"]), "sequence": data["video"]["sequence"]},
                "audio": ({"rep": data["audio"]["rep"], "segments": len(data["audio"]["segments"]), "sequence": data["audio"]["sequence"]} if data["audio"] else None),
            }
            handler.send_bytes(200, (json.dumps(obj, ensure_ascii=False) + "\n").encode(), "application/json; charset=utf-8")
            return True

        kind = (qs.get("kind") or ["master"])[0].lower()
        if kind == "video":
            body = media_playlist(data["video"])
        elif kind == "audio":
            if not data["audio"]:
                handler.send_bytes(404, b"#EXTM3U\n# audio track not found\n", "application/vnd.apple.mpegurl; charset=utf-8")
                return True
            body = media_playlist(data["audio"])
        else:
            body = master_playlist(data["video"], data["audio"], alias)
        handler.send_bytes(200, body, "application/vnd.apple.mpegurl; charset=utf-8")
    except Exception as e:
        msg = re.sub(r"[\r\n]+", " ", f"{type(e).__name__}: {e}")
        handler.send_bytes(502, (f"#EXTM3U\n# Ehime CATV gateway error: {msg}\n").encode(), "application/vnd.apple.mpegurl; charset=utf-8")
    return True


def handle_head(handler) -> bool:
    path = urllib.parse.urlsplit(handler.path).path
    if path != "/ehime-catv.m3u8" and not path.startswith("/ehime-catv/"):
        return False
    handler.send_response(200)
    handler.send_header("Content-Type", "application/vnd.apple.mpegurl; charset=utf-8")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.end_headers()
    return True
