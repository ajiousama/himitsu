#!/usr/bin/env python3
from __future__ import annotations

import collections
import os
import pathlib
import subprocess
import tempfile
import threading
import time
import urllib.parse

import radio_tv_nationwide as impl

VIDEO_DIR = pathlib.Path("/tmp/radio-tv-video")
VIDEO_DIR.mkdir(parents=True, exist_ok=True)
_VIDEO_LOCKS: dict[str, threading.Lock] = {}
_VIDEO_LOCKS_GUARD = threading.Lock()


def prewarm_station(station: str) -> None:
    return


def _drain_stderr(pipe, tail) -> None:
    try:
        while True:
            chunk = pipe.readline()
            if not chunk:
                break
            tail.append(chunk)
    except Exception:
        pass


def _station_lock(station: str) -> threading.Lock:
    with _VIDEO_LOCKS_GUARD:
        return _VIDEO_LOCKS.setdefault(station, threading.Lock())


def _video_path(station: str) -> pathlib.Path:
    safe = station.replace("/", "_")
    return VIDEO_DIR / f"{safe}.mp4"


def _ensure_video(station: str) -> pathlib.Path:
    out = _video_path(station)
    if out.exists() and out.stat().st_size > 1000:
        return out
    with _station_lock(station):
        if out.exists() and out.stat().st_size > 1000:
            return out
        art = impl.base.make_art(station)
        tmp = out.with_suffix(".tmp.mp4")
        tmp.unlink(missing_ok=True)
        cmd = [
            impl.base.ffmpeg_exe(), "-nostdin", "-hide_banner", "-loglevel", "error",
            "-loop", "1", "-framerate", "1", "-i", str(art),
            "-t", "2",
            "-an",
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "stillimage",
            "-crf", "31", "-pix_fmt", "yuv420p", "-r", "1", "-g", "2",
            "-movflags", "+faststart", "-y", str(tmp),
        ]
        p = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=12)
        if p.returncode != 0 or not tmp.exists() or tmp.stat().st_size <= 1000:
            err = p.stderr.decode("utf-8", "replace")[-2000:]
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"station video encode failed: {err}")
        os.replace(tmp, out)
        return out


def _new_output_path() -> pathlib.Path:
    fd, name = tempfile.mkstemp(prefix="radio-tv-", suffix=".ts", dir="/tmp")
    os.close(fd)
    path = pathlib.Path(name)
    path.unlink(missing_ok=True)
    return path


def _file_cmd(station: str, source: str, path: pathlib.Path) -> list[str]:
    video = _ensure_video(station)
    return [
        impl.base.ffmpeg_exe(),
        "-nostdin", "-hide_banner", "-loglevel", "warning",
        "-thread_queue_size", "128",
        "-re", "-stream_loop", "-1", "-i", str(video),
        "-rw_timeout", "10000000",
        "-user_agent", "Mozilla/5.0",
        "-thread_queue_size", "128",
        "-fflags", "nobuffer",
        "-flags", "low_delay",
        # -1 is the only Radiko live-edge mode that proved reliable. Keep it.
        "-live_start_index", "-1",
        "-probesize", "32768",
        "-analyzeduration", "200000",
        "-i", source,
        "-map", "0:v:0", "-map", "1:a:0",
        # Both tracks are already in the exact codecs MPEG-TS needs.
        "-c:v", "copy",
        "-c:a", "copy",
        "-muxdelay", "0", "-muxpreload", "0", "-flush_packets", "1",
        "-max_delay", "0",
        "-mpegts_flags", "resend_headers",
        "-f", "mpegts", str(path),
    ]


def _start_file_mux(station: str, source: str, timeout: float = 12.0):
    path = _new_output_path()
    cmd = _file_cmd(station, source, path)
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, bufsize=0)
    tail = collections.deque(maxlen=120)
    threading.Thread(target=_drain_stderr, args=(proc.stderr, tail), daemon=True).start()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            size = path.stat().st_size
        except FileNotFoundError:
            size = 0
        if size >= 188 * 7:
            return proc, path, tail
        if proc.poll() is not None:
            break
        time.sleep(0.05)
    impl.base._stop_proc(proc)
    detail = b"".join(tail).decode("utf-8", "replace").strip()
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass
    return None, None, detail or "file mux startup timeout"


