#!/usr/bin/env python3
"""GCCX special boundary video + audio verification, without modifying VOD5.

Makes second-by-second visual evidence and audio transition metrics for the
two sides of the year-end SP49 (#391 -> SP49 -> #392). Sources are decoded
directly from the original Kick recording, not from the chapter proxy.
"""
from __future__ import annotations
import json
import math
import subprocess
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from kick_gmcx_chapters import _lowest_hls_variant
from gmcx_auto_cut_audio import read_audio, SAMPLE_RATE

VOD_ID = "a640717e-6b99-4a10-a0d4-152d50117319"
OUT = Path("gmcx_sp49_boundary_review")
OUT.mkdir(exist_ok=True)

def video_frames(url: str, center: int, before: int=22, after: int=22):
    start=center-before
    count=before+after+1
    w,h=320,180
    cmd=[
        "ffmpeg","-nostdin","-hide_banner","-loglevel","error",
        "-rw_timeout","25000000","-ss",str(start),"-i",url,
        "-t",str(count),"-an","-vf",f"fps=1,scale={w}:{h}:flags=area,format=rgb24",
        "-f","rawvideo","pipe:1",
    ]
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=100)
    if p.returncode:
        raise RuntimeError(p.stderr.decode("utf-8","replace")[-450:])
    size=w*h*3
    arr=np.frombuffer(p.stdout,dtype=np.uint8)
    n=min(count,len(arr)//size)
    if n < count-6:
        raise RuntimeError(f"Only {n}/{count} video frames read")
    frames=arr[:n*size].reshape(n,h,w,3)
    # Every frame labeled with absolute time in source recording.
    pilframes=[]
    for i,raw in enumerate(frames):
        f=Image.fromarray(raw)
        draw=ImageDraw.Draw(f)
        second=start+i
        stamp=f"{second//3600:02d}:{second%3600//60:02d}:{second%60:02d}  ({second})"
        color="#ffb400" if abs(second-center)<=2 else "white"
        draw.rectangle([0,0,145,18],fill="#101010")
        draw.text((3,3),stamp,fill=color)
        pilframes.append(f)
    # Print 45 frames in 3 sheets for readable image rendering on iPhone too.
    sizes=[]
    for chunk in range(0,len(pilframes),15):
        subset=pilframes[chunk:chunk+15]
        sheet=Image.new("RGB",(5*w,3*h),"#101010")
        for k,frame in enumerate(subset):
            sheet.paste(frame,((k%5)*w,(k//5)*h))
        filename=OUT/f"at_{center}_{chunk//15+1:02d}.jpg"
        sheet.save(filename,quality=86,subsampling=1)
        sizes.append(str(filename))
    # Abrupt visual changes and average RGB brightness for every frame.
    floats=frames.astype(np.float32)
    differences=np.mean(np.abs(np.diff(floats,axis=0)),axis=(1,2,3))
    peaks=sorted([{"second":start+i,"change":round(float(val),1)}
                  for i,val in enumerate(differences,1)],
                 key=lambda x:x["change"],reverse=True)[:12]
    return {"start_seconds":start,"frames":n,"sheets":sizes,"visual_change_peaks":peaks}

def audio_edges(url: str, center:int, before:int=35,after:int=35):
    start=center-before
    wave=read_audio(url,start,before+after+1)
    # robust 1-second RMS and 100ms smoothed energy for soundtrack cuts
    rms=[]
    for i in range(min(before+after+1,len(wave)//SAMPLE_RATE)):
        samples=wave[i*SAMPLE_RATE:(i+1)*SAMPLE_RATE]
        rms.append(float(np.sqrt(np.mean(samples*samples))))
    # Largest adjacent-second RMS changes
    edges=sorted([{"second":start+i,"prev_rms":round(rms[i-1],4),
                   "next_rms":round(rms[i],4),
                   "log_rms_change":round(abs(math.log(max(rms[i],1e-6)/max(rms[i-1],1e-6))),3)}
                  for i in range(1,len(rms))],
                 key=lambda x:x["log_rms_change"],reverse=True)[:14]
    return {"audio_start_seconds":start,"audio_rms_top_changes":edges}

def main():
    catalog=json.loads(Path("kick_replay.json").read_text(encoding="utf-8"))
    chapters=json.loads(Path("kick_gmcx_chapters.json").read_text(encoding="utf-8"))
    vod=next(x for x in catalog["vods"] if x.get("vod_id")==VOD_ID)
    group=next(x for x in chapters["results"] if x.get("vod_id")==VOD_ID)
    url=_lowest_hls_variant(vod["source_url"])
    targeted=[
        ("SP49_START",next(c for c in group["chapters"]
         if c.get("special_key")=="2024-yearend-sp49-15min")["start_seconds"]),
        ("EP392_START",next(c for c in group["chapters"]
         if c.get("episode")==392)["start_seconds"]),
    ]
    report={"mode":"review_only","source_vod":VOD_ID,"source_title":vod["title"],
            "production_changed":False,"boundaries":[]}
    for label,center in targeted:
        row={"label":label,"current_start":center}
        try: row.update(video_frames(url,center))
        except Exception as ex:row["video_error"]=str(ex)
        try: row.update(audio_edges(url,center))
        except Exception as ex:row["audio_error"]=str(ex)
        report["boundaries"].append(row)
        print("SP49_VERIFY",json.dumps({
            k:v for k,v in row.items() if k not in ["sheets","visual_change_peaks","audio_rms_top_changes"]
        },ensure_ascii=False),flush=True)
        print("TOP_VIDEO_EDGES",label,json.dumps(row.get("visual_change_peaks",[])[:8],ensure_ascii=False),flush=True)
        print("TOP_AUDIO_EDGES",label,json.dumps(row.get("audio_rms_top_changes",[])[:8],ensure_ascii=False),flush=True)
    (OUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__":
    main()
