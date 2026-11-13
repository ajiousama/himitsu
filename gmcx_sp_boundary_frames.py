#!/usr/bin/env python3
"""Frame-by-frame review of a possible GCCX 3-hour SP transition.

This diagnostic is READ ONLY. Individual images have an indexed source-time
label. It never changes VOD5 or claims an episode boundary.
"""
from __future__ import annotations
import json
import subprocess
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
from kick_gmcx_chapters import _lowest_hls_variant

SOURCE_ID = "df1386fd-4bd1-41ae-ac64-743ff49a838f"
START, STOP = 59090, 59220
WIDTH, HEIGHT, FPS = 192, 108, 1
COLS, ROWS = 10, 5
MAX_PER_PAGE = COLS * ROWS
OUT_DIR = Path("gmcx_sp_boundary_frames")
FRAME_SIZE = WIDTH * HEIGHT * 3

def frames(url: str) -> bytes:
    cmd = [
        "ffmpeg", "-nostdin","-hide_banner","-loglevel","error",
        "-rw_timeout","15000000","-ss",str(START),"-i",url,
        "-t",str(STOP-START),"-an",
        "-vf",f"fps={FPS},scale={WIDTH}:{HEIGHT}:flags=area,format=rgb24",
        "-pix_fmt","rgb24","-f","rawvideo","pipe:1"
    ]
    p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=145,check=False)
    if p.returncode or len(p.stdout)<FRAME_SIZE*60:
        raise RuntimeError("decode failed or insufficient frames: "+
                           p.stderr.decode("utf-8","replace")[-300:])
    return p.stdout

def generate(raw: bytes) -> list[dict]:
    OUT_DIR.mkdir(exist_ok=True)
    total=len(raw)//FRAME_SIZE
    pages=[]
    font=ImageFont.load_default()
    for page in range((total+MAX_PER_PAGE-1)//MAX_PER_PAGE):
        sheet=Image.new("RGB",(COLS*(WIDTH+6),ROWS*(HEIGHT+26)),(12,12,12))
        draw=ImageDraw.Draw(sheet)
        for cell in range(MAX_PER_PAGE):
            idx=page*MAX_PER_PAGE+cell
            if idx>=total: break
            frame=Image.frombytes("RGB",(WIDTH,HEIGHT),
                    raw[idx*FRAME_SIZE:(idx+1)*FRAME_SIZE])
            x=(cell%COLS)*(WIDTH+6)
            y=(cell//COLS)*(HEIGHT+26)
            sheet.paste(frame,(x,y))
            seconds=START+idx/FPS
            draw.text((x+4,y+HEIGHT+3), f"t={int(seconds)}  {int(seconds)//3600:02d}:{(int(seconds)//60)%60:02d}:{int(seconds)%60:02d}",font=font,fill="white")
        output=OUT_DIR/f"sp_transition_page_{page+1:02}.jpg"
        sheet.save(output,quality=86,optimize=True)
        pages.append({"page":page+1,"file":str(output),
                      "from_seconds":START+page*MAX_PER_PAGE,
                      "to_seconds":min(STOP,START+(page+1)*MAX_PER_PAGE)})
    return pages

def main() -> int:
    replay=json.loads(Path("kick_replay.json").read_text(encoding="utf-8"))
    source=next((v for v in replay.get("vods",[]) if v.get("vod_id")==SOURCE_ID),None)
    if not source or not source.get("playable") or not source.get("source_url"):
        raise RuntimeError("GCCX source no longer available")
    result={"source_id":SOURCE_ID,"start_seconds":START,
            "stop_seconds":STOP,"sample_fps":FPS,
            "publication_safe":False,"pages":generate(frames(
                _lowest_hls_variant(str(source["source_url"]))))}
    (OUT_DIR/"index.json").write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("GCCX_SP_BOUNDARY_FRAMES "+json.dumps(result,ensure_ascii=False),flush=True)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
