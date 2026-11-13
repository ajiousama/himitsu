#!/usr/bin/env python3
"""Capture small video contact sheets around each logo-like GCCX candidate.

Pure review artifact: NEVER edits VOD5 or claims episode identity.
"""
from __future__ import annotations
import json
import subprocess
import time
from pathlib import Path
from kick_gmcx_chapters import _lowest_hls_variant

OUT_DIR=Path("gmcx_logo_candidate_frames")
TARGETS=(
    ("5847ae05",3444,"nov11_3444"),
    ("5847ae05",3660,"nov11_3660"),
    ("5847ae05",3806,"nov11_3806"),
    ("f622346e",3366,"nov09_morning_3366"),
    ("f622346e",3466,"nov09_morning_3466"),
    ("f622346e",3489,"nov09_morning_3489"),
    ("df1386fd",59197,"nov09_tail_59197"),
    ("df1386fd",59361,"nov09_tail_59361"),
    ("df1386fd",59377,"nov09_tail_59377"),
)

def capture(url: str, center: int, output: Path) -> tuple[bool,str]:
    # 6 x 5, each tile 3 sec apart, covering center-42 through +45s
    start=max(0,center-42)
    cmd=[
        "ffmpeg","-nostdin","-hide_banner","-loglevel","error",
        "-rw_timeout","15000000", "-ss",str(start),"-i",url,
        "-t","90","-an",
        "-vf","fps=1/3,scale=320:180:flags=area,tile=6x5:padding=3:margin=4",
        "-frames:v","1","-q:v","5","-y",str(output)
    ]
    try:
        r=subprocess.run(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=95,check=False)
        if r.returncode!=0 or not output.is_file() or output.stat().st_size<1000:
            return False, r.stderr.decode("utf-8","replace")[-230:]
        return True, "bytes="+str(output.stat().st_size)
    except (OSError,subprocess.TimeoutExpired) as e:
        return False,str(e)[:220]

def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)
    catalog=json.loads(Path("kick_replay.json").read_text(encoding="utf-8"))
    vods=catalog.get("vods") or []
    rows=[]
    for prefix,center,label in TARGETS:
        source=next((v for v in vods if str(v.get("vod_id") or "").startswith(prefix)
                     and str(v.get("tvg_id") or "").startswith("kick.gccx")),None)
        row={"label":label,"vod_prefix":prefix,"center_seconds":center}
        if not source or not source.get("playable") or not source.get("source_url"):
            row["status"]="unavailable"
        else:
            url=_lowest_hls_variant(str(source["source_url"]))
            output=OUT_DIR/(label+".jpg")
            ok,detail=capture(url,center,output)
            row.update(status="captured" if ok else "capture_failed",detail=detail,
                       source_vod_id=str(source["vod_id"]),
                       frame_path=str(output) if ok else None)
        print("GCCX_CANDIDATE_FRAMES "+json.dumps(row,ensure_ascii=False),flush=True)
        rows.append(row)
        time.sleep(1)
    (OUT_DIR/"index.json").write_text(
        json.dumps({"mode":"review_only","rows":rows,"no_playlist_changes":True},
                   ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    return 0

if __name__=="__main__":
    raise SystemExit(main())
