#!/usr/bin/env python3
"""Small, reviewable contact sheets for unresolved GCCX KICK video chapters.

Frames are actual decoded video images. No guesses, no playlist edits.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path

from gmcx_unknown_title_probe import eligible_chunks

TARGET = Path("gmcx_unknown_title_contact_frames")
OFFSETS = (35, 155, 600, 1800)


def grab(vod_id: str, source: str, second: int, path: Path) -> str:
    variants = (
        (source, second, "source"),
        (f"https://kick-resolver-production.up.railway.app/kick"
         f"?vod={vod_id}&start={second}&duration=8", 1, "resolver"),
    )
    for url, offset, name in variants:
        try:
            cmd = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                   "-rw_timeout", "8000000", "-ss", str(offset), "-i", url,
                   "-frames:v", "1", "-y", str(path)]
            result = subprocess.run(cmd, capture_output=True,
                                    timeout=17, check=False)
            if result.returncode == 0 and path.is_file() and path.stat().st_size > 2048:
                return name
        except (OSError, subprocess.TimeoutExpired):
            continue
    return "frame_unavailable"


def sheet(captures: list[tuple[Path,str]], destination: Path) -> None:
    from PIL import Image, ImageDraw
    width, height = 640, 390
    grid = Image.new("RGB", (width*2, height*2), "#202020")
    draw = ImageDraw.Draw(grid)
    for i,(path,label) in enumerate(captures):
        x,y=(i%2)*width,(i//2)*height
        draw.text((x+8,y+6),label,fill="white")
        if path.is_file():
            with Image.open(path) as frame:
                copied=frame.convert("RGB")
                copied.thumbnail((620,350))
                grid.paste(copied,(x+(width-copied.width)//2,y+32+(350-copied.height)//2))
    grid.save(destination,quality=84,subsampling=0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-chunks",type=int,default=12)
    parser.add_argument("--budget-seconds",type=int,default=540)
    args=parser.parse_args()
    TARGET.mkdir(exist_ok=True)
    rows=[]
    finish=time.monotonic()+max(60,args.budget_seconds)
    for vod_id, start, length, source in eligible_chunks():
        if len(rows)>=max(1,args.max_chunks) or time.monotonic()>finish-50:
            break
        captures=[]
        statuses=[]
        for offset in OFFSETS:
            if time.monotonic()>finish-30:
                break
            actual=start+min(length-15,offset)
            image=TARGET/f"{vod_id[:8]}_{start:06d}_{offset:04d}.png"
            status=grab(vod_id,source,actual,image)
            statuses.append({"second":actual,"status":status})
            captures.append((image,f"{vod_id[:8]} / {actual}s / {status}"))
        if captures:
            output=TARGET/f"sheet_{vod_id[:8]}_{start:06d}.jpg"
            try:
                sheet(captures,output)
            except ImportError:
                print("Pillow unavailable")
                return 1
        rows.append({"vod_id":vod_id,"start_seconds":start,"captures":statuses})
        print("GCCX_FRAME",vod_id[:8],start,[x["status"] for x in statuses],flush=True)
    report={"generated_at":datetime.now(timezone.utc).isoformat(),
            "label":"GCCX actual video frames; NOT episode identification",
            "chunks":rows}
    (TARGET/"index.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("GCCX_VIDEO_FRAME_REVIEW",len(rows),"chunks",flush=True)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
