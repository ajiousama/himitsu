#!/usr/bin/env python3
"""Small contact sheets around potential GCCX openings for human video review.

Read-only and rate-limit conscious. Does not publish episodes or full video.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from kick_gmcx_chapters import _lowest_hls_variant

TARGETS = [
    ("df1386fd", 3480, "control_episode46"),
    ("df1386fd", 59096, "tail_candidate"),
    ("5847ae05", 3546, "nov11_candidate"),
]

def main():
    vods = json.loads(Path("kick_replay.json").read_text(encoding="utf-8")).get("vods", [])
    out_dir = Path("gmcx_unresolved_frames")
    out_dir.mkdir(exist_ok=True)
    for prefix, seconds, tag in TARGETS:
        source = next((x for x in vods if str(x.get("vod_id") or "").startswith(prefix)), None)
        if not source or not source.get("playable") or not source.get("source_url"):
            print("FRAME_REVIEW",tag,"unavailable",flush=True)
            continue
        try:
            url = _lowest_hls_variant(str(source["source_url"]))
            # A 60-sec contact sheet, sampled every 2sec. Read from left to
            # right, row by row. Midpoint at tile 16 (candidate start).
            target = out_dir / f"{tag}_{seconds}.jpg"
            cmd = [
                "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                "-rw_timeout", "15000000",
                "-ss", str(max(0, seconds-30)), "-i", url,
                "-t", "60", "-an",
                "-vf", "fps=1/2,scale=320:180:flags=area,tile=6x5:padding=3:margin=3",
                "-frames:v", "1", "-q:v", "4", "-y", str(target),
            ]
            proc = subprocess.run(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                timeout=95, check=False
            )
            print("FRAME_REVIEW",tag,"rc",proc.returncode,
                  "bytes",target.stat().st_size if target.exists() else 0,
                  "error",proc.stderr.decode("utf-8","replace")[-200:],flush=True)
        except (OSError, subprocess.TimeoutExpired) as exc:
            print("FRAME_REVIEW",tag,"failed",str(exc)[:200],flush=True)
        time.sleep(2)

if __name__ == "__main__":
    main()
