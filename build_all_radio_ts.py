#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
import os
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

RADIO = Path("radio.m3u")
FREEWIFI = Path("freewifi")
TS_BASE = "https://raw.githubusercontent.com/ajiousama/himitsu/radio-ts-assets"
RADIKO_AUDIO = "https://himitsu-six.vercel.app/api/radiko?station={sid}&stage=media"
UA = {"User-Agent": "Mozilla/5.0"}
W, H = 640, 360
JST = timezone(timedelta(hours=9))

NHK_AUDIO = {
    "nhk_r1_sapporo": "https://simul2.drdi.st.nhk/live/6/joined/master.m3u8",
    "nhk_fm_sapporo": "https://simul2.drdi.st.nhk/live/7/joined/master.m3u8",
    "nhk_r1_sendai": "https://simul2.drdi.st.nhk/live/8/joined/master.m3u8",
    "nhk_fm_sendai": "https://simul2.drdi.st.nhk/live/9/joined/master.m3u8",
    "nhk_r1_tokyo": "https://simul2.drdi.st.nhk/live/3/joined/master.m3u8",
    "nhk_fm_tokyo": "https://simul2.drdi.st.nhk/live/5/joined/master.m3u8",
    "nhk_r1_nagoya": "https://simul2.drdi.st.nhk/live/10/joined/master.m3u8",
    "nhk_fm_nagoya": "https://simul2.drdi.st.nhk/live/11/joined/master.m3u8",
    "nhk_r1_osaka": "https://simul2.drdi.st.nhk/live/12/joined/master.m3u8",
    "nhk_fm_osaka": "https://simul2.drdi.st.nhk/live/13/joined/master.m3u8",
    "nhk_r1_hiroshima": "https://simul2.drdi.st.nhk/live/14/joined/master.m3u8",
    "nhk_fm_hiroshima": "https://simul2.drdi.st.nhk/live/15/joined/master.m3u8",
    "nhk_r1_matsuyama": "https://simul2.drdi.st.nhk/live/16/joined/master.m3u8",
    "nhk_fm_matsuyama": "https://simul2.drdi.st.nhk/live/17/joined/master.m3u8",
    "nhk_r1_fukuoka": "https://simul2.drdi.st.nhk/live/18/joined/master.m3u8",
    "nhk_fm_fukuoka": "https://simul2.drdi.st.nhk/live/19/joined/master.m3u8",
}

ATTR_RE = re.compile(r'([A-Za-z0-9_-]+)="([^"]*)"')


