#!/usr/bin/env python3
from __future__ import annotations

import base64
import hashlib
import http.server
import mimetypes
import os
import pathlib
import shutil
import subprocess
import threading
import time
import urllib.parse
import zipfile
import io
import json

HERE = pathlib.Path(__file__).resolve().parent
TEST_DIR = HERE / "test"
PORT = int(os.environ.get("PORT", "8080"))
HOST = "0.0.0.0"
DISPLAY = os.environ.get("DISPLAY", ":99")
SCREEN_W = 1920
SCREEN_H = 1080
OUT_W = 1920
OUT_H = 1080
FPS = int(os.environ.get("PATAPATA_FPS", "24"))
PAGE_RELOAD_SECONDS = max(30, int(os.environ.get("PATAPATA_PAGE_RELOAD_SECONDS", "120")))
IDLE_SECONDS = max(60, int(os.environ.get("PATAPATA_IDLE_SECONDS", "120")))
SOURCE_URL = os.environ.get("PATAPATA_SOURCE_URL", "https://ajiousama.github.io/live-wallpaper/transport/freewifi/")
HLS_DIR = pathlib.Path("/tmp/patapata-r15-hls")
HLS_PLAYLIST = HLS_DIR / "index.m3u8"
STOP = threading.Event()
PROCESS_LOCK = threading.Lock()
PROCESSES: dict[str, subprocess.Popen] = {}
VIEWER_LOCK = threading.Lock()
LAST_VIEWER_AT = time.monotonic()
READY_ONCE = threading.Event()
LAST_ERROR = ""
DEPLOYMENT_ID = os.environ.get("RAILWAY_DEPLOYMENT_ID") or "r15-live"

TV_STYLE = """
<style id="freewifi-tv-style">
html,body{overflow:hidden!important}
body{
  zoom:1.35!important;
}
#update-modal{display:none!important}
</style>
"""

REMOTE_UPDATE_SCRIPT = f"""
<script id="patapata-remote-update">
(() => {{
  const bootDeployment = {json.dumps(DEPLOYMENT_ID)};
  async function checkRemoteUpdate() {{
    try {{
      const res = await fetch('/version.json?t=' + Date.now(), {{ cache: 'no-store' }});
      if (!res.ok) return;
      const info = await res.json();
      if (info.deployment_id && info.deployment_id !== bootDeployment) {{
        location.reload();
      }}
    }} catch (_) {{}}
  }}
  setTimeout(checkRemoteUpdate, 15000);
  setInterval(checkRemoteUpdate, 30000);
}})();
</script>
"""

def log(msg: str) -> None:
    print(f"[patapata-r15] {msg}", flush=True)

def assemble_assets() -> pathlib.Path:
    if (ASSET_DIR / "index.html").is_file():
        return ASSET_DIR
    parts = sorted(HERE.glob("r14.zip.b64.*"), key=lambda p: p.name)
    if not parts:
        raise RuntimeError("R14 archive parts are missing")
    payload = "".join(p.read_text(encoding="ascii").strip() for p in parts)
    raw = base64.b64decode(payload, validate=True)
    actual = hashlib.sha256(raw).hexdigest()
    if actual != EXPECTED_SHA256:
        raise RuntimeError(f"R14 SHA256 mismatch: {actual}")
    if ASSET_DIR.exists():
        shutil.rmtree(ASSET_DIR)
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(raw), "r") as zf:
        bad = zf.testzip()
        if bad:
            raise RuntimeError(f"R14 ZIP CRC failure: {bad}")
        zf.extractall(ASSET_DIR)
    if not (ASSET_DIR / "index.html").is_file():
        found = list(ASSET_DIR.rglob("index.html"))
        if len(found) != 1:
            raise RuntimeError("R14 index.html not found uniquely")
        root = found[0].parent
        for item in list(root.iterdir()):
            shutil.move(str(item), ASSET_DIR / item.name)
    log(f"R14 ready sha256={actual}")
    return ASSET_DIR

