#!/usr/bin/env python3
from __future__ import annotations

import base64
import os
import re
import time

# Render exposes its HTTP port through PORT. Configure the existing Radiko
# gateway before importing it so module-level HOST/PORT use cloud values.
os.environ.setdefault("RADIKO_PROXY_HOST", "0.0.0.0")
os.environ.setdefault("RADIKO_PROXY_PORT", os.environ.get("PORT", "10000"))

import radiko_proxy_core as core


def cloud_auth(force: bool = False):
    """Current 2026 Radiko auth flow for api.radiko.jp.

    Premium state must be carried into auth2 with X-Radiko-Session. The old
    radiko_session query parameter no longer preserves the Premium session on
    the api.radiko.jp subdomain.
    """
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


core.auth = cloud_auth
core.BUILD = "20260829-render-session-header-v2"

if __name__ == "__main__":
    core.main()