def font_path(bold=False):
    candidates = [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc" if bold else "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for p in candidates:
        if Path(p).exists():
            return p
    raise RuntimeError("no usable font")


def font(size, bold=False):
    return ImageFont.truetype(font_path(bold), size=size)


def accent_for(key: str):
    d = hashlib.sha256(key.encode("utf-8")).digest()
    return (70 + d[0] % 145, 55 + d[1] % 135, 65 + d[2] % 140)


def mix(a, b, t):
    return tuple(round(a[i] * (1 - t) + b[i] * t) for i in range(3))


def fetch_radiko_logo(sid: str):
    url = f"https://radiko.jp/v2/static/station/logo/{urllib.parse.quote(sid, safe='')}/lrtrim/688x160.png"
    try:
        req = urllib.request.Request(url, headers=UA)
        with urllib.request.urlopen(req, timeout=15) as r:
            return Image.open(io.BytesIO(r.read())).convert("RGBA")
    except Exception as e:
        print(f"{sid}: logo fallback: {e}")
        return None


def make_card(key: str, name: str, radiko_sid: str | None, path: Path):
    accent = accent_for(key)
    im = Image.new("RGB", (W, H), "white")
    dr = ImageDraw.Draw(im)
    for y in range(H):
        t = y / (H - 1)
        dr.line((0, y, W, y), fill=mix((253, 253, 251), accent, 0.04 + 0.26 * t))

    dr.rectangle((0, 0, W, 60), fill=accent)
    title = name.replace("（ラジオ）", "").strip()
    try:
        dr.text((18, 11), title, font=font(27, True), fill="white")
    except Exception:
        dr.text((18, 11), key, font=font(27, True), fill="white")

    logo = fetch_radiko_logo(radiko_sid) if radiko_sid else None
    if logo is not None:
        logo.thumbnail((480, 130), Image.Resampling.LANCZOS)
        im.paste(logo, ((W - logo.width) // 2, 88 + (110 - logo.height) // 2), logo)
    else:
        main = "NHK RADIO 1" if "r1" in key else "NHK FM"
        f = font(54, True)
        box = dr.textbbox((0, 0), main, font=f)
        dr.text(((W - (box[2] - box[0])) / 2, 105), main, font=f, fill=accent)

    badge = "NOW PLAYING"
    bf = font(18, True)
    bb = dr.textbbox((0, 0), badge, font=bf)
    bw = bb[2] - bb[0] + 40
    bx = (W - bw) // 2
    dr.rounded_rectangle((bx, 222, bx + bw, 260), radius=19, fill=accent)
    dr.text((bx + 20, 230), badge, font=bf, fill="white")

    dr.rectangle((0, 300, W, H), fill=(12, 15, 19))
    footer = title if Path(font_path()).name.startswith("NotoSansCJK") else key
    dr.text((18, 314), footer, font=font(22, True), fill="white")
    im.save(path, "JPEG", quality=88, optimize=True)


def parse_radio_entries():
    lines = RADIO.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    entries = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.lstrip().startswith("#EXTINF:"):
            attrs = dict(ATTR_RE.findall(line))
            tvgid = attrs.get("tvg-id", "")
            name = line.split(",", 1)[1].strip() if "," in line else tvgid
            key = None
            radiko_sid = None
            audio = None
            if tvgid.startswith("radiko."):
                radiko_sid = tvgid.split(".", 1)[1]
                key = radiko_sid
                audio = RADIKO_AUDIO.format(sid=urllib.parse.quote(radiko_sid, safe=""))
            elif tvgid in NHK_AUDIO:
                key = tvgid
                audio = NHK_AUDIO[tvgid]
            if key:
                entries[key] = {
                    "key": key,
                    "tvgid": tvgid,
                    "name": name,
                    "radiko_sid": radiko_sid,
                    "audio": audio,
                }
            i += 2
            continue
        i += 1
    radiko_count = sum(1 for e in entries.values() if e["radiko_sid"])
    nhk_count = sum(1 for e in entries.values() if e["tvgid"] in NHK_AUDIO)
    if radiko_count < 100:
        raise RuntimeError(f"nationwide Radiko catalog too small: {radiko_count}")
    if nhk_count != len(NHK_AUDIO):
        raise RuntimeError(f"NHK catalog incomplete: {nhk_count}/{len(NHK_AUDIO)}")
    print(f"radio catalog: {radiko_count} Radiko + {nhk_count} NHK")
    return entries


def parse_media_entries(path: Path):
    rows = []
    dur = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#EXTINF:"):
            dur = float(line.split(":", 1)[1].split(",", 1)[0])
        elif line and not line.startswith("#") and dur is not None and line.endswith(".ts"):
            rows.append((dur, line.strip()))
            dur = None
    return rows


def load_or_build_video(entry, root: Path):
    key = entry["key"]
    out = root / key
    out.mkdir(parents=True, exist_ok=True)
    meta = out / "segments.json"
    rows = []
    if meta.exists():
        try:
            rows = [(float(x[0]), str(x[1])) for x in json.loads(meta.read_text(encoding="utf-8"))]
        except Exception:
            rows = []
    if not rows and (out / "video.m3u8").exists():
        rows = parse_media_entries(out / "video.m3u8")
    if rows and all((out / name).is_file() and (out / name).stat().st_size > 0 for _, name in rows):
        meta.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
        return key, rows, False

    for old in out.glob("seg_*.ts"):
        old.unlink()
    card = out / "card.jpg"
    make_card(key, entry["name"], entry["radiko_sid"], card)
    raw = out / "raw.m3u8"
    cmd = [
        "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
        "-loop", "1", "-framerate", "1", "-i", str(card),
        "-t", "7200",
        "-vf", "scale=320:180:force_original_aspect_ratio=decrease,pad=320:180:(ow-iw)/2:(oh-ih)/2",
        "-c:v", "libx264", "-profile:v", "baseline", "-level:v", "3.0",
        "-preset", "ultrafast", "-tune", "stillimage", "-crf", "38",
        "-pix_fmt", "yuv420p", "-r", "1", "-g", "10", "-keyint_min", "10", "-sc_threshold", "0", "-an",
        "-f", "hls", "-hls_segment_type", "mpegts", "-hls_time", "300", "-hls_list_size", "0",
        "-hls_flags", "independent_segments",
        "-hls_segment_filename", str(out / "seg_%03d.ts"), str(raw),
    ]
    subprocess.run(cmd, check=True)
    rows = parse_media_entries(raw)
    raw.unlink(missing_ok=True)
    if not rows:
        raise RuntimeError(f"{key}: no TS segments generated")
    meta.write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    return key, rows, True


def write_live_playlists(entry, root: Path, rows):
    out = root / entry["key"]
    start = datetime.now(JST) - timedelta(hours=1)
    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        "#EXT-X-INDEPENDENT-SEGMENTS",
        f"#EXT-X-TARGETDURATION:{math.ceil(max(d for d, _ in rows))}",
        "#EXT-X-MEDIA-SEQUENCE:0",
        "#EXT-X-START:TIME-OFFSET=3600.000,PRECISE=YES",
    ]
    stamp = start
    for duration, name in rows:
        lines.append(f"#EXT-X-PROGRAM-DATE-TIME:{stamp.isoformat(timespec='milliseconds')}")
        lines.append(f"#EXTINF:{duration:.3f},")
        lines.append(name)
        stamp += timedelta(seconds=duration)
    lines += ["#EXT-X-ENDLIST", ""]
    (out / "video.m3u8").write_text("\n".join(lines), encoding="utf-8")
    audio = entry["audio"]
    (out / "master.m3u8").write_text("\n".join([
        "#EXTM3U",
        "#EXT-X-VERSION:6",
        "#EXT-X-INDEPENDENT-SEGMENTS",
        f'#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="radio",NAME="{entry["key"]} radio",DEFAULT=YES,AUTOSELECT=YES,CHANNELS="2",URI="{audio}"',
        '#EXT-X-STREAM-INF:BANDWIDTH=180000,AVERAGE-BANDWIDTH=120000,RESOLUTION=320x180,FRAME-RATE=1.000,CODECS="avc1.42e01e,mp4a.40.5",AUDIO="radio",CLOSED-CAPTIONS=NONE',
        "video.m3u8",
        "",
    ]), encoding="utf-8")


def key_for_tvgid(tvgid: str, known: set[str]):
    if tvgid in NHK_AUDIO:
        return tvgid
    if tvgid == "radiko.JOBK":
        return "nhk_r1_osaka"
    if tvgid == "radiko.JOZK":
        return "nhk_r1_matsuyama"
    if tvgid.startswith("radiko."):
        sid = tvgid.split(".", 1)[1]
        if sid in known:
            return sid
    return None


def rewrite_playlist(path: Path, known: set[str], section_only=False):
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    lines = text.splitlines()
    start = 0
    end = len(lines)
    if section_only:
        starts = [i for i, x in enumerate(lines) if x.strip() == "## ラジオ"]
        ends = [i for i, x in enumerate(lines) if x.strip() == "## 愛媛CATV"]
        if not starts or not ends or ends[0] <= starts[0]:
            raise RuntimeError("freewifi radio section boundaries not found")
        start, end = starts[0], ends[0]

    changed = 0
    matched = 0
    i = start
    while i < end:
        line = lines[i]
        if line.lstrip().startswith("#EXTINF:") and i + 1 < len(lines):
            attrs = dict(ATTR_RE.findall(line))
            key = key_for_tvgid(attrs.get("tvg-id", ""), known)
            if key:
                matched += 1
                new = f"{TS_BASE}/{key}/master.m3u8"
                if lines[i + 1].strip() != new:
                    lines[i + 1] = new
                    changed += 1
            i += 2
            continue
        i += 1

    if section_only and matched < 16:
        raise RuntimeError(f"FreeWiFi radio match count too small: {matched}")
    if not section_only and matched < 116:
        raise RuntimeError(f"radio.m3u match count too small: {matched}")
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"{path}: matched={matched} changed={changed}")
    return matched, changed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--assets-root", required=True)
    ap.add_argument("--workers", type=int, default=3)
    args = ap.parse_args()

    if shutil.which("ffmpeg") is None:
        raise SystemExit("ffmpeg is required")

    root = Path(args.assets_root)
    root.mkdir(parents=True, exist_ok=True)
    entries = parse_radio_entries()

    results = {}
    built = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = {ex.submit(load_or_build_video, e, root): k for k, e in entries.items()}
        for fut in as_completed(futs):
            key, rows, was_built = fut.result()
            results[key] = rows
            built += int(was_built)
            print(f"{key}: {'built' if was_built else 'reused'}")

    for key, entry in entries.items():
        write_live_playlists(entry, root, results[key])

    (root / "stations.json").write_text(
        json.dumps({k: {"name": v["name"], "audio": v["audio"]} for k, v in entries.items()}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    known = set(entries)
    rewrite_playlist(RADIO, known, section_only=False)
    rewrite_playlist(FREEWIFI, known, section_only=True)
    print(f"all-radio TS ready: stations={len(entries)} newly_built={built}")


if __name__ == "__main__":
    main()
