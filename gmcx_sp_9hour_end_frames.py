#!/usr/bin/env python3
"""Second-resolution GCCX 2007 Christmas live-SP ending review.

2007-12-24 20:00 to 2007-12-25 05:00 is the OFFICIAL 9-hour broadcast
schedule, not proof of the source clip's transition second. Scan around
the 9-hour point in the 2026 KICK replay, frame by frame. No VOD5 edits.
"""
from __future__ import annotations
import json
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from kick_gmcx_chapters import _lowest_hls_variant

VOD_ID="df1386fd-4bd1-41ae-ac64-743ff49a838f"
START_OBSERVED=59152
NOMINAL_END=START_OBSERVED+9*3600
START=NOMINAL_END-140
STOP=NOMINAL_END+160
WIDTH,HEIGHT=192,108
FRAME_SIZE=WIDTH*HEIGHT*3
PER_PAGE=50
OUT=Path("gmcx_sp_9hour_end_frames")

def main()->int:
    replay=json.loads(Path("kick_replay.json").read_text(encoding="utf-8"))
    source=next((v for v in replay.get("vods",[]) if v.get("vod_id")==VOD_ID),None)
    if not source or not source.get("playable") or not source.get("source_url"):
        raise RuntimeError("GCCX source absent or unavailable")
    url=_lowest_hls_variant(str(source["source_url"]))
    cmd=["ffmpeg","-nostdin","-hide_banner","-loglevel","error",
        "-rw_timeout","15000000","-ss",str(START),"-i",url,
        "-t",str(STOP-START),"-an",
        "-vf",f"fps=1,scale={WIDTH}:{HEIGHT}:flags=area,format=rgb24",
        "-pix_fmt","rgb24","-f","rawvideo","pipe:1"]
    proc=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                        timeout=170,check=False)
    raw=proc.stdout
    n=len(raw)//FRAME_SIZE
    if proc.returncode or n<120:
        raise RuntimeError("insufficient decoded 9h-ending frames "+str(n)+" "+
                           proc.stderr.decode("utf-8","replace")[-250:])
    OUT.mkdir(exist_ok=True)
    pages=[]
    font=ImageFont.load_default()
    for page_idx in range((n+PER_PAGE-1)//PER_PAGE):
        sheet=Image.new("RGB",(10*(WIDTH+5),5*(HEIGHT+24)),(12,12,12))
        draw=ImageDraw.Draw(sheet)
        for k in range(PER_PAGE):
            index=page_idx*PER_PAGE+k
            if index>=n:break
            frame=Image.frombytes("RGB",(WIDTH,HEIGHT),raw[index*FRAME_SIZE:(index+1)*FRAME_SIZE])
            x=(k%10)*(WIDTH+5)
            y=(k//10)*(HEIGHT+24)
            sheet.paste(frame,(x,y))
            secs=START+index
            draw.text((x+3,y+HEIGHT+4),f"t={secs} (+{secs-START_OBSERVED})",font=font,fill="white")
        path=OUT/f"page_{page_idx+1:02d}.jpg"
        sheet.save(path,quality=87,optimize=True)
        pages.append({"file":str(path),"first_second":START+page_idx*PER_PAGE,
                      "last_second":min(STOP-1,START+(page_idx+1)*PER_PAGE-1)})
    index={"mode":"read_only_9h_program_end_visual_review",
           "original_broadcast_scheduled_nine_hours":True,
           "source_id":VOD_ID,"start_observed":START_OBSERVED,
           "nominal_end":NOMINAL_END,"start_seconds":START,
           "stop_seconds":STOP,"decoded_frames":n,
           "verified_end_seconds":None,"pages":pages}
    (OUT/"index.json").write_text(json.dumps(index,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("GCCX_9H_END "+json.dumps(index,ensure_ascii=False),flush=True)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
