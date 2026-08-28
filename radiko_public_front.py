#!/usr/bin/env python3
from __future__ import annotations

import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOST = os.environ.get("RADIKO_FRONT_HOST", "127.0.0.1")
PORT = int(os.environ.get("RADIKO_FRONT_PORT", "9396"))
UPSTREAM = os.environ.get("RADIKO_FRONT_UPSTREAM", "http://127.0.0.1:9395").rstrip("/")
PUBLIC_HOST = os.environ.get("RADIKO_PUBLIC_HOST", "").strip()


class Handler(BaseHTTPRequestHandler):
    server_version = "RadikoPublicFront/1.0"

    def log_message(self, fmt, *args):
        print("[radiko-front] " + fmt % args, flush=True)

    def do_GET(self):
        if not PUBLIC_HOST:
            self.send_error(503, "RADIKO_PUBLIC_HOST is not set")
            return
        url = UPSTREAM + self.path
        headers = {
            "Host": PUBLIC_HOST,
            "X-Forwarded-Proto": "https",
            "X-Forwarded-Host": PUBLIC_HOST,
            "User-Agent": self.headers.get("User-Agent", "Mozilla/5.0"),
        }
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                data = r.read()
                status = getattr(r, "status", 200)
                content_type = r.headers.get("Content-Type") or "application/octet-stream"
        except urllib.error.HTTPError as e:
            data = e.read()
            status = e.code
            content_type = e.headers.get("Content-Type") or "text/plain; charset=utf-8"
        except Exception as e:
            data = (f"front proxy failure: {type(e).__name__}: {e}\n").encode()
            status = 502
            content_type = "text/plain; charset=utf-8"

        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)


def main():
    if not PUBLIC_HOST:
        raise SystemExit("RADIKO_PUBLIC_HOST is required")
    print(f"[radiko-front] listening http://{HOST}:{PORT} -> {UPSTREAM} public=https://{PUBLIC_HOST}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
