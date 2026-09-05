#!/usr/bin/env python3
from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import ehime_catv_hls as ehime_hls

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "10000"))
BUILD = "20260905-ehime-catv-hls-v2"


class Handler(BaseHTTPRequestHandler):
    server_version = "EhimeCATVHLS/1.0"

    def log_message(self, fmt, *args):
        print("[ehime-catv] " + (fmt % args), flush=True)

    def send_bytes(self, status, data, content_type):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/health"):
            self.send_bytes(200, f"OK build={BUILD}\n".encode(), "text/plain; charset=utf-8")
            return
        if ehime_hls.handle_request(self):
            return
        self.send_bytes(404, b"not found\n", "text/plain; charset=utf-8")

    def do_HEAD(self):
        if self.path == "/" or self.path.startswith("/health"):
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            return
        if ehime_hls.handle_head(self):
            return
        self.send_response(404)
        self.end_headers()


if __name__ == "__main__":
    print(f"[ehime-catv] listening on {HOST}:{PORT} build={BUILD}", flush=True)
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()
