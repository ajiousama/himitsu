#!/usr/bin/env python3
from __future__ import annotations

import base64
import fcntl
import os
import re
import struct
import time
import urllib.parse

# Render exposes its HTTP port through PORT. Configure the existing Radiko
# gateway before importing it so module-level HOST/PORT use cloud values.
os.environ.setdefault("RADIKO_PROXY_HOST", "0.0.0.0")
os.environ.setdefault("RADIKO_PROXY_PORT", os.environ.get("PORT", "10000"))

import radiko_proxy_core as core

# Radio TV is optional. A missing Pillow/ffmpeg dependency must never
# take down the existing Radiko gateway during Render startup.
RADIO_TV_IMPORT_ERROR = None
try:
    import radio_tv_filemux as radio_tv
except Exception as e:
    radio_tv = None
    RADIO_TV_IMPORT_ERROR = f"{type(e).__name__}: {e}"
    print(f"[radio-tv] disabled at startup: {RADIO_TV_IMPORT_ERROR}", flush=True)

# BOAT resolver is isolated from Radiko. If it fails to import, Radiko stays up.
BOAT_IMPORT_ERROR = None
try:
    import boat_cloud_resolver as boat_cloud
except Exception as e:
    boat_cloud = None
    BOAT_IMPORT_ERROR = f"{type(e).__name__}: {e}"
    print(f"[boat] disabled at startup: {BOAT_IMPORT_ERROR}", flush=True)


def cloud_auth(force: bool = False):
    """Current 2026 Radiko auth flow for api.radiko.jp."""
    now = time.time()
    with core.LOCK:
        if not force and core.STATE["token"] and now - core.STATE["token_time"] < 2100:
            return core.STATE["token"], core.STATE["detected_area"]

    session = core.premium_login(force=force)

    try:
        with core.open_url(core.API + "/v2/api/auth1", core.BASE_HEADERS, timeout=30) as r:
            token = r.headers.get("X-Radiko-AuthToken")
            off = r.headers.get("X-Radiko-KeyOffset")
            length = r.headers.get("X-Radiko-KeyLength")
    except Exception as e:
        raise RuntimeError(f"auth1 failed: {type(e).__name__}: {e}") from e

    if not token or off is None or length is None:
        raise RuntimeError("auth1 failed: required response headers are missing")

    off = int(off)
    length = int(length)
    part = core.AUTH_KEY[off : off + length]
    if len(part) != length:
        raise RuntimeError("auth1 failed: partial-key range is invalid")

    headers = dict(core.BASE_HEADERS)
    headers.update(
        {
            "X-Radiko-AuthToken": token,
            "X-Radiko-PartialKey": base64.b64encode(part).decode(),
            "X-Radiko-Session": session,
        }
    )

    try:
        with core.open_url(core.API + "/v2/api/auth2", headers, timeout=30) as r:
            body = r.read().decode("utf-8", "replace").strip()
    except Exception as e:
        raise RuntimeError(f"auth2 failed: {type(e).__name__}: {e}") from e

    if not body or body == "OUT":
        raise RuntimeError(
            "auth2 returned OUT after X-Radiko-Session; cloud egress is likely outside Radiko Japan service area"
        )

    detected = body.split(",", 1)[0].strip()
    if not re.fullmatch(r"JP\d{1,2}", detected):
        raise RuntimeError(f"auth2 returned invalid area: {body[:80]}")

    with core.LOCK:
        core.STATE["token"] = token
        core.STATE["token_time"] = now
        core.STATE["detected_area"] = detected

    print(f"[radiko] cloud auth OK detected={detected} mode=premium-session-header", flush=True)
    return token, detected


def tun_capability_report() -> str:
    path = "/dev/net/tun"
    lines = [f"tun_exists={os.path.exists(path)}"]
    if not os.path.exists(path):
        lines.append("tun_create=false")
        lines.append("reason=no_/dev/net/tun")
        return "\n".join(lines) + "\n"

    fd = None
    try:
        fd = os.open(path, os.O_RDWR)
        lines.append("tun_open=true")
        # Linux TUNSETIFF, IFF_TUN | IFF_NO_PI. Creating a temporary interface
        # verifies CAP_NET_ADMIN rather than merely checking the device node.
        ifr = struct.pack("16sH", b"rgate%d", 0x0001 | 0x1000)
        result = fcntl.ioctl(fd, 0x400454CA, ifr)
        name = result[:16].split(b"\x00", 1)[0].decode("ascii", "replace")
        lines.append("tun_create=true")
        lines.append(f"interface={name}")
    except Exception as e:
        lines.append("tun_create=false")
        lines.append(f"reason={type(e).__name__}:{e}")
    finally:
        if fd is not None:
            os.close(fd)
    return "\n".join(lines) + "\n"


core.auth = cloud_auth
core.BUILD = "20260903-radio-tv-filemux-v10"

_original_do_get = core.Handler.do_GET


def _cloud_do_get(self):
    path = urllib.parse.urlsplit(self.path).path
    if boat_cloud is not None and boat_cloud.handle_request(self):
        return
    if boat_cloud is None and (path == "/boat" or path.startswith("/boat/")):
        message = f"boat resolver unavailable: {BOAT_IMPORT_ERROR or 'dependency import failed'}\n"
        self.send_bytes(503, message.encode(), "text/plain; charset=utf-8")
        return
    if radio_tv is not None and radio_tv.handle_request(self):
        return
    if radio_tv is None and (
        path.startswith("/radio-tv/")
        or path.startswith("/radio-art/")
        or path.startswith("/radio-debug/")
    ):
        message = f"radio-tv unavailable: {RADIO_TV_IMPORT_ERROR or 'dependency import failed'}\n"
        self.send_bytes(503, message.encode(), "text/plain; charset=utf-8")
        return
    if path == "/vpncheck":
        self.send_bytes(200, tun_capability_report().encode(), "text/plain; charset=utf-8")
        return
    return _original_do_get(self)


core.Handler.do_GET = _cloud_do_get


def _cloud_do_head(self):
    path = urllib.parse.urlsplit(self.path).path
    if path.startswith("/radio-tv/"):
        # HEAD is only a cheap capability probe. Starting FFmpeg in the
        # background here raced with the following GET on cold stations and
        # could leave the real playback request waiting with zero bytes.
        # Let the GET own its mux from start to finish instead.
        self.send_response(200)
        self.send_header("Content-Type", "video/mp2t")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        return
    if path == "/health":
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        return
    self.send_response(405)
    self.send_header("Allow", "GET, HEAD")
    self.end_headers()


core.Handler.do_HEAD = _cloud_do_head

if __name__ == "__main__":
    core.main()