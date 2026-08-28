#!/usr/bin/env python3
from __future__ import annotations

import base64
import concurrent.futures
import hashlib
import hmac
import json
import os
import pathlib
import re
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urljoin

from radiko_epg import build_xmltv

BUILD = "20260829-premium-refresh-v1"
HOST = os.environ.get("RADIKO_PROXY_HOST", "127.0.0.1")
PORT = int(os.environ.get("RADIKO_PROXY_PORT", "9395"))
WEB = "https://radiko.jp"
API = "https://api.radiko.jp"
AUTH_KEY = b"bcd151073c03b352e1ef2fd66c32209da9ca0afa"
SECRET_PATH = pathlib.Path(".radiko_signing_secret")

BASE_HEADERS = {
    "X-Radiko-App": "pc_html5",
    "X-Radiko-App-Version": "0.0.1",
    "X-Radiko-Device": "pc",
    "X-Radiko-User": "dummy_user",
    "User-Agent": "Mozilla/5.0",
}
MEDIA_UA = "Mozilla/5.0"
LOCK = threading.RLock()
STATE = {
    "session": None,
    "session_time": 0.0,
    "token": None,
    "token_time": 0.0,
    "detected_area": "OUT",
    "stations": None,
    "stations_time": 0.0,
    "epg": None,
    "epg_time": 0.0,
}


def open_url(url, headers=None, data=None, timeout=25, method=None):
    req = urllib.request.Request(url, headers=headers or {}, data=data, method=method)
    return urllib.request.urlopen(req, timeout=timeout)


def credentials():
    mail = os.environ.get("RADIKO_MAIL", "").strip()
    password = os.environ.get("RADIKO_PASSWORD", "").strip()
    if not mail or not password:
        raise RuntimeError("RADIKO_MAIL / RADIKO_PASSWORD are required for Premium mode")
    return mail, password


def premium_login(force=False):
    mail, password = credentials()
    now = time.time()
    with LOCK:
        if not force and STATE["session"] and now - STATE["session_time"] < 2400:
            return STATE["session"]

    data = urllib.parse.urlencode({"mail": mail, "pass": password}).encode()
    headers = {"User-Agent": MEDIA_UA, "Content-Type": "application/x-www-form-urlencoded"}
    try:
        with open_url(WEB + "/v4/api/member/login", headers, data, 30, "POST") as r:
            obj = json.loads(r.read().decode("utf-8", "replace"))
    except Exception as e:
        raise RuntimeError(f"Premium login failed: {type(e).__name__}: {e}") from e

    session = str(obj.get("radiko_session") or "").strip()
    areafree = str(obj.get("areafree") or "0") == "1"
    if not session:
        raise RuntimeError("Premium login failed: radiko_session was not returned")
    if not areafree:
        raise RuntimeError("Premium login succeeded but area-free is not enabled")

    with LOCK:
        STATE["session"] = session
        STATE["session_time"] = now
        STATE["token"] = None
        STATE["token_time"] = 0.0
    print("[radiko] Premium area-free login OK", flush=True)
    return session


