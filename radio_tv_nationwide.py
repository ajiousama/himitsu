#!/usr/bin/env python3
from __future__ import annotations

import collections
import hashlib
import json
import os
import re
import secrets
import select
import subprocess
import threading
import time
import urllib.parse
import urllib.request

import radiko_proxy_core as core
import radio_tv as base

# Keep the working ABC/Osaka/Ehime definitions, but allow every station ID
# returned by the existing Radiko Premium nationwide station list.
# NHK-FM Matsuyama intentionally remains the existing direct feed.
REGION_LABELS = {
    "北海道": "HOKKAIDO",
    "東北": "TOHOKU",
    "関東": "KANTO",
    "甲信越": "KOSHINETSU",
    "東海": "TOKAI",
    "近畿": "KINKI",
    "中国": "CHUGOKU",
    "四国": "SHIKOKU",
    "九州沖縄": "KYUSHU / OKINAWA",
}
SID_RE = re.compile(r"^[A-Za-z0-9_-]{2,32}$")
PUBLIC_RADIKO_BASE = os.environ.get("RADIO_AUDIO_BASE", "https://himitsu-six.vercel.app").rstrip("/")


def _accent(sid: str) -> tuple[int, int, int]:
    d = hashlib.sha256(sid.encode("utf-8")).digest()
    return (70 + d[0] % 150, 55 + d[1] % 135, 65 + d[2] % 145)


class NationwideStations(dict):
    def __init__(self, initial):
        super().__init__(initial)
        self._nationwide = {}
        self._nationwide_at = 0.0

    def _refresh(self, force: bool = False):
        now = time.time()
        if not force and self._nationwide and now - self._nationwide_at < 6 * 3600:
            return
        url = f"{PUBLIC_RADIKO_BASE}/api/radiko?list=1"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            payload = json.loads(r.read().decode("utf-8", "replace"))
        stations = payload.get("stations") or {}
        if not isinstance(stations, dict) or len(stations) < 80:
            raise RuntimeError(
                f"radiko station discovery too small: {len(stations) if isinstance(stations, dict) else 0}"
            )
        self._nationwide = stations
        self._nationwide_at = now

    def _dynamic(self, sid: str):
        if not isinstance(sid, str) or not SID_RE.fullmatch(sid):
            raise KeyError(sid)
        self._refresh()
        meta = self._nationwide.get(sid)
        if not meta:
            raise KeyError(sid)
        region = REGION_LABELS.get(str(meta.get("region") or ""), "JAPAN")
        # Use the exact station ID in text so cards remain readable even on a
        # runtime that lacks Japanese fonts; the central Radiko logo supplies
        # the station branding/name.
        return (sid, f"RADIKO / {region}", _accent(sid), sid, None)

    def __contains__(self, key):
        if dict.__contains__(self, key):
            return True
        try:
            self._dynamic(key)
            return True
        except Exception:
            return False

    def __getitem__(self, key):
        try:
            return dict.__getitem__(self, key)
        except KeyError:
            return self._dynamic(key)


_initial = dict(base.STATIONS)
# NHK R1 Matsuyama exists on Radiko as JOZK, so it can use the same
# image+audio mux route as the other nationwide stations.
_initial["nhk_r1_matsuyama"] = (
    "NHK RADIO 1 MATSUYAMA",
    "RADIKO / SHIKOKU",
    (210, 34, 34),
    "JOZK",
    None,
)
# Keep this direct feed exactly as requested because Radiko has no local
# NHK-FM Matsuyama station ID.
_initial["nhk_fm_matsuyama"] = (
    "NHK FM MATSUYAMA",
    "FM MATSUYAMA",
    (54, 138, 57),
    None,
    "https://simul2.drdi.st.nhk/live/17/joined/master.m3u8",
)

base.STATIONS = NationwideStations(_initial)


# Playback hot path: do not enumerate all 47 Radiko areas before tuning one
# known station. The stream XML itself is enough to validate the station ID.
def _fast_latest_master(sid: str, refresh: bool = False):
    if not SID_RE.fullmatch(str(sid or "")):
        raise RuntimeError(f"invalid Radiko station: {sid}")
    errors = []
    for create_url in core.stream_create_urls(sid):
        for typ in ("c", "b"):
            q = urllib.parse.urlencode(
                {
                    "station_id": sid,
                    "l": 15,
                    "lsid": hashlib.md5(secrets.token_bytes(16)).hexdigest(),
                    "type": typ,
                }
            )
            url = create_url + ("&" if "?" in create_url else "?") + q
            try:
                with core.fetch_with_auth(url, refresh) as r:
                    text = r.read().decode("utf-8", "replace")
                if "#EXTM3U" in text:
                    return url, text
                errors.append(f"{typ}:not-m3u8")
            except Exception as e:
                errors.append(f"{typ}:{type(e).__name__}:{getattr(e, 'code', '')}")
    if not refresh:
        return _fast_latest_master(sid, True)
    raise RuntimeError(f"no playable area-free m3u8 for {sid}: " + ",".join(errors[-8:]))


