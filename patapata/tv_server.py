#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import http.server
import io
import json
import mimetypes
import os
import pathlib
import shutil
import subprocess
import zipfile
import threading
import time
import re
from datetime import datetime, timezone
import urllib.parse

from playwright.sync_api import sync_playwright
from websockets.sync.client import connect as ws_connect

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
STREAM_SEM = threading.BoundedSemaphore(6)
HLS_DIR = pathlib.Path("/tmp/patapata-tv-hls")
HLS_PLAYLIST = HLS_DIR / "index.m3u8"
HLS_ERROR = ""

# --- AIS PROXY v1 ---
AIS_API_KEY = os.environ.get("AISSTREAM_API_KEY", "").strip()
AIS_STREAM_URL = "wss://stream.aisstream.io/v0/stream"
# 西瀬戸内〜豊後水道北部。lat/lon の対角2点。
AIS_BOUNDING_BOXES = [[[35.0, 130.5], [32.9, 134.7]]]
AIS_LOCK = threading.Lock()
AIS_VESSELS: dict[str, dict] = {}
AIS_STATIC: dict[str, dict] = {}
AIS_STATUS = "key_missing" if not AIS_API_KEY else "starting"
AIS_ERROR = ""
AIS_UPDATED_AT = 0.0
AIS_STALE_SECONDS = 20 * 60
AIS_NAME_RE = re.compile(r"(FERRY|SUNFLOWER|ORANGE|HANKYU|HAN9|YAMATO|SETTSU|HIBIKI|IZUMI|OCEAN|TOKYU|SEA\\s*PASEO|SEAPASEO|SUPER\\s*JET|JET)", re.I)

TV_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;600;700;800;900&display=swap');
html, body { width:100% !important; height:100% !important; margin:0 !important; overflow:hidden !important; background:#071019 !important; }
html, body, body * {
  font-family:'Noto Sans JP', sans-serif !important;
  font-variant-numeric: tabular-nums;
}
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

    extract_base = pathlib.Path("/tmp/patapata-tv-assets")
    extract_base.mkdir(parents=True, exist_ok=True)

    # These chunks are the verified FINAL-v5-JR-DEADHEAD web ZIP already kept
    # in the repository. Their unusual suffixes are intentionally joined in
    # normal filename (lexicographic) order.
    parts = sorted(HERE.glob("latest.zip.b64.*"), key=lambda p: p.name)
    if not parts:
        raise RuntimeError("Patapata latest ZIP parts are missing")

    payload = "".join(p.read_text(encoding="ascii").strip() for p in parts)
    raw = base64.b64decode(payload, validate=True)

    with zipfile.ZipFile(io.BytesIO(raw), "r") as zf:
        bad = zf.testzip()
        if bad:
            raise RuntimeError(f"Patapata ZIP CRC failure: {bad}")
        names = zf.namelist()
        expected = "Matsuyama-Patapata-FINAL-v5-JR-DEADHEAD/index.html"
        if expected not in names:
            raise RuntimeError("Patapata ZIP is not FINAL-v5-JR-DEADHEAD")
        zf.extractall(extract_base)

    index = extract_base / "Matsuyama-Patapata-FINAL-v5-JR-DEADHEAD" / "index.html"
    if not index.is_file():
        raise RuntimeError("Patapata index.html missing after extraction")
    ASSET_DIR = index.parent
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
                try:
                    page.evaluate("document.fonts.ready.then(() => true)")
                    page.wait_for_function("document.fonts && document.fonts.status === 'loaded'", timeout=15000)
                except Exception as e:
                    print(f"[patapata] webfont wait warning: {e}", flush=True)
                page.wait_for_timeout(1200)
                try:
                    ok = page.evaluate("document.fonts.check(\"16px 'Noto Sans JP'\", \"松山交通総合発着案内\")")
                    print(f"[patapata] japanese font ready={ok}", flush=True)
                except Exception as e:
                    print(f"[patapata] font check warning: {e}", flush=True)
                BROWSER_ERROR = ""
                while not STOP.is_set():
                    frame = page.screenshot(type="jpeg", quality=76, animations="allow")
                    with FRAME_LOCK:
                        LATEST_FRAME = frame
                        FRAME_AT = time.time()
                    page.wait_for_timeout(120)
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
        "-f", "image2pipe", "-framerate", "8", "-vcodec", "mjpeg", "-i", "pipe:0",
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
        "-map", "0:v:0", "-map", "1:a:0",
        "-vf", "fps=8",
        "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
        "-profile:v", "baseline", "-level", "3.1",
        "-crf", "28", "-pix_fmt", "yuv420p", "-r", "8", "-g", "16",
        "-keyint_min", "16", "-sc_threshold", "0",
        "-c:a", "aac", "-b:a", "64k", "-ar", "48000", "-ac", "2",
        "-muxdelay", "0", "-muxpreload", "0", "-flush_packets", "1",
        "-mpegts_flags", "resend_headers",
        "-f", "mpegts", "pipe:1",
    ]