def auth(force=False):
    now = time.time()
    with LOCK:
        if not force and STATE["token"] and now - STATE["token_time"] < 2100:
            return STATE["token"], STATE["detected_area"]

    session = premium_login(force=force)
    try:
        with open_url(API + "/v2/api/auth1", BASE_HEADERS, timeout=30) as r:
            token = r.headers.get("X-Radiko-AuthToken")
            off = r.headers.get("X-Radiko-KeyOffset")
            length = r.headers.get("X-Radiko-KeyLength")
    except Exception as e:
        raise RuntimeError(f"auth1 failed: {type(e).__name__}: {e}") from e

    if not token or off is None or length is None:
        raise RuntimeError("auth1 failed: required response headers are missing")
    off = int(off)
    length = int(length)
    part = AUTH_KEY[off : off + length]
    if len(part) != length:
        raise RuntimeError("auth1 failed: partial-key range is invalid")

    headers = dict(BASE_HEADERS)
    headers.update(
        {
            "X-Radiko-AuthToken": token,
            "X-Radiko-PartialKey": base64.b64encode(part).decode(),
        }
    )
    url = API + "/v2/api/auth2?radiko_session=" + urllib.parse.quote(session, safe="")
    try:
        with open_url(url, headers, timeout=30) as r:
            body = r.read().decode("utf-8", "replace").strip()
    except Exception as e:
        raise RuntimeError(f"auth2 failed: {type(e).__name__}: {e}") from e

    if not body or body == "OUT":
        raise RuntimeError(f"auth2 returned {body or 'empty response'}")
    detected = body.split(",", 1)[0].strip()
    if not re.fullmatch(r"JP\d{1,2}", detected):
        raise RuntimeError(f"auth2 returned invalid area: {body[:80]}")

    with LOCK:
        STATE["token"] = token
        STATE["token_time"] = now
        STATE["detected_area"] = detected
    print(f"[radiko] auth OK detected={detected} mode=premium", flush=True)
    return token, detected


def media_headers(token):
    # Premium area-free playback deliberately does NOT send X-Radiko-AreaId.
    return {
        "X-Radiko-AuthToken": token,
        "User-Agent": MEDIA_UA,
        "Referer": "https://radiko.jp/",
    }


def region(pref):
    if pref == 1:
        return "北海道"
    if pref <= 7:
        return "東北"
    if pref <= 14:
        return "関東"
    if pref <= 20:
        return "甲信越"
    if pref <= 24:
        return "東海"
    if pref <= 30:
        return "近畿"
    if pref <= 35:
        return "中国"
    if pref <= 39:
        return "四国"
    return "九州沖縄"


def fetch_area(pref):
    area = f"JP{pref}"
    try:
        with open_url(f"{WEB}/v3/station/list/{area}.xml", {"User-Agent": MEDIA_UA}, timeout=12) as r:
            root = ET.fromstring(r.read())
    except Exception:
        return []
    result = []
    for st in root.findall("station"):
        sid = (st.findtext("id") or "").strip()
        if not sid:
            continue
        name = (st.findtext("name") or sid).strip()
        logos = []
        for node in st.findall("logo"):
            if not (node.text or "").strip():
                continue
            try:
                score = int(node.get("width") or 0) * int(node.get("height") or 0)
            except ValueError:
                score = 0
            logos.append((score, node.text.strip()))
        logo = max(logos, default=(0, ""), key=lambda x: x[0])[1]
        result.append((sid, {"name": name, "logo": logo, "pref": pref, "region": region(pref)}))
    return result


def stations(force=False):
    now = time.time()
    with LOCK:
        if not force and STATE["stations"] is not None and now - STATE["stations_time"] < 21600:
            return STATE["stations"]

    by_pref = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        futs = {ex.submit(fetch_area, n): n for n in range(1, 48)}
        for fut in concurrent.futures.as_completed(futs):
            n = futs[fut]
            try:
                by_pref[n] = fut.result()
            except Exception:
                by_pref[n] = []
    result = {}
    for n in range(1, 48):
        for sid, meta in by_pref.get(n, []):
            result.setdefault(sid, meta)
    if len(result) < 100:
        raise RuntimeError(f"station discovery too small: {len(result)}")
    with LOCK:
        STATE["stations"] = result
        STATE["stations_time"] = now
    return result


def stream_create_urls(sid):
    result = []
    for base in (WEB, API):
        try:
            with open_url(f"{base}/v3/station/stream/pc_html5/{sid}.xml", {"User-Agent": MEDIA_UA}, timeout=15) as r:
                root = ET.fromstring(r.read())
        except Exception:
            continue
        for node in root.findall("url"):
            if node.get("areafree") != "1" or node.get("timefree", "0") != "0":
                continue
            p = node.find("playlist_create_url")
            value = (p.text or "").strip() if p is not None else ""
            if value and value not in result:
                result.append(value)
        if result:
            break
    return result


