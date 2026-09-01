#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path

CARD_DIR = Path("vercel-radiko/radio-video-assets/cards")
OUT = Path("radio-tv-static")
RAW_BASE = "https://raw.githubusercontent.com/ajiousama/himitsu/main/radio-tv-static"
RADIKO_BASE = "https://himitsu-six.vercel.app/api/radiko"
JST = timezone(timedelta(hours=9))

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
    return cfg["nhk"]


def build_segments(key: str, card: Path, outdir: Path) -> None:
    segments = sorted(outdir.glob("seg_*.m4s")) if outdir.exists() else []
    if (outdir / "init.mp4").exists() and len(segments) == 24:
        return

    if outdir.exists():
        shutil.rmtree(outdir)
    outdir.mkdir(parents=True)
    segment_pattern = outdir / "seg_%02d.m4s"
    playlist = outdir / "ffmpeg-video.m3u8"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-loop", "1", "-framerate", "1/3600", "-i", str(card),
        "-t", "86400",
        "-c:v", "libx264", "-profile:v", "high", "-level:v", "3.0",
        "-preset", "veryfast", "-tune", "stillimage", "-crf", "34",
        "-pix_fmt", "yuv420p", "-r", "1/3600", "-g", "1", "-an",
        "-f", "hls", "-hls_segment_type", "fmp4",
        "-hls_time", "3600", "-hls_list_size", "0",
        "-hls_fmp4_init_filename", "init.mp4",
        "-hls_segment_filename", str(segment_pattern),
        str(playlist),
    ]
    subprocess.run(cmd, check=True)
    playlist.unlink(missing_ok=True)
    segments = sorted(outdir.glob("seg_*.m4s"))
    if len(segments) != 24:
        raise RuntimeError(f"{key}: expected 24 hourly segments, got {len(segments)}")


def write_video_playlist(outdir: Path, now: datetime) -> None:
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    offset = max(0.0, min(86399.0, (now - midnight).total_seconds()))
    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:7",
        "#EXT-X-TARGETDURATION:3600",
        "#EXT-X-MEDIA-SEQUENCE:0",
        f"#EXT-X-START:TIME-OFFSET={offset:.3f},PRECISE=YES",
        '#EXT-X-MAP:URI="init.mp4"',
    ]
    for hour in range(24):
        stamp = midnight + timedelta(hours=hour)
        lines.append(f"#EXT-X-PROGRAM-DATE-TIME:{stamp.isoformat(timespec='milliseconds')}")
        lines.append("#EXTINF:3600.000,")
        lines.append(f"seg_{hour:02d}.m4s")
    lines.extend(["#EXT-X-ENDLIST", ""])
    (outdir / "video.m3u8").write_text("\n".join(lines), encoding="utf-8")


def write_master(audio: str, outdir: Path) -> None:
    body = "\n".join([
        "#EXTM3U",
        "#EXT-X-VERSION:7",
        "#EXT-X-INDEPENDENT-SEGMENTS",
        f'#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="radio",NAME="Radio",DEFAULT=YES,AUTOSELECT=YES,CHANNELS="2",URI="{audio}"',
        '#EXT-X-STREAM-INF:BANDWIDTH=320000,AVERAGE-BANDWIDTH=220000,RESOLUTION=640x360,CODECS="avc1.64001e,mp4a.40.2",AUDIO="radio",CLOSED-CAPTIONS=NONE',
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

    now = datetime.now(JST)
    manifest: dict[str, dict[str, str]] = {}
    for key, cfg in STATIONS.items():
        card = CARD_DIR / f"{key}.jpg"
        outdir = OUT / key
        outdir.mkdir(parents=True, exist_ok=True)
        build_segments(key, card, outdir)
        write_video_playlist(outdir, now)
        audio = audio_url(cfg)
        write_master(audio, outdir)
        manifest[key] = {
            "master": f"{RAW_BASE}/{urllib.parse.quote(key, safe='')}/master.m3u8",
            "audio": audio,
        }
        print(f"synced {key} at {now.isoformat()}")

    OUT.mkdir(exist_ok=True)
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"updated {len(STATIONS)} radio channels")


if __name__ == "__main__":
    main()