def ffmpeg_hls_cmd() -> list[str]:
    ff = shutil.which("ffmpeg")
    if not ff:
        raise RuntimeError("ffmpeg not found")
    HLS_DIR.mkdir(parents=True, exist_ok=True)
    return [
        ff,
        "-nostdin", "-hide_banner", "-loglevel", "warning",
        "-f", "image2pipe", "-framerate", "2", "-vcodec", "mjpeg", "-i", "pipe:0",
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
        "-map", "0:v:0", "-map", "1:a:0",
        "-vf", "fps=10",
        "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
        "-profile:v", "baseline", "-level", "3.1",
        "-crf", "28", "-pix_fmt", "yuv420p", "-r", "10", "-g", "20",
        "-keyint_min", "20", "-sc_threshold", "0",
        "-c:a", "aac", "-b:a", "64k", "-ar", "48000", "-ac", "2",
        "-f", "hls",
        "-hls_time", "2",
        "-hls_list_size", "12",
        "-hls_delete_threshold", "18",
        "-hls_allow_cache", "0",
        "-hls_flags", "delete_segments+omit_endlist+independent_segments+program_date_time",
        "-hls_segment_filename", str(HLS_DIR / "seg_%06d.ts"),
        str(HLS_PLAYLIST),
    ]

def hls_worker() -> None:
    global HLS_ERROR
    while not STOP.is_set():
        proc = None
        feeder_stop = threading.Event()
        try:
            first = wait_frame(timeout=45.0)
            if not first:
                HLS_ERROR = BROWSER_ERROR or "waiting for first frame"
                time.sleep(3)
                continue
            HLS_DIR.mkdir(parents=True, exist_ok=True)
            for old in HLS_DIR.glob("*"):
                try:
                    old.unlink()
                except OSError:
                    pass
            cmd = ffmpeg_hls_cmd()
            print("[patapata] HLS ffmpeg:", " ".join(cmd[:4]), "...", flush=True)
            proc = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                bufsize=0,
            )
            HLS_ERROR = ""

            def feed() -> None:
                last = first
                try:
                    while not feeder_stop.is_set() and proc.poll() is None:
                        with FRAME_LOCK:
                            if LATEST_FRAME:
                                last = LATEST_FRAME
                        proc.stdin.write(last)
                        proc.stdin.flush()
                        time.sleep(0.125)
                except (BrokenPipeError, OSError, ValueError):
                    pass
                finally:
                    try:
                        proc.stdin.close()
                    except Exception:
                        pass

            threading.Thread(target=feed, daemon=True).start()
            while not STOP.is_set() and proc.poll() is None:
                time.sleep(1)
            if proc.poll() is not None:
                err = (proc.stderr.read() or b"").decode("utf-8", "replace")[-4000:]
                HLS_ERROR = f"ffmpeg exited {proc.returncode}: {err.strip()}"
                print("[patapata] HLS error:", HLS_ERROR, flush=True)
        except Exception as e:
            HLS_ERROR = f"{type(e).__name__}: {e}"
            print("[patapata] HLS worker error:", HLS_ERROR, flush=True)
        finally:
            feeder_stop.set()
            if proc is not None and proc.poll() is None:
                try:
                    proc.terminate()
                    proc.wait(timeout=2)
                except Exception:
                    try:
                        proc.kill()
                    except Exception:
                        pass
        if not STOP.is_set():
            time.sleep(3)

def wait_hls(timeout: float = 20.0) -> bool:
    end = time.time() + timeout
    while time.time() < end:
        if HLS_PLAYLIST.is_file() and HLS_PLAYLIST.stat().st_size > 0:
            try:
                text = HLS_PLAYLIST.read_text(encoding="utf-8", errors="replace")
                if "#EXTM3U" in text and any(
                    line.strip() and not line.startswith("#")
                    for line in text.splitlines()
                ):
                    return True
            except OSError:
                pass
        time.sleep(0.2)
    return False

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
                    time.sleep(0.125)
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


def _ais_is_passenger(name: str, ship_type) -> bool:
    try:
        t = int(ship_type) if ship_type is not None else -1
    except Exception:
        t = -1
    return 60 <= t <= 69 or bool(AIS_NAME_RE.search(name or ""))