def _stream_file(handler, proc: subprocess.Popen, path: pathlib.Path) -> None:
    handler.send_response(200)
    handler.send_header("Content-Type", "video/mp2t")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Connection", "close")
    handler.end_headers()
    handler.close_connection = True
    try:
        with path.open("rb", buffering=0) as src:
            while True:
                chunk = src.read(64 * 1024)
                if chunk:
                    handler.wfile.write(chunk)
                    handler.wfile.flush()
                    continue
                if proc.poll() is not None:
                    chunk = src.read(64 * 1024)
                    if chunk:
                        handler.wfile.write(chunk)
                        handler.wfile.flush()
                    break
                time.sleep(0.05)
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass
    finally:
        impl.base._stop_proc(proc)
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass


def _stream_station(handler, station: str) -> None:
    if station not in impl.base.STATIONS:
        handler.send_error(404, "unknown radio station")
        return
    try:
        _ensure_video(station)
    except Exception as e:
        handler.send_error(500, f"station video setup failed: {type(e).__name__}: {e}")
        return
    failures = []
    for source in impl._audio_sources(station):
        proc, path, detail = _start_file_mux(station, source, 12.0)
        if proc is not None and path is not None:
            _stream_file(handler, proc, path)
            return
        failures.append(f"{source}: {detail[-1200:]}")
        print(f"[radio-tv-filemux] startup failed station={station} source={source} detail={detail[-500:]}", flush=True)
    handler.send_error(504, (" | ".join(failures)[-3000:] or "radio file mux failed"))


def _debug_file_mux(handler, station: str) -> None:
    if station not in impl.base.STATIONS:
        handler.send_error(404, "unknown radio station")
        return
    lines = [f"station={station}", "video_mode=preencoded-h264-copy", "live_start_index=-1"]
    try:
        t0 = time.monotonic()
        video = _ensure_video(station)
        lines.append(f"video_ready_elapsed={time.monotonic() - t0:.3f}")
        lines.append(f"video_bytes={video.stat().st_size}")
    except Exception as e:
        lines.append(f"video_error={type(e).__name__}: {e}")
        video = None
    source = impl._audio_sources(station)[0]
    lines.append(f"source={source}")
    started = time.monotonic()
    proc = None
    path = None
    try:
        proc, path, detail = _start_file_mux(station, source, 15.0)
        lines.append(f"elapsed={time.monotonic() - started:.3f}")
        lines.append(f"started={proc is not None}")
        if proc is not None and path is not None:
            try:
                size = path.stat().st_size
            except FileNotFoundError:
                size = -1
            lines.append(f"bytes={size}")
            lines.append(f"proc_poll={proc.poll()}")
        else:
            lines.append("bytes=0")
            lines.append("detail=" + str(detail).replace("\n", " | ")[-5000:])
    except Exception as e:
        lines.append(f"error={type(e).__name__}: {e}")
    finally:
        if proc is not None:
            impl.base._stop_proc(proc)
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except Exception:
                pass
    body = ("\n".join(lines) + "\n").encode("utf-8")
    handler.send_response(200)
    handler.send_header("Content-Type", "text/plain; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    handler.wfile.write(body)


def handle_request(handler) -> bool:
    parsed = urllib.parse.urlsplit(handler.path)
    if parsed.path.startswith("/radio-file-debug/"):
        station = urllib.parse.unquote(parsed.path.split("/", 2)[2]).strip()
        _debug_file_mux(handler, station)
        return True
    if parsed.path.startswith("/radio-tv/"):
        station = urllib.parse.unquote(parsed.path.split("/", 2)[2]).strip()
        _stream_station(handler, station)
        return True
    return impl.handle_request(handler)
