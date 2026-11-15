#!/usr/bin/env python3
"""One-frame-per-second images around GCCX audio discrepancies (#50/#55).

Audio fingerprint mismatches are NOT enough to assign episodes. Inspect these
actual frames before publishing a precise title boundary. Read only.
"""
import argparse
import json
import subprocess
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from kick_gmcx_chapters import _lowest_hls_variant

VOD="df1386fd-4bd1-41ae-ac64-743ff49a838f"
TARGETS={
 "ep50_no_ode": (17380,17465),
 "ep55_ten_second_shift": (34786,34852),
 "ep54_control": (31304,31365),
}
WIDTH,HEIGHT,COLS,ROWS=320,180,8,6
SIZE=WIDTH*HEIGHT*3

def main():
    args=argparse.ArgumentParser()
    args.add_argument("--target",choices=TARGETS,required=True)
    name=args.parse_args().target
    start,stop=TARGETS[name]
    rec=json.loads(Path("kick_replay.json").read_text(encoding="utf-8"))
    match=[v for v in rec.get("vods",[]) if v.get("vod_id")==VOD and v.get("playable")]
    if len(match)!=1 or not match[0].get("source_url"):
        raise RuntimeError("Exact source not found")
    src=_lowest_hls_variant(match[0]["source_url"])
    out=Path("gmcx_audio_boundary_video_frames")/name
    out.mkdir(parents=True,exist_ok=True)
    variants=[
      ("direct",-1,src),
      ("resolver",0,
       f"https://kick-resolver-production.up.railway.app/kick?vod={VOD}"
       f"&start={start}&duration={stop-start}"),
    ]
    frames=[]
    failures=[]
    for mode,at,url in variants:
        seek=start if at<0 else at
        cmd=["ffmpeg","-nostdin","-hide_banner","-loglevel","error",
             "-rw_timeout","15000000",
             "-ss",str(seek),"-i",url,"-t",str(stop-start),
             "-an","-vf",f"fps=1,scale={WIDTH}:{HEIGHT}:flags=area,format=rgb24",
             "-pix_fmt","rgb24","-f","rawvideo","pipe:1"]
        try:
            p=subprocess.run(cmd,capture_output=True,timeout=145)
            count=len(p.stdout)//SIZE
            if count>=20:
                frames=[Image.frombytes("RGB",(WIDTH,HEIGHT),
                        p.stdout[i*SIZE:(i+1)*SIZE]) for i in range(count)]
                print("SUCCESS",name,mode,count,flush=True)
                break
            failures.append({"mode":mode,"ret":p.returncode,
                 "frames":count,"error":p.stderr.decode("utf-8","replace")[-220:]})
        except (OSError,subprocess.TimeoutExpired) as exc:
            failures.append({"mode":mode,"error":str(exc)[:180]})
    if not frames:
        print("ERROR",name,failures,flush=True)
        raise RuntimeError("Both audio-boundary video captures failed")
    pages=[]
    for n in range((len(frames)+COLS*ROWS-1)//(COLS*ROWS)):
        grid=Image.new("RGB",(COLS*(WIDTH+5),ROWS*(HEIGHT+30)),(14,14,14))
        pen=ImageDraw.Draw(grid)
        for idx in range(n*COLS*ROWS,min(len(frames),(n+1)*COLS*ROWS)):
            cell=idx-n*COLS*ROWS
            x=(cell%COLS)*(WIDTH+5)
            y=(cell//COLS)*(HEIGHT+30)
            grid.paste(frames[idx],(x,y))
            t=start+idx
            pen.text((x+4,y+HEIGHT+2),
                     f"{t}s | {t//3600:02d}:{(t//60)%60:02d}:{t%60:02d}",
                     font=ImageFont.load_default(),fill="white")
        filepath=out/f"{name}_page_{n+1:02}.jpg"
        grid.save(filepath,quality=86)
        pages.append(str(filepath))
    index={
        "task":name,"source_vod_id":VOD,"requested_start_seconds":start,
        "requested_stop_seconds":stop,"nominal_interval_seconds":1,
        "frames_captured":len(frames),"pages":pages,
        "failure_details":failures,"production_changed":False,
        "status":"frames_for_visual_review_only",
        "warning":"Frame offsets are approximate on HLS seek. Inspect frames and opening titles before promoting proposed audio boundary."
    }
    (out/"index.json").write_text(json.dumps(index,ensure_ascii=False,indent=2)+"\n",
                                  encoding="utf-8")
if __name__=="__main__":
    main()
