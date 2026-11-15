#!/usr/bin/env python3
"""Read-only time-labelled GCCX transition frames; no guessed programme boundary.

Usage: python gmcx_transition_probe.py --task kai_end
Produces indexed 8x6 contact sheets and report, or an explicit decode failure.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

TASKS = {
    # By 90,903s the Kai live studio remains; by 92,293s PC Genjin is visible.
    "kai_end": ("df1386fd-4bd1-41ae-ac64-743ff49a838f", 90880, 92480, 20),
    # The five-hour special occupies much of 76,560..93,960, verify what follows.
    "fivehour_end": ("e4f91158-8a0e-4c75-9fb4-eab36c247464", 91000, 101000, 125),
    # Lemmings is visible at 122,400s; source ends at 131,723s.
    "lemmings_end": ("5847ae05-893e-4ae8-986e-bf0abf888ecf", 121800, 131500, 125),
}
W,H = 256,144
COLS,ROWS=8,6
FRAME_BYTES=W*H*3

def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--task",required=True,choices=TASKS)
    args=parser.parse_args()
    ident,start,stop,step=TASKS[args.task]
    rec=json.loads(Path("kick_replay.json").read_text(encoding="utf-8"))
    candidates=[v for v in rec.get("vods",[]) if v.get("vod_id")==ident]
    if len(candidates)!=1 or candidates[0].get("playable") is not True:
        raise RuntimeError("Source VOD missing/unavailable")
    vod=candidates[0]
    if not vod.get("source_url") or int(vod.get("duration_seconds") or 0)<stop:
        raise RuntimeError("VOD source/duration did not match")
    dest=Path("gmcx_transition_probe_frames")/args.task
    dest.mkdir(parents=True,exist_ok=True)
    cmd=["ffmpeg","-nostdin","-hide_banner","-loglevel","error",
         "-rw_timeout","15000000","-ss",str(start),"-i",vod["source_url"],
         "-t",str(stop-start),"-an",
         "-vf",f"fps=1/{step},scale={W}:{H}:flags=area,format=rgb24",
         "-pix_fmt","rgb24","-f","rawvideo","pipe:1"]
    print("START",args.task,ident,start,stop,"step",step,flush=True)
    try:
        proc=subprocess.run(cmd,capture_output=True,timeout=330,check=False)
        raw=proc.stdout
        error=proc.stderr.decode("utf-8","replace")[-800:]
        count=len(raw)//FRAME_BYTES
        print("DECODE",proc.returncode,"frames",count,"error",error,flush=True)
        if count<10:
            raise RuntimeError("Insufficient actual video frames; no title/boundary claimed: "+error)
        font=ImageFont.load_default()
        pages=[]
        for page in range((count+COLS*ROWS-1)//(COLS*ROWS)):
            grid=Image.new("RGB",(COLS*(W+8),ROWS*(H+27)),(20,20,20))
            draw=ImageDraw.Draw(grid)
            for idx in range(page*COLS*ROWS,min(count,(page+1)*COLS*ROWS)):
                cell=idx-page*COLS*ROWS
                x=(cell%COLS)*(W+8)
                y=(cell//COLS)*(H+27)
                im=Image.frombytes("RGB",(W,H),raw[idx*FRAME_BYTES:(idx+1)*FRAME_BYTES])
                grid.paste(im,(x,y))
                timecode=start+idx*step
                draw.text((x+4,y+H+3),f"{timecode}s {timecode//3600:02}:{timecode//60%60:02}:{timecode%60:02}",font=font,fill="white")
            file=dest/f"page_{page+1:02d}.jpg"
            grid.save(file,quality=88)
            pages.append(str(file))
        report={"task":args.task,"vod_id":ident,"source_url":vod["source_url"],
                "start_seconds":start,"stop_seconds":stop,"sample_interval_seconds":step,
                "frames_observed":count,"pages":pages,"frame_time_estimate":True,
                "status":"frames_captured" if proc.returncode==0 else "partial_frames_capture",
                "warning":"These are sampled frames, not verified programme boundaries. Recheck any candidate at 1 fps before changing a replay split."}
        (dest/"index.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        return 0
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("Video decode timed out; no episode boundary is claimed") from exc

if __name__=="__main__":
    sys.exit(main())
