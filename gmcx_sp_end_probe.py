#!/usr/bin/env python3
"""Read-only contact sheets around anticipated ending of historical 3-hour GCCX SP.

The estimate uses the *observed* source intro at 59152s plus a nominal
3 hours, and deliberately scans a wide region. This does not assume the
programme lasts exactly three hours. Do not publish an end cut from a
single visual observation.
"""
from __future__ import annotations
import json
import subprocess
from pathlib import Path
from kick_gmcx_chapters import _lowest_hls_variant

VOD_ID="df1386fd-4bd1-41ae-ac64-743ff49a838f"
START_OBSERVED=59152
NOMINAL_END=START_OBSERVED+3*60*60
OUT_DIR=Path("gmcx_sp_end_review")
CENTRES=(NOMINAL_END-600,NOMINAL_END-300,NOMINAL_END,NOMINAL_END+300,NOMINAL_END+600)

def capture(url:str,centre:int,file:Path)->dict:
    # ~8 minutes sampled once per 12 seconds: broad visual summary.
    start=max(0,centre-240)
    cmd=["ffmpeg","-nostdin","-hide_banner","-loglevel","error",
         "-rw_timeout","15000000","-ss",str(start),"-i",url,"-t","480","-an",
         "-vf","fps=1/12,scale=256:144:flags=area,tile=8x5:padding=3:margin=3",
         "-frames:v","1","-q:v","5","-y",str(file)]
    try:
        p=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                         timeout=115,check=False)
        if p.returncode or not file.exists() or file.stat().st_size<2000:
            return {"status":"decode_failed","error":p.stderr.decode("utf-8","replace")[-240:]}
        return {"status":"captured","bytes":file.stat().st_size,
                "sample_from_seconds":start,"sample_to_seconds":start+480,
                "frame_interval_seconds":12}
    except (OSError,subprocess.TimeoutExpired) as e:
        return {"status":"decode_failed","error":str(e)[:200]}

def main()->int:
    v=json.loads(Path("kick_replay.json").read_text(encoding="utf-8"))
    source=next((x for x in v.get("vods",[]) if x.get("vod_id")==VOD_ID),None)
    if not source or not source.get("playable") or not source.get("source_url"):
        raise RuntimeError("source HLS unavailable")
    if int(source.get("duration_seconds") or 0) < CENTRES[-1]+240:
        raise RuntimeError("source duration changed, unsafe to scan")
    OUT_DIR.mkdir(exist_ok=True)
    url=_lowest_hls_variant(str(source["source_url"]))
    rows=[]
    for i,centre in enumerate(CENTRES):
        file=OUT_DIR/f"around_nominal_end_{i+1:02}_{centre}.jpg"
        row={"centre_seconds":centre,"nominal_end_seconds":NOMINAL_END,
             "file":str(file),**capture(url,centre,file)}
        rows.append(row)
        print("GCCX_SP_END "+json.dumps(row,ensure_ascii=False),flush=True)
    (OUT_DIR/"index.json").write_text(
        json.dumps({"mode":"read_only_nominal_three_hour_end_review",
                    "source_vod_id":VOD_ID,
                    "real_end_verified":False,"rows":rows},
                   ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