core.latest_master = _fast_latest_master

def _audio_sources(station: str) -> list[str]:
    _display, _freq, _accent_value, radiko_sid, fixed = base.STATIONS[station]
    if fixed:
        return [fixed]
    sid = urllib.parse.quote(radiko_sid, safe="")
    # Render's internal Radiko gateway can return OUT/502 from its cloud region.
    # The Vercel gateway is already verified live, so give FFmpeg the full
    # startup budget on that single source instead of losing 10 seconds locally.
    return [f"{PUBLIC_RADIKO_BASE}/api/radiko?station={sid}&stage=media"]


def _audio_url(station: str) -> str:
    return _audio_sources(station)[0]


def _ffmpeg_cmd(station: str, src: str | None = None) -> list[str]:
    art = base.make_art(station)
    source = src or _audio_url(station)
    return [
        base.ffmpeg_exe(),
        "-nostdin",
        "-hide_banner", "-loglevel", "warning",
        "-re", "-loop", "1", "-framerate", "1", "-i", str(art),
        "-rw_timeout", "12000000",
        "-user_agent", "Mozilla/5.0",
        # Tune directly to the newest Radiko fragment and emit the first TS
        # packets quickly.  IPTV clients give up on a silent GET after roughly
        # ten seconds, so a full HLS probe is too expensive here.
        "-fflags", "nobuffer",
        "-flags", "low_delay",
        "-live_start_index", "-1",
        "-probesize", "32768",
        "-analyzeduration", "200000",
        "-i", source,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "ultrafast", "-tune", "stillimage",
        "-crf", "31", "-pix_fmt", "yuv420p", "-r", "1", "-g", "2",
        # Radiko is already AAC. MPEG-TS accepts it directly, and copying it
        # avoids an unnecessary transcode on Render's small instance.
        "-c:a", "copy",
        "-muxdelay", "0", "-muxpreload", "0", "-flush_packets", "1",
        "-max_delay", "0",
        "-mpegts_flags", "resend_headers",
        "-f", "mpegts", "pipe:1",
    ]


def _drain_stderr(pipe, tail):
    try:
        while True:
            chunk = pipe.readline()
            if not chunk:
                break
            tail.append(chunk)
    except Exception:
        pass


def _start_attempt(station: str, source: str, timeout: float):
    proc = subprocess.Popen(
        _ffmpeg_cmd(station, source),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
    tail = collections.deque(maxlen=120)
    threading.Thread(target=_drain_stderr, args=(proc.stderr, tail), daemon=True).start()

    ready, _, _ = select.select([proc.stdout], [], [], timeout)
    if not ready:
        base._stop_proc(proc)
        detail = b"".join(tail).decode("utf-8", "replace").strip()
        return None, b"", detail or "startup timeout"

    # One small aligned TS burst is enough to prove FFmpeg is ready. Waiting
    # for 64 KiB delayed the HTTP 200 response by another five seconds and
    # caused stricter IPTV clients to declare the channel unplayable.
    first = proc.stdout.read(188 * 7)
    if not first:
        base._stop_proc(proc)
        detail = b"".join(tail).decode("utf-8", "replace").strip()
        return None, b"", detail or "ffmpeg exited without producing MPEG-TS"
    return proc, first, ""


def _stream_station(handler, station: str):
    if station not in base.STATIONS:
        handler.send_error(404, "unknown radio station")
        return

    try:
        sources = _audio_sources(station)
        base.make_art(station)
        base.ffmpeg_exe()
    except Exception as e:
        handler.send_error(500, f"ffmpeg setup failed: {type(e).__name__}: {e}")
        return

    failures = []
    winner = None
    first = b""
    # One verified source gets the complete cold-start budget.
    budgets = [18.0]

    for source, timeout in zip(sources, budgets):
        proc, data, detail = _start_attempt(station, source, timeout)
        if proc is not None and data:
            winner = proc
            first = data
            break
        failures.append(f"{source}: {detail[-1200:]}")

    if winner is None:
        detail = " | ".join(failures)[-3000:] or "radio transcoder failed"
        handler.send_error(504, detail)
        return

    handler.send_response(200)
    handler.send_header("Content-Type", "video/mp2t")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Connection", "close")
    handler.end_headers()
    handler.close_connection = True
    try:
        handler.wfile.write(first)
        handler.wfile.flush()
        while True:
            chunk = winner.stdout.read(64 * 1024)
            if not chunk:
                break
            handler.wfile.write(chunk)
            handler.wfile.flush()
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass
    finally:
        base._stop_proc(winner)


# Patch the original request handler's globals. debug_station also benefits
# because it resolves these functions at call time.
base.audio_url = _audio_url
base.ffmpeg_cmd = _ffmpeg_cmd
base.stream_station = _stream_station

# Re-export the working request handler. All of radio_tv.py's existing art,
# debug, and routing logic now uses the resilient local-first playback path.
handle_request = base.handle_request
