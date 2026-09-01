#!/usr/bin/env python3
from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path("vercel-radiko/radio-video-assets")
W, H = 640, 360

# key: (display name, frequency, accent RGB, Radiko logo id)
STATIONS = {
    "nhk_r1_osaka": ("NHKラジオ第1（大阪）", "AM 666kHz / FM 85.1MHz", (204, 43, 43), None),
    "nhk_fm_osaka": ("NHK-FM（大阪）", "FM 88.1MHz", (73, 145, 48), None),
    "nhk_r1_matsuyama": ("NHKラジオ第1（松山）", "AM 963kHz / FM 90.8MHz", (204, 43, 43), None),
    "nhk_fm_matsuyama": ("NHK-FM（松山）", "FM 87.7MHz", (73, 145, 48), None),
    "JOEU-FM": ("FM愛媛", "FM 79.7MHz", (239, 112, 30), "JOEU-FM"),
    "RNB": ("RNB南海放送", "AM 1116kHz / FM 91.7MHz", (32, 99, 184), "RNB"),
    "ABC": ("ABCラジオ", "AM 1008kHz / FM 93.3MHz", (232, 81, 28), "ABC"),
    "CCL": ("FM COCOLO", "FM 76.5MHz", (104, 67, 146), "CCL"),
    "802": ("FM802", "FM 80.2MHz", (38, 76, 175), "802"),
    "FMO": ("FM大阪", "FM 85.1MHz", (34, 127, 183), "FMO"),
    "MBS": ("MBSラジオ", "AM 1179kHz / FM 90.6MHz", (92, 164, 42), "MBS"),
    "OBC": ("OBCラジオ大阪", "AM 1314kHz / FM 91.9MHz", (218, 48, 43), "OBC"),
    "KBS": ("KBS京都ラジオ", "AM 1143kHz / FM 94.9MHz", (44, 103, 178), "KBS"),
    "ALPHA-STATION": ("α-STATION FM KYOTO", "FM 89.4MHz", (152, 69, 164), "ALPHA-STATION"),
    "E-RADIO": ("e-radio FM滋賀", "FM 77.0MHz", (36, 143, 196), "E-RADIO"),
    "CRK": ("ラジオ関西", "AM 558kHz / FM 91.1MHz", (42, 91, 171), "CRK"),
}


def font_path(bold=False):
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    raise RuntimeError("No usable font found")


def font(size, bold=False):
    return ImageFont.truetype(font_path(bold), size=size)


def fetch_logo(sid):
    if not sid:
        return None
    url = f"https://radiko.jp/v2/static/station/logo/{urllib.parse.quote(sid, safe='')}/lrtrim/688x160.png"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            return Image.open(io.BytesIO(r.read())).convert("RGBA")
    except Exception as e:
        print(f"logo fallback {sid}: {e}")
        return None


def mix(a, b, t):
    return tuple(round(a[i] * (1-t) + b[i] * t) for i in range(3))


def centered(draw, text, y, ft, fill):
    box = draw.textbbox((0, 0), text, font=ft)
    draw.text(((W - (box[2]-box[0]))/2, y), text, font=ft, fill=fill)


def make_card(key, display, freq, accent, logo_sid, path):
    im = Image.new("RGB", (W, H), "white")
    dr = ImageDraw.Draw(im)
    for y in range(H):
        t = y / (H - 1)
        dr.line((0, y, W, y), fill=mix((253,253,251), accent, 0.04 + 0.26*t))

    # Header strip.
    dr.rectangle((0, 0, W, 58), fill=accent)
    dr.text((18, 10), display, font=font(29, True), fill="white")

    # Soft city/equalizer motif along the lower half, matching the approved card style.
    for i in range(48):
        x = i * 14
        bar = 18 + ((i * 31 + len(key) * 11) % 88)
        dr.rounded_rectangle((x, 290-bar, x+8, 290), radius=2, fill=mix(accent, (255,255,255), 0.22))
    for i in range(18):
        x = 6 + i*37
        bh = 18 + ((i*23 + len(display)*7) % 55)
        dr.rectangle((x, 290-bh, x+25, 290), fill=mix(accent, (255,255,255), 0.43))

    logo = fetch_logo(logo_sid)
    if logo is not None:
        logo.thumbnail((430, 105), Image.Resampling.LANCZOS)
        im.paste(logo, ((W-logo.width)//2, 78 + (95-logo.height)//2), logo)
    else:
        main = "NHK ラジオ第1" if "r1" in key else "NHK FM"
        centered(dr, main, 87, font(56, True), accent)

    centered(dr, freq, 176, font(22, True), mix(accent, (0,0,0), 0.35))

    badge = "NOW PLAYING"
    bf = font(18, True)
    bb = dr.textbbox((0, 0), badge, font=bf)
    bw = bb[2]-bb[0]+38
    bx = (W-bw)//2
    dr.rounded_rectangle((bx, 214, bx+bw, 250), radius=18, fill=accent)
    dr.text((bx+19, 221), badge, font=bf, fill="white")

    # Black station footer.
    dr.rectangle((0, 300, W, H), fill=(12, 15, 19))
    dr.text((18, 310), display, font=font(23, True), fill="white")
    fb = dr.textbbox((0, 0), freq, font=font(15))
    dr.text((W-(fb[2]-fb[0])-18, 337), freq, font=font(15), fill=(225,230,235))

    im.save(path, "JPEG", quality=91, optimize=True)


def build_segment(image_path, tempdir, key):
    d = Path(tempdir) / key
    d.mkdir(parents=True, exist_ok=True)
    playlist = d / "v.m3u8"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-loop", "1", "-framerate", "25", "-i", str(image_path),
        "-t", "5", "-c:v", "libx264", "-preset", "slow", "-tune", "stillimage",
        "-crf", "36", "-pix_fmt", "yuv420p", "-r", "25", "-g", "125", "-an",
        "-f", "hls", "-hls_segment_type", "fmp4", "-hls_time", "5", "-hls_list_size", "0",
        "-hls_fmp4_init_filename", "init.mp4", str(playlist),
    ]
    subprocess.run(cmd, check=True)
    return d / "init.mp4", d / "v0.m4s"


def main():
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg is required")
    OUT.mkdir(parents=True, exist_ok=True)
    cards = OUT / "cards"
    cards.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        shared_init = None
        for key, (display, freq, accent, logo_sid) in STATIONS.items():
            jpg = cards / f"{key}.jpg"
            make_card(key, display, freq, accent, logo_sid, jpg)
            init, seg = build_segment(jpg, tmp, key)
            if shared_init is None:
                shared_init = init.read_bytes()
                (OUT / "init.mp4").write_bytes(shared_init)
            elif init.read_bytes() != shared_init:
                raise RuntimeError(f"fMP4 init differs for {key}")
            (OUT / f"{key}.m4s").write_bytes(seg.read_bytes())
            print(f"built {key}: {(OUT / f'{key}.m4s').stat().st_size} bytes")
    (OUT / "manifest.txt").write_text("timescale=12800\nsegment_seconds=5\n", encoding="ascii")
    print(f"built {len(STATIONS)} radio video cards")


if __name__ == "__main__":
    main()
