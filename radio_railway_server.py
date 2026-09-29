#!/usr/bin/env python3
from __future__ import annotations

import http.server
import os
import urllib.parse

import radio_tv_filemux as radio_tv

HOST = "0.0.0.0"
PORT = int(os.environ.get("PORT", "8080"))
BUILD = "20260929-railway-radio-v2"
FAST_RADIKO = {"HBC", "TBC", "CBC", "RCC", "RKB", "KBC"}
RADIKO_AUDIO_BASE = "https://himitsu-six.vercel.app/api/radiko"
RADIO_VIDEO_BASE = "https://raw.githubusercontent.com/ajiousama/himitsu/radio-ts-assets"


def fast_radiko_master(station: str) -> bytes:
    audio = f"{RADIKO_AUDIO_BASE}?station={urllib.parse.quote(station, safe='')}&stage=media"
    video = f"{RADIO_VIDEO_BASE}/{urllib.parse.quote(station, safe='')}/video.m3u8"
    return ("\n".join([
        "#EXTM3U",
        "#EXT-X-VERSION:6",
        "#EXT-X-INDEPENDENT-SEGMENTS",
        f'#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="radio",NAME="{station} radio",DEFAULT=YES,AUTOSELECT=YES,CHANNELS="2",URI="{audio}"',
        '#EXT-X-STREAM-INF:BANDWIDTH=180000,AVERAGE-BANDWIDTH=120000,RESOLUTION=320x180,FRAME-RATE=1.000,CODECS="avc1.42e01e,mp4a.40.5",AUDIO="radio",CLOSED-CAPTIONS=NONE',
        video,
        "",
    ])).encode()


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
            station = urllib.parse.unquote(path.split("/", 2)[2]).strip()
            ctype = "application/vnd.apple.mpegurl; charset=utf-8" if station in FAST_RADIKO else "video/mp2t"
            self._send(200, b"", ctype)
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
                    f"radiko6=direct HLS master (no FFmpeg startup)\n"
                    f"community=ListenRadio/JCBA + FFmpeg MPEG-TS static-image video\n"
                ).encode(),
                "text/plain; charset=utf-8",
            )
            return
        if path.startswith("/radio-tv/"):
            station = urllib.parse.unquote(path.split("/", 2)[2]).strip()
            if station in FAST_RADIKO:
                self._send(200, fast_radiko_master(station), "application/vnd.apple.mpegurl; charset=utf-8")
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
