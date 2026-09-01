#!/usr/bin/env python3
from __future__ import annotations

import io
import os
import pathlib
import subprocess
import urllib.parse
import urllib.request

from PIL import Image, ImageDraw, ImageFont
import imageio_ffmpeg

RADIKO_BASE = os.environ.get("RADIKO_PUBLIC_BASE", "https://himitsu-six.vercel.app").rstrip("/")
ART_DIR = pathlib.Path(os.environ.get("RADIO_TV_ART_DIR", "/tmp/radio-tv-art"))
ART_DIR.mkdir(parents=True, exist_ok=True)

# display, frequency, accent RGB, radiko station id, fixed audio URL
STATIONS = {
    "nhk_r1_osaka": ("NHK RADIO 1 OSAKA", "AM 666 kHz", (210, 34, 34), None, "https://simul2.drdi.st.nhk/live/12/joined/master.m3u8"),
    "nhk_fm_osaka": ("NHK FM OSAKA", "FM 88.1 MHz", (54, 138, 57), None, "https://simul2.drdi.st.nhk/live/13/joined/master.m3u8"),
    "nhk_r1_matsuyama": ("NHK RADIO 1 MATSUYAMA", "RADIO", (210, 34, 34), None, "https://simul2.drdi.st.nhk/live/16/joined/master.m3u8"),
    "nhk_fm_matsuyama": ("NHK FM MATSUYAMA", "FM", (54, 138, 57), None, "https://simul2.drdi.st.nhk/live/17/joined/master.m3u8"),
    "JOEU-FM": ("FM EHIME", "FM 79.7 MHz", (244, 112, 28), "JOEU-FM", None),
    "RNB": ("RNB NAN-KAI", "AM 1116 kHz / FM 91.7 MHz", (25, 96, 196), "RNB", None),
    "ABC": ("ABC RADIO", "AM 1008 kHz / FM 93.3 MHz", (236, 87, 24), "ABC", None),
    "CCL": ("FM COCOLO", "FM 76.5 MHz", (100, 62, 151), "CCL", None),
    "802": ("FM802", "FM 80.2 MHz", (33, 74, 180), "802", None),
    "FMO": ("FM OSAKA", "FM 85.1 MHz", (30, 125, 185), "FMO", None),
    "MBS": ("MBS RADIO", "AM 1179 kHz / FM 90.6 MHz", (89, 164, 40), "MBS", None),
    "OBC": ("OBC RADIO OSAKA", "AM 1314 kHz / FM 91.9 MHz", (222, 42, 42), "OBC", None),
    "KBS": ("KBS KYOTO RADIO", "AM 1143 kHz / FM 94.9 MHz", (34, 100, 183), "KBS", None),
    "ALPHA-STATION": ("ALPHA-STATION FM KYOTO", "FM 89.4 MHz", (154, 66, 169), "ALPHA-STATION", None),
    "E-RADIO": ("E-RADIO FM SHIGA", "FM 77.0 MHz", (27, 135, 200), "E-RADIO", None),
    "CRK": ("RADIO KANSAI", "AM 558 kHz / FM 91.1 MHz", (41, 91, 174), "CRK", None),
}


def _font(size: int, bold: bool = False):
    paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                pass
    return ImageFont.load_default()


def _logo_url(radiko_sid: str) -> str:
    return f"https://radiko.jp/v2/static/station/logo/{urllib.parse.quote(radiko_sid, safe='')}/lrtrim/688x160.png"


