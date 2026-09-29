#!/usr/bin/env python3
from __future__ import annotations

import http.server
import os
import urllib.parse

import radio_tv_filemux as radio_tv

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8080"))
BUILD = "20260929-railway-radio-v1"


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if self.path == "/health":
            return
        print("[freewifi-radio] " + (fmt % args), flush=True)

    def _send(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_HEAD(self):
        path = urllib.parse.urlsplit(self.path).path
        if path == "/health":
            self._send(200, b"", "text/plain; charset=utf-8")
            return
        if path.startswith("/radio-tv/"):
            self._send(200, b"", "video/mp2t")
            return
        self._send(404, b"", "text/plain; charset=utf-8")

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if path == "/health":
            self._send(200, f"OK build={BUILD}\n".encode(), "text/plain; charset=utf-8")
            return
        if path == "/status":
            self._send(
                200,
                (
                    f"FreeWiFi Radio Railway\n"
                    f"build={BUILD}\n"
                    f"audio=Vercel Premium Radiko + ListenRadio/JCBA official sources\n"
                    f"mux=FFmpeg MPEG-TS static-image video\n"
                ).encode(),
                "text/plain; charset=utf-8",
            )
            return
        if radio_tv.handle_request(self):
            return
        self._send(404, b"not found\n", "text/plain; charset=utf-8")


def main() -> None:
    server = http.server.ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True
    print(f"[freewifi-radio] listening on {HOST}:{PORT} build={BUILD}", flush=True)
    server.serve_forever(poll_interval=0.5)


if __name__ == "__main__":
    main()
