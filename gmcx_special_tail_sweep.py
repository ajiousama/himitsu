#!/usr/bin/env python3
"""Read-only actual frame sweep for the three GCCX multi-hour special tails.

Decode 1 frame per short HLS clip, NOT a multi-hour ffmpeg input. Black frame
or failed seek is unknown media, never proof of programme end.
"""
from __future__ import annotations
import argparse
import json
import subprocess
from datetime import datetime,timezone
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageStat

VOD={
    "kai_after_live":("df1386fd-4bd1-41ae-ac64-743ff49a838f",89000,101000,600),
    "fivehour_after_live":("e4f91158-8a0e-4c75-9fb4-eab36c247464",90000,104000,600),
    "lemmings_late":("5847ae05-893e-4ae8-986e-bf0abf888ecf",118000,131600,600),
}
W,H,COLS,ROWS=320,180,4,4
OUT=Path("gmcx_special_tail_sweep")
BASE="https://kick-resolver-production.up.railway.app/kick"


def frame(url:str,seconds:int,path:Path)->tuple[str,str]:
    attempts=[(f"{BASE}?vod={url}&start={seconds}&duration=8",1,"resolver")]
    for src,seek,mode in attempts:
        cmd=["ffmpeg","-nostdin","-hide_banner","-loglevel","error",
             "-rw_timeout","8000000","-ss",str(seek),"-i",src,
             "-frames:v","1","-y",str(path)]
        try:
            p=subprocess.run(cmd,capture_output=True,timeout=19,check=False)
            if p.returncode==0 and path.is_file() and path.stat().st_size>2500:
                return ("video_frame_decoded",mode)
        except (subprocess.TimeoutExpired,OSError):
            pass
    return ("unavailable","none")


def main()->int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--task",required=True,choices=VOD)
    args=parser.parse_args()
    ident,start,stop,step=VOD[args.task]
    catalog=json.loads(Path("kick_replay.json").read_text(encoding="utf-8"))
    found=[x for x in catalog["vods"] if x.get("vod_id")==ident and x.get("playable") is True]
    if len(found)!=1 or int(found[0].get("duration_seconds") or 0)<stop:
        raise RuntimeError("Exact playable source or duration missing")
    dest=OUT/args.task
    dest.mkdir(parents=True,exist_ok=True)
    items=[]
    for t in range(start,stop+1,step):
        f=dest/f"frame_{t:06d}.jpg"
        status,method=frame(ident,t,f)
        row={"second":t,"status":status,"read_mode":method}
        if status=="video_frame_decoded":
            with Image.open(f) as im:
                im=im.convert("RGB")
                bright=sum(ImageStat.Stat(im).mean)/3
                row["mean_brightness"]=round(bright,2)
                row["near_black_frame"]=bright<9
        items.append(row)
        print("GCCX_END_SAMPLE",args.task,t,status,
              row.get("near_black_frame"),flush=True)
    font=ImageFont.load_default()
    pages=[]
    for page in range((len(items)+COLS*ROWS-1)//(COLS*ROWS)):
        grid=Image.new("RGB",(COLS*(W+8),ROWS*(H+26)),(25,25,25))
        d=ImageDraw.Draw(grid)
        for i in range(page*COLS*ROWS,min(len(items),(page+1)*COLS*ROWS)):
            item=items[i];n=i-page*COLS*ROWS
            x=(n%COLS)*(W+8);y=(n//COLS)*(H+26)
            f=dest/f"frame_{item['second']:06d}.jpg"
            if f.exists():
                with Image.open(f) as im:
                    im=im.convert("RGB");im.thumbnail((W,H))
                    grid.paste(im,(x+(W-im.width)//2,y+(H-im.height)//2))
            secs=item["second"]
            d.text((x+4,y+H+3),f"{secs}s {secs//3600:02d}:{secs//60%60:02d}:{secs%60:02d} {item['status'][:10]}",fill="white",font=font)
        output=dest/f"contact_{page+1:02d}.jpg"
        grid.save(output,quality=84)
        pages.append(str(output))
    report={
        "schema_version":1,
        "generated_utc":datetime.now(timezone.utc).isoformat(),
        "task":args.task,"source_vod_id":ident,"sampled_interval_seconds":step,
        "sampled_second_range":[start,stop],
        "rows":items,"contact_pages":pages,
        "verified_programme_end_seconds":None,
        "production_changed":False,
        "warning":"Sampled frames show content at particular seconds only. Black images and unavailable frames never establish an episode ending."
    }
    (dest/"index.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("GCCX_END_SWEEP_COMPLETE",args.task,len(items),sum(x["status"]=="video_frame_decoded" for x in items),flush=True)
    return 0
if __name__=="__main__":
    raise SystemExit(main())