def process_log_path(name: str) -> pathlib.Path:
    return pathlib.Path("/tmp") / f"patapata-{name}.log"

def launch_logged(name: str, cmd: list[str], **kwargs) -> subprocess.Popen:
    # Keep only the latest process attempt's output.
    with process_log_path(name).open("wb") as output:
        return subprocess.Popen(cmd, stdout=output, stderr=subprocess.STDOUT, **kwargs)

def process_alive(name: str) -> bool:
    with PROCESS_LOCK:
        p = PROCESSES.get(name)
    if p is None:
        return False
    code = p.poll()
    if code is None:
        return True
    with PROCESS_LOCK:
        if PROCESSES.get(name) is not p:
            return False
        PROCESSES.pop(name, None)
    log(f"{name} exited unexpectedly: pid={p.pid} returncode={code}")
    try:
        tail = process_log_path(name).read_bytes()[-1500:].decode("utf-8", "replace").strip()
        if tail:
            log(f"{name} exit output: {tail}")
    except OSError:
        pass
    return False

def set_process(name: str, proc: subprocess.Popen) -> None:
    with PROCESS_LOCK:
        PROCESSES[name] = proc

def stop_process(name: str) -> None:
    with PROCESS_LOCK:
        p = PROCESSES.pop(name, None)
    if not p:
        return
    try:
        p.terminate()
        p.wait(timeout=4)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass

def hls_age() -> float:
    try:
        return time.time() - HLS_PLAYLIST.stat().st_mtime
    except OSError:
        return 999999.0

def touch_viewer() -> None:
    global LAST_VIEWER_AT
    with VIEWER_LOCK:
        LAST_VIEWER_AT = time.monotonic()

def viewers_active() -> bool:
    with VIEWER_LOCK:
        return time.monotonic() - LAST_VIEWER_AT < IDLE_SECONDS

def ready() -> bool:
    if not (process_alive("xvfb") and process_alive("chromium") and process_alive("ffmpeg")):
        return False
    try:
        text = HLS_PLAYLIST.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    ok = "#EXTM3U" in text and any(line.strip() and not line.startswith("#") for line in text.splitlines()) and hls_age() < 10
    if ok:
        READY_ONCE.set()
    return ok

