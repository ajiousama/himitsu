#!/usr/bin/env python3
import base64, concurrent.futures, hashlib, json, os, random, threading, urllib.parse, urllib.request, urllib.error
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urljoin

AUTH_KEY = "bcd151073c03b352e1ef2fd66c32209da9ca0afa"
BASE_HEADERS = {
    "X-Radiko-App": "pc_html5",
    "X-Radiko-App-Version": "0.0.1",
    "X-Radiko-Device": "pc",
    "X-Radiko-User": "dummy_user",
    "User-Agent": "Mozilla/5.0",
}
HOST = os.environ.get("RADIKO_PROXY_HOST", "127.0.0.1")
PORT = int(os.environ.get("RADIKO_PROXY_PORT", "9395"))

_state_lock = threading.Lock()
_state = {"session": None, "token": None, "area": None, "stations": None}


def open_url(url, headers=None, data=None, timeout=15):
    req = urllib.request.Request(url, headers=headers or {}, data=data)
    return urllib.request.urlopen(req, timeout=timeout)


def premium_login():
    mail = os.environ.get("RADIKO_MAIL", "").strip()
    password = os.environ.get("RADIKO_PASSWORD", "").strip()
    if not mail or not password:
        raise RuntimeError("RADIKO_MAIL / RADIKO_PASSWORD are not set")
    data = urllib.parse.urlencode({"mail": mail, "pass": password}).encode()
    with open_url("https://radiko.jp/v4/api/member/login", data=data, timeout=30) as r:
        obj = json.loads(r.read().decode("utf-8"))
    session = str(obj.get("radiko_session") or "").strip()
    if not session or str(obj.get("areafree") or "0") != "1":
        raise RuntimeError("radiko Premium area-free login failed")
    return session


def auth(session):
    with open_url("https://radiko.jp/v2/api/auth1", headers=BASE_HEADERS, timeout=30) as r:
        token = r.headers["X-Radiko-AuthToken"]
        off = int(r.headers["X-Radiko-KeyOffset"])
        length = int(r.headers["X-Radiko-KeyLength"])
    partial = base64.b64encode(AUTH_KEY[off:off+length].encode()).decode()
    h = dict(BASE_HEADERS)
    h.update({"X-Radiko-AuthToken": token, "X-Radiko-Partialkey": partial})
    url = "https://radiko.jp/v2/api/auth2?radiko_session=" + urllib.parse.quote(session)
    with open_url(url, headers=h, timeout=30) as r:
        body = r.read().decode().strip()
    return token, (body.split(",")[0] if body else "OUT")


def ensure_auth(force=False):
    with _state_lock:
        if not force and _state["token"]:
            return _state["session"], _state["token"], _state["area"]
    session = premium_login()
    token, area = auth(session)
    with _state_lock:
        _state.update(session=session, token=token, area=area)
    return session, token, area


def _fetch_area_stations(n):
    area = f"JP{n}"
    try:
        with open_url(
            f"https://radiko.jp/v3/station/list/{area}.xml",
            headers={"User-Agent": "Mozilla/5.0"}, timeout=8,
        ) as r:
            root = ET.fromstring(r.read())
    except Exception:
        return []
    found = []
    for st in root.findall("station"):
        sid = (st.findtext("id") or "").strip()
        name = (st.findtext("name") or sid).strip()
        logo = (
            st.findtext("logo_large")
            or st.findtext("logo_medium")
            or st.findtext("logo_small")
            or st.findtext("logo_xsmall")
            or ""
        ).strip()
        if sid:
            found.append((sid, {"name": name, "logo": logo}))
    return found


def discover_stations(force=False):
    with _state_lock:
        if _state["stations"] is not None and not force:
            return _state["stations"]
    stations = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        futures = [ex.submit(_fetch_area_stations, n) for n in range(1, 48)]
        for fut in concurrent.futures.as_completed(futures):
            for sid, meta in fut.result():
                stations.setdefault(sid, meta)
    with _state_lock:
        _state["stations"] = stations
    return stations


def playlist_create_urls(station):
    with open_url(f"https://radiko.jp/v3/station/stream/pc_html5/{station}.xml", headers={"User-Agent":"Mozilla/5.0"}, timeout=10) as r:
        root = ET.fromstring(r.read())
    out = []
    for node in root.findall("url"):
        if node.get("areafree") == "1" and node.get("timefree", "0") == "0":
            p = node.find("playlist_create_url")
            if p is not None and p.text:
                out.append(p.text.strip())
    return out