def _ais_update_static(mmsi: str, payload: dict, msg_type: str, metadata: dict) -> None:
    current = AIS_STATIC.get(mmsi, {}).copy()
    if msg_type == "ShipStaticData":
        current.update({
            "name": (payload.get("Name") or metadata.get("ShipName") or current.get("name") or "").strip(),
            "ship_type": payload.get("Type", current.get("ship_type")),
            "destination": (payload.get("Destination") or current.get("destination") or "").strip(),
            "imo": payload.get("ImoNumber", current.get("imo")),
        })
    elif msg_type == "StaticDataReport":
        a = payload.get("ReportA") or {}
        b = payload.get("ReportB") or {}
        if a.get("Valid") and a.get("Name"):
            current["name"] = str(a.get("Name")).strip()
        if b.get("Valid"):
            current["ship_type"] = b.get("ShipType", current.get("ship_type"))
    if not current.get("name"):
        current["name"] = str(metadata.get("ShipName") or "").strip()
    current["updated_at"] = time.time()
    AIS_STATIC[mmsi] = current

def _ais_position_from_message(msg_type: str, payload: dict, metadata: dict):
    lat = payload.get("Latitude", metadata.get("Latitude", metadata.get("latitude")))
    lon = payload.get("Longitude", metadata.get("Longitude", metadata.get("longitude")))
    if lat is None or lon is None:
        return None
    try:
        lat = float(lat); lon = float(lon)
    except Exception:
        return None
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return {
        "lat": lat,
        "lng": lon,
        "sog": payload.get("Sog"),
        "cog": payload.get("Cog"),
        "heading": payload.get("TrueHeading"),
        "nav_status": payload.get("NavigationalStatus"),
    }

def _ais_handle_message(obj: dict) -> None:
    global AIS_UPDATED_AT
    msg_type = str(obj.get("MessageType") or "")
    metadata = obj.get("MetaData") or {}
    mmsi = str(metadata.get("MMSI") or "")
    if not mmsi:
        return
    payload = (obj.get("Message") or {}).get(msg_type) or {}
    now = time.time()
    with AIS_LOCK:
        if msg_type in ("ShipStaticData", "StaticDataReport"):
            _ais_update_static(mmsi, payload, msg_type, metadata)
        elif msg_type in ("PositionReport", "StandardClassBPositionReport", "ExtendedClassBPositionReport", "LongRangeAisBroadcastMessage"):
            pos = _ais_position_from_message(msg_type, payload, metadata)
            if pos:
                static = AIS_STATIC.get(mmsi, {})
                name = str(metadata.get("ShipName") or static.get("name") or "").strip()
                AIS_VESSELS[mmsi] = {
                    "mmsi": mmsi,
                    "name": name,
                    "ship_type": static.get("ship_type"),
                    "destination": static.get("destination", ""),
                    **pos,
                    "updated_at": now,
                }
                AIS_UPDATED_AT = now

def ais_worker() -> None:
    global AIS_STATUS, AIS_ERROR
    if not AIS_API_KEY:
        AIS_STATUS = "key_missing"
        return
    backoff = 2
    while not STOP.is_set():
        try:
            AIS_STATUS = "connecting"
            AIS_ERROR = ""
            with ws_connect(AIS_STREAM_URL, compression="deflate", open_timeout=15, close_timeout=5) as ws:
                ws.send(json.dumps({
                    "APIKey": AIS_API_KEY,
                    "BoundingBoxes": AIS_BOUNDING_BOXES,
                    "FilterMessageTypes": [
                        "PositionReport",
                        "StandardClassBPositionReport",
                        "ExtendedClassBPositionReport",
                        "LongRangeAisBroadcastMessage",
                        "ShipStaticData",
                        "StaticDataReport",
                    ],
                }))
                AIS_STATUS = "live"
                backoff = 2
                while not STOP.is_set():
                    try:
                        raw = ws.recv(timeout=90)
                    except TimeoutError:
                        raise RuntimeError("AIS stream timeout")
                    if raw is None:
                        raise RuntimeError("AIS stream closed")
                    if isinstance(raw, bytes):
                        raw = raw.decode("utf-8", "replace")
                    obj = json.loads(raw)
                    if obj.get("MessageType") == "SubscriptionConfirmation":
                        continue
                    _ais_handle_message(obj)
        except Exception as e:
            AIS_STATUS = "error"
            AIS_ERROR = f"{type(e).__name__}: {e}"
            print(f"[ais] worker error: {AIS_ERROR}", flush=True)
            if STOP.wait(backoff):
                break
            backoff = min(backoff * 2, 60)

