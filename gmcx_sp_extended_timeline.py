#!/usr/bin/env python3
"""Broad chronological check for where GCCX's long special actually ends.

Produces visual evidence at +3h through +14h from the observed introduction.
The three-hour marketing title is not assumed to equal the true runtime.
No changes to video files or published M3U.
"""
from __future__ import annotations
import json
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from kick_gmcx_chapters import _lowest_hls_variant

VOD_ID="df1386fd-4bd1-41ae-ac64-743ff49a838f"
OPENING_SECONDS=59152
# Intervals become wider once it is clear the nominal three-hour endpoint
# is still the same live game challenge.
OFFSETS_MINUTES=(180,195,210,225,240,255,270,300,330,360,420,480,540,600,720,840)
WIDTH, HEIGHT = 256,144
OUT=Path("gmcx_sp_extended_timeline")
COLS=4
PER_PAGE=8

def sample(url,center):
    # Three tiny frames spanning 24 seconds in chronological order
    start=max(0,center-12)
    cmd=["ffmpeg","-nostdin","-hide_banner","-loglevel","error",
         "-rw_timeout","15000000","-ss",str(start),"-i",url,
         "-t","24","-an",
         f"-vf","fps=1/8,scale={WIDTH}:{HEIGHT}:flags=area,format=rgb24",
         "-pix_fmt","rgb24","-f","rawvideo","pipe:1"]
    try:
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=50,check=False)
        if p.returncode or len(p.stdout)<WIDTH*HEIGHT*3:
            return [],p.stderr.decode("utf-8","replace")[-200:]
        frames=[]
        frame_len=WIDTH*HEIGHT*3
        for i in range(min(3,len(p.stdout)//frame_len)):
            frames.append(Image.frombytes("RGB",(WIDTH,HEIGHT),
                p.stdout[i*frame_len:(i+1)*frame_len]))
        return frames,None
    except (OSError,subprocess.TimeoutExpired) as e:
        return [],str(e)[:200]

def main():
    data=json.loads(Path("kick_replay.json").read_text(encoding="utf-8"))
    vod=next((x for x in data.get("vods",[]) if x.get("vod_id")==VOD_ID),None)
    if not vod or not vod.get("playable") or not vod.get("source_url"):
        raise RuntimeError("Unavailable KICK VOD")
    dur=int(vod.get("duration_seconds") or 0)
    url=_lowest_hls_variant(str(vod["source_url"]))
    OUT.mkdir(exist_ok=True)
    font=ImageFont.load_default()
    all_rows=[]
    for i,minutes in enumerate(OFFSETS_MINUTES):
        center=OPENING_SECONDS+minutes*60
        row={"minutes_after_intro":minutes,"center_seconds":center}
        if center+20>=dur:
            row["status"]="beyond_vod"
        else:
            frames,error=sample(url,center)
            if error:
                row.update(status="sample_failed",reason=error)
            else:
                row["status"]="sampled"
                file=OUT/f"minute_{minutes:04d}.jpg"
                strip=Image.new("RGB",(WIDTH*3,HEIGHT+24),"#121212")
                d=ImageDraw.Draw(strip)
                for n,img in enumerate(frames):strip.paste(img,(n*WIDTH,0))
                d.text((7,HEIGHT+5),f"+{minutes} min / VOD {center}s",fill="white",font=font)
                strip.save(file,quality=84,optimize=True)
                row["file"]=str(file)
        all_rows.append(row)
        print("GCCX_SP_EXTENDED "+json.dumps(row,ensure_ascii=False),flush=True)
    (OUT/"index.json").write_text(json.dumps({
        "mode":"read_only_unverified_extended_end_review",
        "opening_seconds":OPENING_SECONDS,"source_vod_id":VOD_ID,
        "real_end_verified":False,"rows":all_rows
    },ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
