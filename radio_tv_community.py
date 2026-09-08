#!/usr/bin/env python3
from __future__ import annotations

import html
import io
import re
import threading
import time
import urllib.request

# Community FM stations are intentionally kept outside the Radiko nationwide
# catalogue.  They use each station's public Internet simulcast and then feed
# the exact same Render image+audio MPEG-TS mux used by the existing radios.
COMMUNITY_STATIONS = {
    "FMOTOKUNI": ("FM OTOKUNI", "FM 86.2 MHz", (67, 139, 90), "FMOTOKUNI", None),
    "FM845": ("FM845", "FM 84.5 MHz", (185, 53, 86), "FM845", None),
    "BARIBARI": ("FM RADIO BARIBARI", "FM 78.9 MHz", (35, 113, 174), "BARIBARI", None),
}

# Current station artwork exposed on the JCBA station pages.  FMおとくに uses
# a generated badge so playback never depends on an unrelated third-party logo.
COMMUNITY_LOGOS = {
    "FM845": "https://radimo.s3.amazonaws.com/logo/97f3b857175c58d24de8ec54c956dff09aa4c301ab6e20150ff11d2d071f874b.jpg",
    "BARIBARI": "https://radimo.s3.amazonaws.com/logo/7fef6dc58526b7a6d55560ae97dacce850edf946b5cca38e54bd68de387b0e95.jpg",
}

JCBA_RAWPLAYERS = {
    "FM845": "https://www.jcbasimul.com/kyotoribingufm/rawplayer",
    "BARIBARI": "https://www.jcbasimul.com/fmradiobaribari/rawplayer",
}

# Public fallbacks.  The resolver always prefers the current JCBA raw player
# when it exposes a live URL, but these known endpoints keep playback alive if
# the JCBA page markup changes.
STATIC_AUDIO = {
    "FMOTOKUNI": [
        "https://mtist.as.smartstream.ne.jp/30063/livestream/playlist.m3u8",
        "http://mtist.as.smartstream.ne.jp/30063/livestream/playlist.m3u8",
    ],
    "FM845": [
        "https://musicbird-hls.leanstream.co/musicbird/JCB007.stream/playlist.m3u8?args=web_03",
        "http://musicbird-hls.leanstream.co/musicbird/JCB007.stream/playlist.m3u8?args=web_03",
        "mmsh://simuledge.shibapon.net/KyotoLivingFM?MSWMExt=.asf",
    ],
    "BARIBARI": [
        "https://musicbird-hls.leanstream.co/musicbird/JCB076.stream/playlist.m3u8?args=web_03",
        "http://musicbird-hls.leanstream.co/musicbird/JCB076.stream/playlist.m3u8?args=web_03",
    ],
}

_CACHE_LOCK = threading.Lock()
_RESOLVED: dict[str, tuple[float, list[str]]] = {}


def _extract_urls(text: str) -> list[str]:
    # Raw players have used both ordinary URLs and JSON/JS-escaped strings.
    cleaned = html.unescape(text).replace("\\/", "/")
    try:
        cleaned = bytes(cleaned, "utf-8").decode("unicode_escape")
    except Exception:
        pass
    found: list[str] = []
    patterns = [
        r"https?://[^\s\"'<>]+?\.m3u8(?:\?[^\s\"'<>]*)?",
        r"https?://[^\s\"'<>]+?/playlist(?:\.m3u8)?(?:\?[^\s\"'<>]*)?",
    ]
    for pattern in patterns:
        for value in re.findall(pattern, cleaned, flags=re.IGNORECASE):
            value = value.rstrip("),;]")
            if value not in found:
                found.append(value)
    return found


def _resolve_jcba(station: str) -> list[str]:
    page = JCBA_RAWPLAYERS.get(station)
    if not page:
        return []
    now = time.time()
    with _CACHE_LOCK:
        cached = _RESOLVED.get(station)
        if cached and now - cached[0] < 300:
            return list(cached[1])
    urls: list[str] = []
    try:
        req = urllib.request.Request(
            page,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
                "Referer": page.rsplit("/", 1)[0],
            },
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            text = response.read(1024 * 1024).decode("utf-8", "replace")
        urls = _extract_urls(text)
    except Exception as exc:
        print(f"[community-radio] JCBA resolve failed station={station} error={type(exc).__name__}:{exc}", flush=True)
    with _CACHE_LOCK:
        _RESOLVED[station] = (now, list(urls))
    return urls


def install(impl) -> None:
    # radio_tv_nationwide replaces STATIONS with a dict subclass.  Updating it
    # here preserves the complete existing nationwide Radiko behaviour.
    impl.base.STATIONS.update(COMMUNITY_STATIONS)

    previous_fetch_logo = impl.base._fetch_logo
    previous_audio_sources = impl._audio_sources

    def _badge(station: str):
        w, h = 470, 120
        image = impl.base.Image.new("RGBA", (w, h), (255, 255, 255, 245))
        draw = impl.base.ImageDraw.Draw(image)
        font = impl.base._font(38, True)
        label = {
            "FMOTOKUNI": "FM OTOKUNI 86.2",
            "FM845": "FM845 84.5",
            "BARIBARI": "FM BARIBARI 78.9",
        }.get(station, station)
        box = draw.textbbox((0, 0), label, font=font)
        tw, th = box[2] - box[0], box[3] - box[1]
        draw.rounded_rectangle((4, 4, w - 4, h - 4), 18, outline=(38, 48, 58, 255), width=4)
        draw.text(((w - tw) // 2, (h - th) // 2 - box[1]), label, fill=(24, 30, 38, 255), font=font)
        return image

    def _community_logo(station: str):
        url = COMMUNITY_LOGOS.get(station)
        if not url:
            return _badge(station)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=4) as response:
                data = response.read(2 * 1024 * 1024)
            return impl.base.Image.open(io.BytesIO(data)).convert("RGBA")
        except Exception as exc:
            print(f"[community-radio] logo fallback station={station} error={type(exc).__name__}:{exc}", flush=True)
            return _badge(station)

    def _fetch_logo(station_id: str):
        if station_id in COMMUNITY_STATIONS:
            return _community_logo(station_id)
        return previous_fetch_logo(station_id)

    def _audio_sources(station: str) -> list[str]:
        if station not in COMMUNITY_STATIONS:
            return previous_audio_sources(station)
        candidates: list[str] = []
        for url in _resolve_jcba(station):
            if url not in candidates:
                candidates.append(url)
        for url in STATIC_AUDIO.get(station, []):
            if url not in candidates:
                candidates.append(url)
        return candidates

    impl.base._fetch_logo = _fetch_logo
    impl._audio_sources = _audio_sources
