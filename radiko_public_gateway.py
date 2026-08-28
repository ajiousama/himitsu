#!/usr/bin/env python3
import hashlib
import hmac
import os
import re
import secrets
import urllib.error
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = os.environ.get("RADIKO_GATEWAY_HOST", "127.0.0.1")
PORT = int(os.environ.get("RADIKO_GATEWAY_PORT", "9396"))
BACKEND = os.environ.get("RADIKO_GATEWAY_BACKEND", "http://127.0.0.1:9395").rstrip("/")
ACCESS_KEY = os.environ.get("RADIKO_ACCESS_KEY", "").strip()
PUBLIC_NO_KEY = os.environ.get("RADIKO_PUBLIC_NO_KEY", "0").strip().lower() in {"1", "true", "yes", "on"}
SIGNING_SECRET = os.environ.get("RADIKO_GATEWAY_SIGNING_SECRET", "").strip() or secrets.token_hex(32)
SID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def add_query(url, name, value):
    if not value:
        return url
    p = urllib.parse.urlsplit(url)
    q = urllib.parse.parse_qsl(p.query, keep_blank_values=True)
    q = [(k, v) for k, v in q if k != name]
    q.append((name, value))
    return urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, urllib.parse.urlencode(q), p.fragment))


def add_key(url, key):
    return add_query(url, "k", key) if key else url


def proxy_signature(target):
    return hmac.new(SIGNING_SECRET.encode("utf-8"), target.encode("utf-8"), hashlib.sha256).hexdigest()


def signed_proxy_url(url):
    p = urllib.parse.urlsplit(url)
    if p.path != "/proxy":
        return url
    q = urllib.parse.parse_qs(p.query)
    target = (q.get("u") or [""])[0]
    if not target:
        return url
    return add_query(url, "s", proxy_signature(target))


def valid_signed_proxy(parsed):
    if parsed.path != "/proxy":
        return False
    q = urllib.parse.parse_qs(parsed.query)
    target = (q.get("u") or [""])[0]
    supplied = (q.get("s") or [""])[0]
    if not target or not supplied:
        return False
    try:
        tp = urllib.parse.urlsplit(target)
    except Exception:
        return False
    if tp.scheme not in {"http", "https"} or not tp.hostname:
        return False
    return hmac.compare_digest(supplied, proxy_signature(target))


def public_path_allowed(parsed):
    if parsed.path in {"/health", "/epg.xml", "/playlist.m3u", "/"}:
        return True
    if parsed.path.startswith("/live/"):
        sid = urllib.parse.unquote(parsed.path.split("/", 2)[2])
        return bool(SID_RE.fullmatch(sid))
    if parsed.path == "/proxy":
        return valid_signed_proxy(parsed)
    return False


def rewrite_text(text, public_base, key):
    host = urllib.parse.urlsplit(public_base).netloc
    text = text.replace(f"http://{host}", public_base).replace(f"https://{host}", public_base)
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("#EXTM3U") and "url-tvg=" in line:
            old1 = f'url-tvg="{public_base}/epg.xml"'
            old2 = f"url-tvg='{public_base}/epg.xml'"
            if old1 in line:
                line = line.replace(old1, f'url-tvg="{add_key(public_base + "/epg.xml", key)}"')
            if old2 in line:
                line = line.replace(old2, f"url-tvg='{add_key(public_base + '/epg.xml', key)}'")
        elif s.startswith(public_base + "/"):
            if PUBLIC_NO_KEY and urllib.parse.urlsplit(s).path == "/proxy":
                line = signed_proxy_url(s)
            else:
                line = add_key(s, key)
        out.append(line)
    return "\n".join(out) + "\n"


class Handler(BaseHTTPRequestHandler):
    server_version = "RadikoPublicGateway/1.2"

    def log_message(self, fmt, *args):
        print("[radiko-public] " + fmt % args, flush=True)

    def _public_base(self):
        proto = (self.headers.get("X-Forwarded-Proto") or "https").split(",", 1)[0].strip()
        host = (self.headers.get("X-Forwarded-Host") or self.headers.get("Host") or "").split(",", 1)[0].strip()
        return f"{proto}://{host}".rstrip("/")

    def _authorized(self, parsed):
        if PUBLIC_NO_KEY:
            return public_path_allowed(parsed)
        if parsed.path == "/health":
            return True
        if not ACCESS_KEY:
            return False
        supplied = (urllib.parse.parse_qs(parsed.query).get("k") or [""])[0]
        return supplied == ACCESS_KEY

    def do_GET(self):
        parsed = urllib.parse.urlsplit(self.path)
        if not self._authorized(parsed):
            self.send_error(403, "access denied")
            return
        if parsed.path == "/health":
            body = b"OK\n"
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        target = BACKEND + self.path
        headers = {"User-Agent": self.headers.get("User-Agent", "Mozilla/5.0")}
        public_base = self._public_base()
        if urllib.parse.urlsplit(public_base).netloc:
            headers["Host"] = urllib.parse.urlsplit(public_base).netloc
        try:
            with urllib.request.urlopen(urllib.request.Request(target, headers=headers), timeout=60) as r:
                data = r.read()
                ctype = r.headers.get("Content-Type", "application/octet-stream")
                is_text_m3u = "mpegurl" in ctype.lower() or parsed.path.endswith((".m3u", ".m3u8")) or data.startswith(b"#EXTM3U")
                if is_text_m3u:
                    rewrite_key = "" if PUBLIC_NO_KEY else ACCESS_KEY
                    data = rewrite_text(data.decode("utf-8", "replace"), public_base, rewrite_key).encode("utf-8")
                    ctype = "application/vnd.apple.mpegurl; charset=utf-8"
                self.send_response(r.status)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(data)
        except urllib.error.HTTPError as e:
            self.send_error(e.code, str(e.reason))
        except Exception as e:
            self.send_error(502, str(e))


def main():
    if not PUBLIC_NO_KEY and not ACCESS_KEY:
        raise SystemExit("RADIKO_ACCESS_KEY is not set")
    mode = "public-restricted-signed" if PUBLIC_NO_KEY else "key-protected"
    print(f"radiko public gateway ({mode}): http://{HOST}:{PORT}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
