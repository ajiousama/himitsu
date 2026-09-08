#!/usr/bin/env python3
from __future__ import annotations

import io
import json
import threading
import time
import urllib.parse
import urllib.request

import websocket

# Community FM stays outside the Radiko catalogue but feeds the same station-art
# MPEG-TS endpoint used by the existing FreeWiFi radio channels.
COMMUNITY_STATIONS = {
    "FMOTOKUNI": ("FM OTOKUNI", "FM 86.2 MHz", (67, 139, 90), "FMOTOKUNI", None),
    "FM845": ("FM845", "FM 84.5 MHz", (185, 53, 86), "FM845", None),
    "BARIBARI": ("FM RADIO BARIBARI", "FM 78.9 MHz", (35, 113, 174), "BARIBARI", None),
}

COMMUNITY_LOGOS = {
    "FMOTOKUNI": "https://www.simulradio.info/data/161.jpg",
    "FM845": "https://radimo.s3.amazonaws.com/logo/97f3b857175c58d24de8ec54c956dff09aa4c301ab6e20150ff11d2d071f874b.jpg",
    "BARIBARI": "https://radimo.s3.amazonaws.com/logo/7fef6dc58526b7a6d55560ae97dacce850edf946b5cca38e54bd68de387b0e95.jpg",
}

BROWSER_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
    "AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
)

LISTENRADIO = {
    "FMOTOKUNI": {
        "channel_id": "30063",
        "slug": "lr038",
        # Verified current official player source. Keep it only as a fallback
        # when the metadata API itself is temporarily unavailable.
        "fallback": "https://mtist.as.smartstream.ne.jp/30063/livestream/playlist.m3u8",
    }
}

JCBA = {
    "FM845": "kyotoribingufm",
    "BARIBARI": "fmradiobaribari",
}

# JCBA's select_stream is the geo-sensitive step. Resolve that short-lived
# location/token pair from the existing Osaka Vercel function first, then keep
# the WebSocket/audio path on Render. Direct JCBA resolution remains a fallback
# so a Vercel outage never makes the stations worse than before.
JCBA_OSAKA_SELECT = "https://himitsu-six.vercel.app/api/jcba-select"

_CACHE_LOCK = threading.Lock()
_LISTEN_CACHE: dict[str, tuple[float, list[str]]] = {}


def _json_get(url: str, referer: str | None = None, timeout: float = 15.0):
    headers = {
        "User-Agent": BROWSER_UA,
        "Accept": "application/json,*/*",
    }
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def _listenradio_sources(station: str) -> list[str]:
    cfg = LISTENRADIO[station]
    now = time.time()
    with _CACHE_LOCK:
        cached = _LISTEN_CACHE.get(station)
        if cached and now - cached[0] < 300:
            return list(cached[1])

    page = f"https://listenradio.jp/?ch={cfg['slug']}"
    api = (
        "https://listenradio.jp/service/toppage.aspx?"
        + urllib.parse.urlencode({"channelid": cfg["channel_id"], "devtype": "ios"})
    )
    sources: list[str] = []
    try:
        payload = _json_get(api, page)
        hls = str((payload.get("Channel") or {}).get("ChannelHls") or "").strip()
        if hls:
            if hls.startswith("http://"):
                hls = "https://" + hls[len("http://") :]
            sources.append(hls)
    except Exception as exc:
        print(
            f"[community-radio] ListenRadio resolve failed station={station} "
            f"error={type(exc).__name__}:{exc}",
            flush=True,
        )

    fallback = str(cfg.get("fallback") or "").strip()
    if fallback and fallback not in sources:
        sources.append(fallback)
    with _CACHE_LOCK:
        _LISTEN_CACHE[station] = (now, list(sources))
    return sources


def is_jcba_source(source: str) -> bool:
    return str(source).startswith("jcba://")


def ffmpeg_input_options(station: str, source: str) -> list[str]:
    """Options that must appear immediately before the audio input."""
    if station in LISTENRADIO:
        slug = LISTENRADIO[station]["slug"]
        return [
            "-rw_timeout", "10000000",
            "-user_agent", BROWSER_UA,
            "-headers",
            f"Referer: https://listenradio.jp/?ch={slug}\r\n"
            "Origin: https://listenradio.jp\r\n",
            "-thread_queue_size", "128",
            "-fflags", "nobuffer",
            "-flags", "low_delay",
            "-live_start_index", "-1",
            "-probesize", "32768",
            "-analyzeduration", "200000",
        ]
    return []


