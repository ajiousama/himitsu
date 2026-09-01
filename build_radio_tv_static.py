#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
import urllib.parse
from pathlib import Path

CARD_DIR = Path("vercel-radiko/radio-video-assets/cards")
OUT = Path("radio-tv-static")
RAW_BASE = "https://raw.githubusercontent.com/ajiousama/himitsu/main/radio-tv-static"
RADIKO_BASE = "https://himitsu-six.vercel.app/api/radiko"

# key: audio source config. The key also matches the approved card JPEG name.
STATIONS = {
    "nhk_r1_osaka": {"nhk": "https://simul2.drdi.st.nhk/live/12/joined/master.m3u8"},
    "nhk_fm_osaka": {"nhk": "https://simul2.drdi.st.nhk/live/13/joined/master.m3u8"},
    "nhk_r1_matsuyama": {"nhk": "https://simul2.drdi.st.nhk/live/16/joined/master.m3u8"},
    "nhk_fm_matsuyama": {"nhk": "https://simul2.drdi.st.nhk/live/17/joined/master.m3u8"},
    "JOEU-FM": {"radiko": "JOEU-FM"},
    "RNB": {"radiko": "RNB"},
    "ABC": {"radiko": "ABC"},
    "CCL": {"radiko": "CCL"},
    "802": {"radiko": "802"},
    "FMO": {"radiko": "FMO"},
    "MBS": {"radiko": "MBS"},
    "OBC": {"radiko": "OBC"},
    "KBS": {"radiko": "KBS"},
    "ALPHA-STATION": {"radiko": "ALPHA-STATION"},
    "E-RADIO": {"radiko": "E-RADIO"},
    "CRK": {"radiko": "CRK"},
}


def audio_url(cfg: dict[str, str]) -> str:
    if "radiko" in cfg:
        sid = urllib.parse.quote(cfg["radiko"], safe="")
        return f"{RADIKO_BASE}?station={sid}&stage=media"
    # NHK blocks the US-hosted GitHub Actions runner. Keep the same direct
    # Japan-facing HLS URL already used successfully by FreeWiFi instead of
    # probing it from CI.
    return cfg["nhk"]


def build_video(key: str, card: Path, outdir: Path) -> None:
    if outdir.exists():
        shutil.rmtree(outdir)
    outdir.mkdir(parents=True)
    playlist = outdir / "video.m3u8"
    segment_pattern = outdir / "seg_%02d.m4s"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-loop", "1", "-framerate", "1/3600", "-i", str(card),
        "-t", "86400",
        "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage",
        "-crf", "34", "-pix_fmt", "yuv420p",
        "-r", "1/3600", "-g", "1", "-an",
        "-f", "hls", "-hls_segment_type", "fmp4",
        "-hls_time", "3600", "-hls_list_size", "0",
        "-hls_fmp4_init_filename", "init.mp4",
        "-hls_segment_filename", str(segment_pattern),
        str(playlist),
    ]
    subprocess.run(cmd, check=True)
    segments = sorted(outdir.glob("seg_*.m4s"))
    if len(segments) != 24:
        raise RuntimeError(f"{key}: expected 24 hourly segments, got {len(segments)}")


def write_master(audio: str, outdir: Path) -> None:
    body = "\n".join([
        "#EXTM3U",
        "#EXT-X-VERSION:7",
        "#EXT-X-INDEPENDENT-SEGMENTS",
        f'#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="radio",NAME="Radio",DEFAULT=YES,AUTOSELECT=YES,URI="{audio}"',
        '#EXT-X-STREAM-INF:BANDWIDTH=320000,AVERAGE-BANDWIDTH=220000,RESOLUTION=640x360,AUDIO="radio",CLOSED-CAPTIONS=NONE',
        "video.m3u8",
        "",
    ])
    (outdir / "master.m3u8").write_text(body, encoding="utf-8")


def main() -> None:
    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg is required")
    missing = [key for key in STATIONS if not (CARD_DIR / f"{key}.jpg").exists()]
    if missing:
        raise SystemExit("approved radio cards missing: " + ", ".join(missing))

    manifest: dict[str, dict[str, str]] = {}
    for key, cfg in STATIONS.items():
        card = CARD_DIR / f"{key}.jpg"
        outdir = OUT / key
        build_video(key, card, outdir)
        audio = audio_url(cfg)
        write_master(audio, outdir)
        manifest[key] = {
            "master": f"{RAW_BASE}/{urllib.parse.quote(key, safe='')}/master.m3u8",
            "audio": audio,
        }
        print(f"built {key}: 24h static video + live audio")

    OUT.mkdir(exist_ok=True)
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"built {len(STATIONS)} radio channels")


if __name__ == "__main__":
    main()
