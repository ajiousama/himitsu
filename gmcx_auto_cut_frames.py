#!/usr/bin/env python3
"""Render a few small, time-ordered contact sheets for GCCX boundary debugging.

Diagnostic only. Never edits the catalogue or exports full episodes.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from kick_gmcx_chapters import _lowest_hls_variant

def main():
    vod = json.loads(Path("kick_replay.json").read_text(encoding="utf-8"))
    chapters = json.loads(Path("kick_gmcx_chapters.json").read_text(encoding="utf-8"))
    source = next(x for x in vod["vods"] if str(x.get("vod_id")) == "a640717e-6b99-4a10-a0d4-152d50117319")
    group = next(x for x in chapters["results"] if int(x.get("episode_start") or 0) == 387)
    url = _lowest_hls_variant(source["source_url"])
    Path("gmcx_cut_frames").mkdir(exist_ok=True)
    for ep in [388, 389, 390, 393, 394]:
        row = next(x for x in group["chapters"] if x.get("episode") == ep)
        center = int(row["start_seconds"])
        start = max(0, center - 40)
        out = f"gmcx_cut_frames/{ep}_from_{start}_step4sec.jpg"
        # 30 tiles: each ~4s apart, in chronological row-major order.
        vf = "fps=1/4,scale=160:90:flags=area,tile=10x3:padding=3:margin=5"
        cmd = ["ffmpeg","-nostdin","-hide_banner","-loglevel","error",
               "-rw_timeout","15000000","-ss",str(start),"-i",url,
               "-t","120","-an","-vf",vf,"-frames:v","1","-q:v","4","-y",out]
        try:
            proc=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=110,check=False)
            print(f"contact sheet #{ep}: rc={proc.returncode}, size={Path(out).stat().st_size if Path(out).exists() else 0}")
            if proc.returncode:
                print(proc.stderr.decode("utf-8","replace")[-500:])
        except (OSError,subprocess.TimeoutExpired) as exc:
            print(f"contact sheet #{ep} unavailable: {exc}")
if __name__ == "__main__":
    main()
