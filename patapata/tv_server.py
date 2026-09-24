#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import http.server
import io
import mimetypes
import os
import pathlib
import shutil
import subprocess
import tarfile
import threading
import time
import urllib.parse

from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).resolve().parent
PORT = int(os.environ.get("PORT", "10000"))
HOST = "0.0.0.0"
ASSET_DIR = pathlib.Path("/tmp/patapata-tv-assets")
EXPECTED_SHA256 = "31c85da8571e65117297bd5ad5b96b8b27bf1e6e67d3411b1f32b1a2df64a255"

FRAME_LOCK = threading.Lock()
LATEST_FRAME: bytes | None = None
FRAME_AT = 0.0
BROWSER_ERROR = ""
STOP = threading.Event()
STREAM_SEM = threading.BoundedSemaphore(2)

TV_CSS = """
html, body { width:100% !important; height:100% !important; margin:0 !important; overflow:hidden !important; background:#071019 !important; }
#wall {
  left:50% !important; right:auto !important; top:50% !important;
  transform-origin:center center !important;
  transform:translate(-50%,-50%) scale(0.98) !important;
}
#update-modal { display:none !important; }
"""

def ensure_assets() -> pathlib.Path:
    global ASSET_DIR
    if (ASSET_DIR / "index.html").exists():
        return ASSET_DIR
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    parts = sorted(HERE.glob("source.part*.b64"))
    if not parts:
        raise RuntimeError("Patapata source archive parts are missing")
    payload = "".join(p.read_text(encoding="ascii").strip() for p in parts)
    raw = base64.b64decode(payload, validate=True)
    digest = hashlib.sha256(raw).hexdigest()
    if digest != EXPECTED_SHA256:
        raise RuntimeError(f"Patapata archive sha256 mismatch: {digest}")
    with tarfile.open(fileobj=io.BytesIO(raw), mode="r:gz") as tf:
        names = {m.name for m in tf.getmembers()}
        required = {"index.html", "style.css", "app.js", "schedule.js"}
        if not required.issubset(names):
            raise RuntimeError(f"Patapata archive incomplete: {sorted(required - names)}")
        tf.extractall(ASSET_DIR)
    return ASSET_DIR

def browser_worker() -> None:
    global LATEST_FRAME, FRAME_AT, BROWSER_ERROR
    while not STOP.is_set():
        try:
            ensure_assets()
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-gpu",
                        "--hide-scrollbars",
                        "--autoplay-policy=no-user-gesture-required",
                    ],
                )
                page = browser.new_page(
                    viewport={"width": 1280, "height": 720},
                    device_scale_factor=1,
                )
                page.goto(
                    f"http://127.0.0.1:{PORT}/patapata/index.html",
                    wait_until="domcontentloaded",
                    timeout=45000,
                )
                page.add_style_tag(content=TV_CSS)
                page.wait_for_timeout(1500)
                BROWSER_ERROR = ""
                while not STOP.is_set():
                    frame = page.screenshot(type="jpeg", quality=76, animations="allow")
                    with FRAME_LOCK:
                        LATEST_FRAME = frame
                        FRAME_AT = time.time()
                    page.wait_for_timeout(450)
                browser.close()
        except Exception as e:
            BROWSER_ERROR = f"{type(e).__name__}: {e}"
            print(f"[patapata] browser worker error: {BROWSER_ERROR}", flush=True)
            time.sleep(4)

def wait_frame(timeout: float = 20.0) -> bytes | None:
    end = time.time() + timeout
    while time.time() < end:
        with FRAME_LOCK:
            frame = LATEST_FRAME
            age = time.time() - FRAME_AT if FRAME_AT else 999
        if frame and age < 8:
            return frame
        time.sleep(0.15)
    return None

