#!/usr/bin/env python3
"""Read-only parallel visual review of UNLABELED KICK/GCCX VOD navigation clips.

This script intentionally does not assign a title or change any playlist.
It only returns contact sheets and traceable timestamp/source evidence.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from PIL import Image, ImageDraw

RESOLVER = "https://kick-resolver-production.up.railway.app/kick?vod="
SAMPLE_OFFSETS = (35, 155, 600, 1800)  # new 2026-11-24 recordings / expanded 11-22 VOD


def unresolved_from_vod5():
    vods = json.loads(Path("kick_replay.json").read_text(encoding="utf-8")).get("vods", [])
    valid = {
        v["vod_id"]: v for v in vods
        if v.get("ready_for_publish") is True
        and v.get("playable") is True
        and str(v.get("tvg_id") or "").startswith("kick.gccx")
        and v.get("source_url")
    }
    lines = Path("VOD5").read_text(encoding="utf-8-sig").splitlines()
    found = []
    seen = set()
    for i in range(len(lines) - 1):
        label = lines[i]
        if not (label.startswith("#EXTINF") and "仮チャプター" in label
                and 'group-title="KICK系VOD"' in label):
            continue
        qs = parse_qs(urlsplit(lines[i + 1].strip()).query)
        vod = qs.get("vod", [""])[0]
        if vod not in valid:
            continue
        try:
            start = int(qs["start"][0])
            duration = int(qs["duration"][0])
        except (KeyError, ValueError, TypeError, IndexError):
            continue
        key = (vod, start)
        if key in seen or start < 0 or duration < 300:
            continue
        seen.add(key)
        found.append({
            "vod_id": vod, "start_seconds": start, "duration_seconds": duration,
            "source_url": valid[vod]["source_url"],
            "old_label": label.split(",", 1)[-1]
        })
    # Do not waste the second-pass job on titles identified by actual video
    # in the first round but not yet published into VOD5.
    evidence = json.loads(Path("gmcx_frame_identified_titles.json").read_text(encoding="utf-8"))
    named = {(str(x.get("source_vod_id")), int(x.get("start_seconds") or 0))
             for x in evidence.get("entries", []) if isinstance(x, dict)}
    found = [row for row in found
             if (row["vod_id"], row["start_seconds"]) not in named]
    # Prefer oldest, potentially expiring recordings. Shard deterministically.
    dates = {str(v.get("vod_id")): str(v.get("created_at") or "") for v in vods}
    found.sort(key=lambda row: (dates.get(row["vod_id"], ""), row["start_seconds"]))
    return found


def capture(vod, source, second, destination):
    sources = (
        (source, second, "source"),
        (f"{RESOLVER}{vod}&start={second}&duration=8", 1, "resolver"),
    )
    for url, seek, kind in sources:
        cmd = [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-rw_timeout", "8000000", "-ss", str(seek), "-i", url,
            "-frames:v", "1", "-y", str(destination)
        ]
        try:
            run = subprocess.run(cmd, capture_output=True, timeout=21)
            if run.returncode == 0 and destination.exists() and destination.stat().st_size > 2048:
                return kind
        except (OSError, subprocess.TimeoutExpired):
            pass
    return "unavailable"


def make_sheet(pictures, path):
    w, h = 640, 390
    canvas = Image.new("RGB", (w * 2, h * 2), "#222222")
    draw = ImageDraw.Draw(canvas)
    for index, (file, caption) in enumerate(pictures):
        x, y = (index % 2) * w, (index // 2) * h
        draw.text((x + 7, y + 5), caption, fill="white")
        if file.exists():
            try:
                with Image.open(file) as img:
                    img = img.convert("RGB")
                    img.thumbnail((w - 14, h - 36))
                    canvas.paste(img, (x + (w - img.width) // 2, y + 28 + (h - 36 - img.height) // 2))
            except OSError:
                pass
    canvas.save(path, quality=85)


def inspect_clip(row, folder):
    vod = row["vod_id"]
    start = row["start_seconds"]
    duration = row["duration_seconds"]
    shots = []
    statuses = []
    for off in SAMPLE_OFFSETS:
        at = start + min(max(0, duration - 15), off)
        path = folder / f"{vod[:8]}_{start:06d}_{off:04d}.png"
        status = capture(vod, row["source_url"], at, path)
        shots.append((path, f"{vod[:8]} / {at}s / {status}"))
        statuses.append({"second": at, "status": status})
    sheet = f"sheet_{vod[:8]}_{start:06d}.jpg"
    make_sheet(shots, folder / sheet)
    return {**row, "samples": statuses, "sheet": sheet,
            "success_frames": sum(x["status"] != "unavailable" for x in statuses)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--shard", type=int, required=True)
    p.add_argument("--shards", type=int, default=12)
    p.add_argument("--workers", type=int, default=2)
    p.add_argument("--max-chunks", type=int, default=20)
    args = p.parse_args()
    if not 0 <= args.shard < args.shards:
        p.error("shard must be in [0,shards)")
    all_pending = unresolved_from_vod5()
    chosen = [row for idx, row in enumerate(all_pending)
              if idx % args.shards == args.shard][:args.max_chunks]
    folder = Path("gmcx_bulk_title_frames")
    folder.mkdir(exist_ok=True)
    rows = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        tasks = [pool.submit(inspect_clip, row, folder) for row in chosen]
        for future in concurrent.futures.as_completed(tasks):
            result = future.result()
            rows.append(result)
            print("GMCX_FRAME", result["vod_id"][:8], result["start_seconds"],
                  result["success_frames"], flush=True)
    rows.sort(key=lambda x: (x["vod_id"], x["start_seconds"]))
    index = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "shard": args.shard, "shards": args.shards,
        "all_pending_count": len(all_pending), "selected_count": len(chosen),
        "completed_count": len(rows), "clips": rows,
        "warning": "Video stills for human verification; no programme boundaries are claimed.",
    }
    (folder / "index.json").write_text(
        json.dumps(index, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("GMCX_BULK_REVIEW", args.shard, len(rows), len(all_pending), flush=True)


if __name__ == "__main__":
    main()