class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):
        if self.path.startswith("/health"):
            return
        log("http " + (fmt % args))

    def send_bytes(self, status: int, data: bytes, ctype: str, cache: str = "no-store"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def send_text(self, status: int, text: str, ctype: str = "text/plain; charset=utf-8"):
        self.send_bytes(status, text.encode("utf-8"), ctype)

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
        if path in ("/wallpaper", "/wallpaper/", "/patapata", "/patapata/"):
            self.send_response(302)
            self.send_header("Location", SOURCE_URL)
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            return
        if path == "/version.json":
            self.send_text(
                200,
                json.dumps(
                    {
                        "deployment_id": DEPLOYMENT_ID,
                        "source": "R15-GITHUB-LIVE",
                        "source_url": SOURCE_URL,
                        "fps": FPS,
                    },
                    ensure_ascii=False,
                ) + "\n",
                "application/json; charset=utf-8",
            )
            return
        if path == "/health":
            stream_ready = ready()
            idle = not viewers_active()
            ok = stream_ready or (idle and READY_ONCE.is_set())
            self.send_text(
                200 if ok else 503,
                f"ready={str(stream_ready).lower()} idle={str(idle).lower()} source=R15-GITHUB-LIVE "
                f"fps={FPS} hls_age={hls_age():.2f} "
                f"xvfb={process_alive('xvfb')} chromium={process_alive('chromium')} ffmpeg={process_alive('ffmpeg')} "
                f"error={LAST_ERROR}\n",
            )
            return
        if path in ("/", "/status"):
            self.send_text(
                200,
                "Patapata TV\n"
                "source=R15-GITHUB-LIVE\n"
                f"source_url={SOURCE_URL}\n"
                f"capture=x11grab {SCREEN_W}x{SCREEN_H} {FPS}fps\n"
                f"video={OUT_W}x{OUT_H} H.264 baseline\n"
                "audio=AAC 48kHz stereo silence\n"
                "hls=/live.m3u8\n",
            )
            return
        if path == "/live.m3u8":
            touch_viewer()
            deadline = time.monotonic() + 45
            while not ready() and time.monotonic() < deadline:
                time.sleep(0.25)
            if not ready():
                self.send_text(503, "HLS warming up\n")
                return
            src = HLS_PLAYLIST.read_text(encoding="utf-8", errors="replace")
            lines = []
            for line in src.splitlines():
                if line and not line.startswith("#"):
                    lines.append("/hls/" + pathlib.Path(line).name)
                else:
                    lines.append(line)
            self.send_text(200, "\n".join(lines).rstrip() + "\n", "application/vnd.apple.mpegurl")
            return
        if path.startswith("/hls/"):
            touch_viewer()
            name = pathlib.Path(path[len("/hls/"):]).name
            if not name.endswith(".ts"):
                self.send_error(404)
                return
            target = HLS_DIR / name
            if not target.is_file():
                self.send_error(404)
                return
            self.send_bytes(200, target.read_bytes(), "video/mp2t")
            return
        if path in ("/test", "/test/"):
            path = "/test/index.html"
        if path.startswith("/test/"):
            rel = path[len("/test/"):] or "index.html"
            target = (TEST_DIR / rel).resolve()
            root = TEST_DIR.resolve()
            if target != root and root not in target.parents:
                self.send_error(403)
                return
            if not target.is_file():
                self.send_error(404)
                return
            data = target.read_bytes()
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
                ctype += "; charset=utf-8"
            self.send_bytes(200, data, ctype, "no-store")
            return
        if False and path.startswith("/patapata/"):
            rel = path[len("/patapata/"):] or "index.html"
            target = (ASSET_DIR / rel).resolve()
            root = ASSET_DIR.resolve()
            if target != root and root not in target.parents:
                self.send_error(403)
                return
            if not target.is_file():
                self.send_error(404)
                return
            data = target.read_bytes()
            ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
            if target.name == "index.html":
                html = data.decode("utf-8", "replace")
                html = html.replace("</head>", TV_STYLE + "\n" + REMOTE_UPDATE_SCRIPT + "\n</head>")
                data = html.encode("utf-8")
            if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
                ctype += "; charset=utf-8"
            self.send_bytes(200, data, ctype, "no-cache")
            return
        self.send_error(404)

def start_xvfb() -> subprocess.Popen:
    cmd = [
        "Xvfb", DISPLAY, "-screen", "0", f"{SCREEN_W}x{SCREEN_H}x24",
        "-nolisten", "tcp", "-ac",
    ]
    log("starting Xvfb")
    return launch_logged("xvfb", cmd)

def wait_x() -> None:
    display_num = DISPLAY.lstrip(":").split(".")[0]
    sock = pathlib.Path(f"/tmp/.X11-unix/X{display_num}")
    end = time.time() + 15
    while time.time() < end:
        if sock.exists():
            return
        time.sleep(0.2)
    raise RuntimeError("Xvfb did not become ready")

def start_chromium() -> subprocess.Popen:
    chrome = shutil.which("chromium") or shutil.which("chromium-browser")
    if not chrome:
        raise RuntimeError("chromium not found")
    env = os.environ.copy()
    env["DISPLAY"] = DISPLAY
    url = SOURCE_URL
    cmd = [
        chrome,
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--disable-software-rasterizer",
        "--hide-scrollbars",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-session-crashed-bubble",
        "--disable-infobars",
        "--autoplay-policy=no-user-gesture-required",
        f"--window-size={SCREEN_W},{SCREEN_H}",
        "--window-position=0,0",
        "--kiosk",
        url,
    ]
    log(f"starting Chromium {url}")
    return launch_logged("chromium", cmd, env=env)

def start_ffmpeg() -> subprocess.Popen:
    ff = shutil.which("ffmpeg")
    if not ff:
        raise RuntimeError("ffmpeg not found")
    HLS_DIR.mkdir(parents=True, exist_ok=True)
    for old in HLS_DIR.glob("*"):
        try:
            old.unlink()
        except OSError:
            pass
    cmd = [
        ff, "-nostdin", "-hide_banner", "-loglevel", "warning",
        "-f", "x11grab", "-draw_mouse", "0",
        "-framerate", str(FPS),
        "-video_size", f"{SCREEN_W}x{SCREEN_H}",
        "-i", f"{DISPLAY}.0+0,0",
        "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
        "-map", "0:v:0", "-map", "1:a:0",
        # Do not rescale video when source and output resolutions match.
        *(
            ["-vf", f"scale={OUT_W}:{OUT_H}:flags=fast_bilinear"]
            if (OUT_W, OUT_H) != (SCREEN_W, SCREEN_H)
            else []
        ),
        "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
        "-profile:v", "baseline", "-level", "4.0",
        "-crf", "24", "-pix_fmt", "yuv420p",
        "-r", str(FPS), "-g", str(FPS * 2), "-keyint_min", str(FPS * 2), "-sc_threshold", "0",
        "-c:a", "aac", "-b:a", "64k", "-ar", "48000", "-ac", "2",
        "-f", "hls",
        "-hls_time", "1",
        "-hls_list_size", "8",
        "-hls_delete_threshold", "16",
        "-hls_allow_cache", "0",
        "-hls_flags", "delete_segments+omit_endlist+independent_segments+program_date_time",
        "-hls_segment_filename", str(HLS_DIR / "seg_%06d.ts"),
        str(HLS_PLAYLIST),
    ]
    log(f"starting ffmpeg x11grab {SCREEN_W}x{SCREEN_H}@{FPS} -> {OUT_W}x{OUT_H}")
    return launch_logged("ffmpeg", cmd)

def supervisor() -> None:
    global LAST_ERROR
    last_browser_start = 0.0
    while not STOP.is_set():
        if not viewers_active():
            if PROCESSES:
                log(f"no viewers for {IDLE_SECONDS}s; stopping capture until next request")
                for name in ("ffmpeg", "chromium", "xvfb"):
                    stop_process(name)
            time.sleep(1)
            continue
        try:
            if not process_alive("xvfb"):
                stop_process("chromium")
                stop_process("ffmpeg")
                set_process("xvfb", start_xvfb())
                wait_x()
                time.sleep(0.5)
            if not process_alive("chromium"):
                stop_process("ffmpeg")
                set_process("chromium", start_chromium())
                last_browser_start = time.time()
                time.sleep(5)
            if process_alive("chromium") and last_browser_start and time.time() - last_browser_start >= PAGE_RELOAD_SECONDS:
                log(f"refreshing GitHub Pages source after {PAGE_RELOAD_SECONDS}s")
                stop_process("chromium")
                set_process("chromium", start_chromium())
                last_browser_start = time.time()
                time.sleep(2)
            if not process_alive("ffmpeg"):
                set_process("ffmpeg", start_ffmpeg())
            LAST_ERROR = ""
        except Exception as exc:
            LAST_ERROR = f"{type(exc).__name__}: {exc}"
            log("supervisor error: " + LAST_ERROR)
            time.sleep(3)
        time.sleep(1)

def main() -> None:
    server = http.server.ThreadingHTTPServer((HOST, PORT), Handler)
    server.daemon_threads = True
    threading.Thread(target=supervisor, daemon=True).start()
    log(f"listening on {HOST}:{PORT}")
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        STOP.set()
        server.server_close()
        for name in ("ffmpeg", "chromium", "xvfb"):
            stop_process(name)

if __name__ == "__main__":
    main()

