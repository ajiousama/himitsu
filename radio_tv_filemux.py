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


def prewarm_station(station: str) -> None:
    # v10 intentionally avoids background muxers. IPTV clients often issue a
    # HEAD immediately before GET; starting FFmpeg on HEAD made the real GET
    # race or wait behind a second muxer on Render's small instance.
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


def _start_file_mux(station: str, source: str, timeout: float = 12.0):
    fd, name = tempfile.mkstemp(prefix="radio-tv-", suffix=".ts", dir="/tmp")
    os.close(fd)
    path = pathlib.Path(name)
    try:
        path.unlink(missing_ok=True)
    except Exception:
        pass

    cmd = impl._ffmpeg_cmd(station, source)
    if cmd[-1] != "pipe:1":
        raise RuntimeError("unexpected FFmpeg output target")
    cmd = cmd[:-1] + ["-y", str(path)]

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        bufsize=0,
    )
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
                    # FFmpeg ended; drain any final bytes written just before exit.
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
        impl.base.make_art(station)
        impl.base.ffmpeg_exe()
    except Exception as e:
        handler.send_error(500, f"ffmpeg setup failed: {type(e).__name__}: {e}")
        return

    failures = []
    for source in impl._audio_sources(station):
        proc, path, detail = _start_file_mux(station, source, 12.0)
        if proc is not None and path is not None:
            _stream_file(handler, proc, path)
            return
        failures.append(f"{source}: {detail[-1200:]}")
        print(
            f"[radio-tv-filemux] startup failed station={station} source={source} detail={detail[-500:]}",
            flush=True,
        )

    handler.send_error(504, (" | ".join(failures)[-3000:] or "radio file mux failed"))


def handle_request(handler) -> bool:
    parsed = urllib.parse.urlsplit(handler.path)
    if parsed.path.startswith("/radio-tv/"):
        station = urllib.parse.unquote(parsed.path.split("/", 2)[2]).strip()
        _stream_station(handler, station)
        return True
    # Keep the existing debug/art routes and nationwide station discovery.
    return impl.handle_request(handler)