def ffmpeg_cmd() -> list[str]:
    ff = shutil.which("ffmpeg")
    if not ff:
        raise RuntimeError("ffmpeg not found")
    return [
        ff,
        "-nostdin", "-hide_banner", "-loglevel", "warning",
        "-f", "image2pipe", "-framerate", "2", "-vcodec", "mjpeg", "-i", "pipe:0",
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
        "-crf", "28", "-pix_fmt", "yuv420p", "-r", "2", "-g", "4",
        "-c:a", "aac", "-b:a", "64k", "-ar", "48000", "-ac", "2",
        "-muxdelay", "0", "-muxpreload", "0", "-flush_packets", "1",
        "-mpegts_flags", "resend_headers",
        "-f", "mpegts", "pipe:1",
    ]

def stream_tv(handler: "Handler") -> None:
    first = wait_frame()
    if not first:
        handler.send_error(503, f"Patapata browser not ready: {BROWSER_ERROR or 'waiting for first frame'}")
        return
    if not STREAM_SEM.acquire(blocking=False):
        handler.send_error(503, "Patapata TV is busy")
        return
    proc = None
    feeder_stop = threading.Event()
    try:
        proc = subprocess.Popen(
            ffmpeg_cmd(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            bufsize=0,
        )
        def feed() -> None:
            last = first
            try:
                while not feeder_stop.is_set() and proc.poll() is None:
                    with FRAME_LOCK:
                        if LATEST_FRAME:
                            last = LATEST_FRAME
                    proc.stdin.write(last)
                    proc.stdin.flush()
                    time.sleep(0.5)
            except (BrokenPipeError, OSError, ValueError):
                pass
            finally:
                try:
                    proc.stdin.close()
                except Exception:
                    pass
        threading.Thread(target=feed, daemon=True).start()

        handler.send_response(200)
        handler.send_header("Content-Type", "video/mp2t")
        handler.send_header("Cache-Control", "no-store")
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.send_header("Connection", "close")
        handler.end_headers()
        handler.close_connection = True

        while True:
            chunk = proc.stdout.read(64 * 1024)
            if not chunk:
                break
            handler.wfile.write(chunk)
            handler.wfile.flush()
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass
    finally:
        feeder_stop.set()
        if proc is not None:
            try:
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                try:
                    proc.kill()
                except Exception:
                    pass
        STREAM_SEM.release()

class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        print("[http] " + (fmt % args), flush=True)

    def _text(self, status: int, body: str, ctype="text/plain; charset=utf-8"):
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def do_HEAD(self):
        path = urllib.parse.urlsplit(self.path).path
        if path == "/tv":
            self.send_response(200)
            self.send_header("Content-Type", "video/mp2t")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            return
        if path == "/health":
            self._text(200, "ok\n")
            return
        self.do_GET()

    def do_GET(self):
        path = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
        if path == "/tv":
            stream_tv(self)
            return
        if path == "/health":
            with FRAME_LOCK:
                age = time.time() - FRAME_AT if FRAME_AT else -1
                ready = LATEST_FRAME is not None and age >= 0 and age < 8
            self._text(200 if ready else 503, f"ready={str(ready).lower()} frame_age={age:.2f} error={BROWSER_ERROR}\n")
            return
        if path in ("/", "/status"):
            self._text(
                200,
                "Patapata TV\n"
                "source=FINAL-v5-JR-DEADHEAD\n"
                "video=1280x720 2fps H.264 MPEG-TS\n"
                "audio=AAC 48kHz stereo silence\n"
                "stream=/tv\n",
            )
            return
        if path.startswith("/patapata/"):
            root = ensure_assets()
            rel = path[len("/patapata/"):] or "index.html"
            target = (root / rel).resolve()
            if root.resolve() not in target.parents and target != root.resolve():
                self.send_error(403)
                return
            if not target.is_file():
                self.send_error(404)
                return
            data = target.read_bytes()
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", ctype + ("; charset=utf-8" if ctype.startswith("text/") or ctype in ("application/javascript", "application/json") else ""))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
            return
        self.send_error(404)

def main() -> None:
    ensure_assets()
    server = http.server.ThreadingHTTPServer((HOST, PORT), Handler)
    threading.Thread(target=browser_worker, daemon=True).start()
    print(f"[patapata] listening on {HOST}:{PORT}", flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        STOP.set()
        server.server_close()

if __name__ == "__main__":
    main()