def auth_headers(token, session=None):
    h = {"X-Radiko-AuthToken": token, "User-Agent": "Mozilla/5.0"}
    if session:
        h["Cookie"] = "radiko_session=" + session
    return h


def get_live_master(station, refresh=False):
    session, token, _ = ensure_auth(force=refresh)
    errors = []
    for base in playlist_create_urls(station):
        for typ in ("b", "c"):
            q = urllib.parse.urlencode({
                "station_id": station,
                "l": 15,
                "lsid": hashlib.md5(str(random.random()).encode()).hexdigest(),
                "type": typ,
            })
            url = base + ("&" if "?" in base else "?") + q
            try:
                with open_url(url, headers=auth_headers(token, session), timeout=12) as r:
                    body = r.read().decode("utf-8", "replace")
                if "#EXTM3U" in body:
                    return url, body
            except Exception as e:
                errors.append(type(e).__name__)
    if not refresh:
        return get_live_master(station, refresh=True)
    raise RuntimeError(f"no playable area-free URL for {station}: {','.join(errors[-3:])}")


def rewrite_m3u(text, source_url, base_proxy):
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith("#"):
            absolute = urljoin(source_url, s)
            line = base_proxy + "/proxy?u=" + urllib.parse.quote(absolute, safe="")
        out.append(line)
    return "\n".join(out) + "\n"


def fetch_proxied(url, refresh=False):
    session, token, _ = ensure_auth(force=refresh)
    try:
        return open_url(url, headers=auth_headers(token, session), timeout=20)
    except urllib.error.HTTPError as e:
        if e.code in (401, 403) and not refresh:
            return fetch_proxied(url, refresh=True)
        raise


class Handler(BaseHTTPRequestHandler):
    server_version = "RadikoProxy/1.2"

    def log_message(self, fmt, *args):
        print("[radiko] " + fmt % args, flush=True)

    def send_bytes(self, status, data, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        p = urllib.parse.urlsplit(self.path)
        base_proxy = f"http://{self.headers.get('Host', f'{HOST}:{PORT}')}"
        try:
            if p.path == "/health":
                self.send_bytes(200, b"OK\n", "text/plain; charset=utf-8")
                return

            if p.path == "/ready":
                _, _, area = ensure_auth()
                stations = discover_stations()
                self.send_bytes(200, f"OK {area} stations={len(stations)}\n".encode(), "text/plain; charset=utf-8")
                return

            if p.path in ("/", "/playlist.m3u"):
                stations = discover_stations()
                lines = ["#EXTM3U"]
                for sid, meta in sorted(stations.items()):
                    logo = meta.get("logo", "")
                    lines.append(f'#EXTINF:-1 tvg-id="radiko.{sid}" tvg-logo="{logo}" group-title="地域（ラジオ）",{meta["name"]}')
                    lines.append(f"{base_proxy}/live/{urllib.parse.quote(sid)}")
                self.send_bytes(200, ("\n".join(lines)+"\n").encode("utf-8"), "audio/x-mpegurl; charset=utf-8")
                return

            if p.path.startswith("/live/"):
                sid = urllib.parse.unquote(p.path.split("/", 2)[2])
                source, text = get_live_master(sid)
                body = rewrite_m3u(text, source, base_proxy).encode("utf-8")
                self.send_bytes(200, body, "application/vnd.apple.mpegurl")
                return

            if p.path == "/proxy":
                qs = urllib.parse.parse_qs(p.query)
                target = (qs.get("u") or [""])[0]
                if not target.startswith(("http://", "https://")):
                    self.send_error(400, "bad proxy URL")
                    return
                with fetch_proxied(target) as r:
                    data = r.read()
                    ctype = r.headers.get_content_type()
                    is_m3u = "mpegurl" in ctype or target.lower().split("?",1)[0].endswith((".m3u8", ".m3u")) or data.startswith(b"#EXTM3U")
                    if is_m3u:
                        text = data.decode("utf-8", "replace")
                        data = rewrite_m3u(text, target, base_proxy).encode("utf-8")
                        ctype = "application/vnd.apple.mpegurl"
                    self.send_bytes(200, data, ctype or "application/octet-stream")
                return

            self.send_error(404)
        except Exception as e:
            self.send_error(502, str(e))


def main():
    print(f"radiko proxy listening: http://{HOST}:{PORT}", flush=True)
    print(f"VLC playlist: http://{HOST}:{PORT}/playlist.m3u", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