def _fetch_logo(radiko_sid: str):
    try:
        req = urllib.request.Request(_logo_url(radiko_sid), headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as r:
            data = r.read()
        return Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception:
        return None


def make_art(station: str) -> pathlib.Path:
    if station not in STATIONS:
        raise KeyError(station)
    path = ART_DIR / f"{station}.jpg"
    if path.exists() and path.stat().st_size > 5000:
        return path

    display, freq, accent, radiko_sid, _ = STATIONS[station]
    w, h = 640, 360
    im = Image.new("RGB", (w, h), "white")
    dr = ImageDraw.Draw(im)

    # Soft pastel background similar to the approved radio-card design.
    for y in range(h):
        t = y / max(1, h - 1)
        mix = 0.06 + 0.24 * t
        c = tuple(int(250 * (1 - mix) + a * mix) for a in accent)
        dr.line((0, y, w, y), fill=c)

    # Equalizer motif.
    for i in range(42):
        x = 8 + i * 15
        bar = 14 + ((i * 29) % 78)
        dr.rounded_rectangle((x, 286 - bar, x + 8, 286), 3, fill=accent)

    # Header strip and station code.
    dr.rectangle((0, 0, w, 54), fill=accent)
    dr.text((18, 12), display, fill="white", font=_font(27, True))

    # Main logo or fallback text.
    logo = _fetch_logo(radiko_sid) if radiko_sid else None
    if logo is not None:
        logo.thumbnail((470, 125), Image.Resampling.LANCZOS)
        x = (w - logo.width) // 2
        y = 82 + (100 - logo.height) // 2
        im.paste(logo, (x, y), logo)
    else:
        text = "NHK RADIO 1" if "r1" in station else "NHK FM"
        box = dr.textbbox((0, 0), text, font=_font(60, True))
        dr.text(((w - (box[2]-box[0]))//2, 94), text, fill=accent, font=_font(60, True))

    # On-air badge.
    badge = "NOW PLAYING"
    bf = _font(19, True)
    bb = dr.textbbox((0, 0), badge, font=bf)
    bw = bb[2] - bb[0] + 34
    bx = (w - bw) // 2
    dr.rounded_rectangle((bx, 205, bx + bw, 239), 17, fill=accent)
    dr.text((bx + 17, 211), badge, fill="white", font=bf)

    # Dark footer, with Latin text to stay font-safe on Render.
    dr.rectangle((0, 300, w, 360), fill=(13, 17, 22))
    dr.text((18, 311), display, fill="white", font=_font(22, True))
    fb = dr.textbbox((0, 0), freq, font=_font(16, False))
    dr.text((w - (fb[2]-fb[0]) - 18, 334), freq, fill=(225, 230, 235), font=_font(16, False))

    im.save(path, "JPEG", quality=90, optimize=True)
    return path


def audio_url(station: str) -> str:
    display, freq, accent, radiko_sid, fixed = STATIONS[station]
    if fixed:
        return fixed
    return f"{RADIKO_BASE}/api/radiko?station={urllib.parse.quote(radiko_sid, safe='')}"


def ffmpeg_exe() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def stream_station(handler, station: str):
    if station not in STATIONS:
        handler.send_error(404, "unknown radio station")
        return
    art = make_art(station)
    src = audio_url(station)
    cmd = [
        ffmpeg_exe(),
        "-hide_banner", "-loglevel", "error",
        "-re", "-loop", "1", "-framerate", "1", "-i", str(art),
        "-i", src,
        "-map", "0:v:0", "-map", "1:a:0",
        "-c:v", "libx264", "-preset", "ultrafast", "-tune", "stillimage",
        "-crf", "31", "-pix_fmt", "yuv420p", "-r", "1", "-g", "2",
        "-c:a", "aac", "-b:a", "96k", "-ar", "48000", "-ac", "2",
        "-muxdelay", "0", "-muxpreload", "0",
        "-f", "mpegts", "pipe:1",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
    handler.send_response(200)
    handler.send_header("Content-Type", "video/mp2t")
    handler.send_header("Cache-Control", "no-store")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Connection", "close")
    handler.end_headers()
    handler.close_connection = True
    try:
        while True:
            chunk = proc.stdout.read(64 * 1024)
            if not chunk:
                break
            handler.wfile.write(chunk)
            handler.wfile.flush()
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass
    finally:
        try:
            proc.terminate()
        except Exception:
            pass
        try:
            proc.wait(timeout=2)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass


def handle_request(handler) -> bool:
    parsed = urllib.parse.urlsplit(handler.path)
    if parsed.path.startswith("/radio-tv/"):
        station = urllib.parse.unquote(parsed.path.split("/", 2)[2]).strip()
        stream_station(handler, station)
        return True
    if parsed.path.startswith("/radio-art/"):
        name = urllib.parse.unquote(parsed.path.split("/", 2)[2]).strip()
        station = name[:-4] if name.lower().endswith(".jpg") else name
        if station not in STATIONS:
            handler.send_error(404, "unknown radio station")
            return True
        data = make_art(station).read_bytes()
        handler.send_response(200)
        handler.send_header("Content-Type", "image/jpeg")
        handler.send_header("Content-Length", str(len(data)))
        handler.send_header("Cache-Control", "public, max-age=3600")
        handler.send_header("Access-Control-Allow-Origin", "*")
        handler.end_headers()
        handler.wfile.write(data)
        return True
    return False