def _validate_jcba_selection(payload: dict) -> tuple[str, str]:
    location = str(payload.get("location") or "").strip()
    token = str(payload.get("token") or "").strip()
    if not location.startswith("wss://") or not token:
        raise RuntimeError("JCBA select_stream response is missing location/token")
    return location, token


def _select_jcba_direct(station: str) -> tuple[str, str]:
    slug = JCBA[station]
    referer = f"https://www.jcbasimul.com/{slug}/rawplayer"
    query = urllib.parse.urlencode(
        {"station": slug, "channel": "0", "quality": "high", "burst": "5"}
    )
    payload = _json_get(
        "https://www.jcbasimul.com/api/select_stream?" + query,
        referer,
        timeout=12.0,
    )
    if int(payload.get("code") or 0) != 200:
        raise RuntimeError(f"JCBA select_stream returned code={payload.get('code')}")
    return _validate_jcba_selection(payload)


def _select_jcba(station: str) -> tuple[str, str]:
    # First choice: acquire the short-lived JCBA session from Osaka. We verified
    # that a token acquired in kix1 can then feed the official WebSocket from an
    # overseas runner, so only this small control request needs Japanese egress.
    try:
        url = JCBA_OSAKA_SELECT + "?" + urllib.parse.urlencode({"station": station})
        payload = _json_get(url, timeout=12.0)
        if not payload.get("ok") or payload.get("via") != "vercel-kix1":
            raise RuntimeError(
                f"Osaka relay returned ok={payload.get('ok')} via={payload.get('via')}"
            )
        selection = _validate_jcba_selection(payload)
        print(f"[community-radio] JCBA select station={station} via=vercel-kix1", flush=True)
        return selection
    except Exception as exc:
        print(
            f"[community-radio] JCBA Osaka select failed station={station} "
            f"error={type(exc).__name__}:{exc}; fallback=direct",
            flush=True,
        )

    selection = _select_jcba_direct(station)
    print(f"[community-radio] JCBA select station={station} via=direct-fallback", flush=True)
    return selection


def feed_jcba_audio(station: str, sink, stop: threading.Event) -> None:
    """Feed the current official JCBA Ogg/Opus WebSocket into FFmpeg stdin."""
    ws = None
    try:
        location, token = _select_jcba(station)
        ws = websocket.create_connection(
            location,
            subprotocols=["listener.fmplapla.com"],
            origin="https://www.jcbasimul.com",
            header=["User-Agent: " + BROWSER_UA],
            timeout=15,
        )
        ws.send(token)
        while not stop.is_set():
            message = ws.recv()
            if isinstance(message, bytes) and message:
                sink.write(message)
                sink.flush()
    except (BrokenPipeError, OSError):
        pass
    except Exception as exc:
        if not stop.is_set():
            print(
                f"[community-radio] JCBA feed ended station={station} "
                f"error={type(exc).__name__}:{exc}",
                flush=True,
            )
    finally:
        if ws is not None:
            try:
                ws.close()
            except Exception:
                pass
        try:
            sink.close()
        except Exception:
            pass


def install(impl) -> None:
    # radio_tv_nationwide replaces STATIONS with a dict subclass. Updating that
    # object preserves all existing nationwide Radiko behaviour.
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
        draw.rounded_rectangle(
            (4, 4, w - 4, h - 4), 18, outline=(38, 48, 58, 255), width=4
        )
        draw.text(
            ((w - tw) // 2, (h - th) // 2 - box[1]),
            label,
            fill=(24, 30, 38, 255),
            font=font,
        )
        return image

    def _community_logo(station: str):
        url = COMMUNITY_LOGOS.get(station)
        if not url:
            return _badge(station)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": BROWSER_UA})
            with urllib.request.urlopen(req, timeout=4) as response:
                data = response.read(2 * 1024 * 1024)
            return impl.base.Image.open(io.BytesIO(data)).convert("RGBA")
        except Exception as exc:
            print(
                f"[community-radio] logo fallback station={station} "
                f"error={type(exc).__name__}:{exc}",
                flush=True,
            )
            return _badge(station)

    def _fetch_logo(station_id: str):
        if station_id in COMMUNITY_STATIONS:
            return _community_logo(station_id)
        return previous_fetch_logo(station_id)

    def _audio_sources(station: str) -> list[str]:
        if station in LISTENRADIO:
            return _listenradio_sources(station)
        if station in JCBA:
            return [f"jcba://{station}"]
        return previous_audio_sources(station)

    impl.base._fetch_logo = _fetch_logo
    impl._audio_sources = _audio_sources