def ais_snapshot() -> dict:
    now = time.time()
    rows = []
    with AIS_LOCK:
        stale = [m for m, v in AIS_VESSELS.items() if now - float(v.get("updated_at") or 0) > AIS_STALE_SECONDS]
        for m in stale:
            AIS_VESSELS.pop(m, None)
        for v in AIS_VESSELS.values():
            static = AIS_STATIC.get(str(v.get("mmsi")), {})
            name = str(v.get("name") or static.get("name") or "").strip()
            ship_type = v.get("ship_type", static.get("ship_type"))
            if not _ais_is_passenger(name, ship_type):
                continue
            row = dict(v)
            row["name"] = name or f"MMSI {v.get('mmsi','')}"
            row["ship_type"] = ship_type
            row["destination"] = str(v.get("destination") or static.get("destination") or "").strip()
            row["age_seconds"] = max(0, int(now - float(v.get("updated_at") or now)))
            rows.append(row)
    rows.sort(key=lambda x: (x.get("name") or "", x.get("mmsi") or ""))
    updated = datetime.fromtimestamp(AIS_UPDATED_AT, timezone.utc).isoformat() if AIS_UPDATED_AT else None
    return {
        "status": AIS_STATUS,
        "updated_at": updated,
        "error": AIS_ERROR,
        "bbox": AIS_BOUNDING_BOXES,
        "vessels": rows,
    }


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

    def _json(self, status: int, obj):
        data = json.dumps(obj, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def do_HEAD(self):
        path = urllib.parse.urlsplit(self.path).path
        if path == "/ais.json":
            self._json(200, ais_snapshot())
            return
        if path == "/tv":
            self.send_response(200)
            self.send_header("Content-Type", "video/mp2t")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            return
        if path == "/live.m3u8":
            status = 200 if wait_hls(timeout=2.0) else 503
            self._text(status, "#EXTM3U\n" if status == 200 else "HLS warming up\n", "application/vnd.apple.mpegurl; charset=utf-8")
            return
        if path == "/health":
            self._text(200, "ok\n")
            return
        self.do_GET()

    def do_GET(self):
        path = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
        if path == "/ais.json":
            self._json(200, ais_snapshot())
            return
        if path == "/tv":
            stream_tv(self)
            return
        if path == "/live.m3u8":
            if not wait_hls(timeout=20.0):
                self.send_error(503, f"Patapata HLS not ready: {HLS_ERROR or 'warming up'}")
                return
            text = HLS_PLAYLIST.read_text(encoding="utf-8", errors="replace")
            out = []
            for line in text.splitlines():
                if line and not line.startswith("#"):
                    out.append("/hls/" + pathlib.Path(line).name)
                else:
                    out.append(line)
            self._text(200, "\n".join(out).rstrip() + "\n", "application/vnd.apple.mpegurl; charset=utf-8")
            return
        if path.startswith("/hls/"):
            name = pathlib.Path(path[len("/hls/"):]).name
            if not name.endswith(".ts"):
                self.send_error(404)
                return
            target = HLS_DIR / name
            if not target.is_file():
                self.send_error(404)
                return
            data = target.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "video/mp2t")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
            return
        if path == "/health":
            with FRAME_LOCK:
                age = time.time() - FRAME_AT if FRAME_AT else -1
                ready = LATEST_FRAME is not None and age >= 0 and age < 8
            hls_ready = HLS_PLAYLIST.is_file() and HLS_PLAYLIST.stat().st_size > 0
            self._text(
                200 if ready else 503,
                f"ready={str(ready).lower()} hls_ready={str(hls_ready).lower()} frame_age={age:.2f} error={BROWSER_ERROR} hls_error={HLS_ERROR}\n"
            )
            return
        if path in ("/", "/status"):
            self._text(
                200,
                "Patapata TV\n"
                "source=FINAL-v5-JR-DEADHEAD\n"
                "video=1280x720 8fps real-capture H.264 baseline\n"
                "audio=AAC 48kHz stereo silence\n"
                "stream=/tv\n"
                "hls=/live.m3u8\n",
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
    threading.Thread(target=hls_worker, daemon=True).start()
    if AIS_API_KEY:
        threading.Thread(target=ais_worker, daemon=True).start()
    else:
        print("[ais] AISSTREAM_API_KEY not set; /ais.json will report key_missing", flush=True)
    print(f"[patapata] listening on {HOST}:{PORT}; ffmpeg={shutil.which('ffmpeg')}", flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        STOP.set()
        server.server_close()

if __name__ == "__main__":
    main()