def fetch_with_auth(url, refresh=False):
    token, _ = auth(force=refresh)
    try:
        return open_url(url, media_headers(token), timeout=25)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403) and not refresh:
            return fetch_with_auth(url, True)
        raise


def latest_master(sid, refresh=False):
    if sid not in stations():
        raise RuntimeError(f"unknown Radiko station: {sid}")
    errors = []
    for base in stream_create_urls(sid):
        for typ in ("c", "b"):
            q = urllib.parse.urlencode(
                {
                    "station_id": sid,
                    "l": 15,
                    "lsid": hashlib.md5(secrets.token_bytes(16)).hexdigest(),
                    "type": typ,
                }
            )
            url = base + ("&" if "?" in base else "?") + q
            try:
                with fetch_with_auth(url, refresh) as r:
                    text = r.read().decode("utf-8", "replace")
                if "#EXTM3U" in text:
                    return url, text
                errors.append(f"{typ}:not-m3u8")
            except Exception as e:
                errors.append(f"{typ}:{type(e).__name__}:{getattr(e, 'code', '')}")
    if not refresh:
        return latest_master(sid, True)
    raise RuntimeError(f"no playable area-free m3u8 for {sid}: " + ",".join(errors[-8:]))


def signing_secret():
    env = os.environ.get("RADIKO_SIGNING_SECRET", "").strip()
    if env:
        return env.encode()
    with LOCK:
        if SECRET_PATH.exists():
            value = SECRET_PATH.read_text(encoding="ascii", errors="ignore").strip()
            if value:
                return value.encode()
        value = secrets.token_hex(32)
        SECRET_PATH.write_text(value, encoding="ascii")
        return value.encode()


def signature(sid, upstream):
    msg = (sid + "\n" + upstream).encode()
    return hmac.new(signing_secret(), msg, hashlib.sha256).hexdigest()


def signed_fetch(base, sid, upstream):
    return (
        base
        + "/fetch?sid="
        + urllib.parse.quote(sid, safe="")
        + "&u="
        + urllib.parse.quote(upstream, safe="")
        + "&sig="
        + signature(sid, upstream)
    )


def rewrite_playlist(text, src, base, sid):
    def repl_uri(match):
        quote = match.group(1)
        raw = match.group(2)
        return "URI=" + quote + signed_fetch(base, sid, urljoin(src, raw)) + quote

    out = []
    for line in text.splitlines():
        line = re.sub(r'URI=(["\'])(.*?)(\1)', lambda m: repl_uri(type("M", (), {"group": lambda self, i: {1:m.group(1),2:m.group(2)}[i]})()), line) if False else line
        # Rewrite quoted URI attributes without touching unrelated tag text.
        line = re.sub(
            r'URI="([^"]+)"',
            lambda m: 'URI="' + signed_fetch(base, sid, urljoin(src, m.group(1))) + '"',
            line,
        )
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            line = signed_fetch(base, sid, urljoin(src, stripped))
        out.append(line)
    return "\n".join(out) + "\n"


def epg(force=False):
    now = time.time()
    with LOCK:
        if not force and STATE["epg"] is not None and now - STATE["epg_time"] < 10800:
            return STATE["epg"]
    data = build_xmltv(3)
    with LOCK:
        STATE["epg"] = data
        STATE["epg_time"] = now
    return data


class Handler(BaseHTTPRequestHandler):
    server_version = "RadikoPremiumGateway/1.0"

    def log_message(self, fmt, *args):
        print("[radiko] " + fmt % args, flush=True)

    def send_bytes(self, status, data, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        host = self.headers.get("Host", f"{HOST}:{PORT}")
        proto = self.headers.get("X-Forwarded-Proto", "http")
        base = f"{proto}://{host}"
        try:
            if parsed.path == "/health":
                self.send_bytes(200, ("OK build=" + BUILD + "\n").encode(), "text/plain; charset=utf-8")
                return

            if parsed.path == "/ready":
                token, detected = auth(force=True)
                ss = stations(force=True)
                smoke = "RNB" if "RNB" in ss else next(iter(ss))
                _, master = latest_master(smoke)
                if "#EXTM3U" not in master:
                    raise RuntimeError("live smoke test did not return m3u8")
                body = f"OK mode=premium detected={detected} stations={len(ss)} smoke={smoke} build={BUILD}\n"
                self.send_bytes(200, body.encode(), "text/plain; charset=utf-8")
                return

            if parsed.path == "/epg.xml":
                self.send_bytes(200, epg(), "application/xml; charset=utf-8")
                return

            if parsed.path in ("/", "/playlist.m3u"):
                ss = stations()
                order = {x: i for i, x in enumerate(("北海道", "東北", "関東", "甲信越", "東海", "近畿", "中国", "四国", "九州沖縄"))}
                lines = [f'#EXTM3U url-tvg="{base}/epg.xml"']
                for sid, meta in sorted(ss.items(), key=lambda kv: (order.get(kv[1]["region"], 99), kv[1]["pref"], kv[1]["name"])):
                    group = "短波（ラジオ）" if sid in {"RN1", "RN2"} else meta["region"] + "（ラジオ）"
                    name = meta["name"] if meta["name"].endswith("（ラジオ）") else meta["name"] + "（ラジオ）"
                    lines.append(f'#EXTINF:-1 tvg-id="radiko.{sid}" tvg-logo="{meta["logo"]}" group-title="{group}",{name}')
                    lines.append(base + "/live/" + urllib.parse.quote(sid, safe=""))
                self.send_bytes(200, ("\n".join(lines) + "\n").encode(), "audio/x-mpegurl")
                return

            if parsed.path.startswith("/live/"):
                sid = urllib.parse.unquote(parsed.path.split("/", 2)[2]).strip()
                src, master = latest_master(sid)
                body = rewrite_playlist(master, src, base, sid).encode()
                self.send_bytes(200, body, "application/vnd.apple.mpegurl")
                return

            if parsed.path == "/fetch":
                q = urllib.parse.parse_qs(parsed.query)
                sid = (q.get("sid") or [""])[0]
                upstream = (q.get("u") or [""])[0]
                sig = (q.get("sig") or [""])[0]
                if not sid or not upstream or not sig or not hmac.compare_digest(sig, signature(sid, upstream)):
                    self.send_bytes(403, b"forbidden\n", "text/plain; charset=utf-8")
                    return
                with fetch_with_auth(upstream) as r:
                    data = r.read()
                    content_type = r.headers.get("Content-Type") or "application/octet-stream"
                if ".m3u8" in urllib.parse.urlsplit(upstream).path.lower() or "mpegurl" in content_type.lower() or data.lstrip().startswith(b"#EXTM3U"):
                    text = data.decode("utf-8", "replace")
                    data = rewrite_playlist(text, upstream, base, sid).encode()
                    content_type = "application/vnd.apple.mpegurl"
                self.send_bytes(200, data, content_type)
                return

            self.send_bytes(404, b"not found\n", "text/plain; charset=utf-8")
        except Exception as e:
            msg = f"FAIL {type(e).__name__}: {e}\n"
            print("[radiko] " + msg.strip(), flush=True)
            self.send_bytes(502, msg.encode("utf-8", "replace"), "text/plain; charset=utf-8")


def main():
    signing_secret()
    credentials()
    print(f"[radiko] Premium refresh gateway build={BUILD}", flush=True)
    print(f"[radiko] listening on http://{HOST}:{PORT}", flush=True)
    server = ThreadingHTTPServer((HOST, PORT), Handler)
    server.serve_forever()


if __name__ == "__main__":
    main()
