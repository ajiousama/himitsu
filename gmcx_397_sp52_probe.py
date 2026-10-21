#!/usr/bin/env python3
"""Read-only 3-reference GCCX title BGM scan of 2025 #397-403 + SP52 archive.

Anchor on manually confirmed #388 in a DIFFERENT source recording. Never
publish based only on this detector. Dump per-source votes and visual contact
sheets at the SP52 join (between #399 and #400).
"""
from __future__ import annotations
import json
import math
import subprocess
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path
import numpy as np
import gmcx_bgm_autocut as match
from gmcx_auto_cut_audio import read_audio,fingerprint
from kick_gmcx_chapters import _lowest_hls_variant

VOD="c60eb405-0e1a-4679-beca-79d8c95b2e7f"
REFERENCE_VOD="a640717e-6b99-4a10-a0d4-152d50117319"
OUTPUT=Path("gmcx_397_sp52_review")
OUTPUT.mkdir(exist_ok=True)

def scan(url,center:int,ref_vectors:dict[int,np.ndarray],label:str):
    start=max(0,center-match.WINDOW_BEFORE)
    span=match.WINDOW_BEFORE+match.WINDOW_AFTER
    feat=fingerprint(read_audio(url,start,span))
    # Primary matcher expects search audio to begin exactly WINDOW_BEFORE
    # before expected chapter start; all non-zero centers here meet that.
    m={str(k):match.correlate_one(ref,feat) for k,ref in ref_vectors.items()}
    return {"label":label,"expected_seconds":center,"source_range":[start,start+span],"matches":m}

def contact(url,center,name):
    # Two 4-second sheets around the 400-minute broadcast boundaries; images
    # show what is actually at the predicted change in programming.
    start=max(0,center-64)
    fn=OUTPUT/f"{name}_near_{center}.jpg"
    vf="fps=1/4,scale=240:135:flags=area,drawtext=fontcolor=white:fontsize=12:text='%{pts\\:hms}':x=4:y=5:box=1:boxcolor=black@0.7,tile=8x4:padding=3:margin=4"
    args=["ffmpeg","-nostdin","-hide_banner","-loglevel","error","-rw_timeout","25000000",
          "-ss",str(start),"-i",url,"-t","128","-an","-vf",vf,
          "-frames:v","1","-q:v","4","-y",str(fn)]
    try:
        p=subprocess.run(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=150)
        return {"sheet":str(fn),"status":"created" if p.returncode==0 and fn.exists() else "failed",
                "error":p.stderr.decode("utf-8","replace")[-250:] if p.returncode else ""}
    except Exception as exc:
        return {"status":"failed","error":str(exc)[:200]}

def main():
    catalog=json.loads(Path("kick_replay.json").read_text(encoding="utf-8"))
    sources={str(x.get("vod_id")):x for x in catalog["vods"]}
    vod=sources[VOD]
    archive=sources[REFERENCE_VOD]
    state=json.loads(Path("kick_gmcx_chapters.json").read_text(encoding="utf-8"))
    entry=next(g for g in state["results"] if g["episode_start"]==397)
    chapters=entry["chapters"]
    if not chapters:
        raise RuntimeError("The #397 SP52 provisional chapter scaffold has not been built yet.")
    refs,read_state=match.read_reference_sources(catalog["vods"])
    if len(refs)<2:raise RuntimeError("At least two live reference sources required")
    # A cross-recording anchor: #388 manual playback confirmed at 3488s.
    anchor_url=_lowest_hls_variant(archive["source_url"])
    target_url=_lowest_hls_variant(vod["source_url"])
    anchor=scan(anchor_url,3488,refs,"#388_MANUAL_ANCHOR")
    calibration={k:v["raw_delay_seconds"] for k,v in anchor["matches"].items()
                 if v.get("status")=="matched"}
    if len(calibration)<2:raise RuntimeError("Insufficient manual anchor votes")
    targets=[c for c in chapters if c.get("kind")=="episode" and c.get("episode")!=397]
    scanned=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        future_to_ep={
            pool.submit(scan,target_url,int(c["start_seconds"]),refs,"#"+str(c["episode"])):c
            for c in targets
        }
        for fut in as_completed(future_to_ep):
            chapter=future_to_ep[fut]
            try:
                row=fut.result()
                votes=[]
                for k,v in row["matches"].items():
                    if k not in calibration or v.get("status")!="matched":continue
                    shift=v["raw_delay_seconds"]-calibration[k]
                    votes.append({"reference":int(k),"shift_seconds":round(float(shift),2),
                                  "similarity":v["mean_similarity"],"strong_windows":v["strong"]})
                row["votes"]=votes
                if len(votes)>=2 and max(v["shift_seconds"] for v in votes)-min(v["shift_seconds"] for v in votes)<=3:
                    shift=round(float(np.median([x["shift_seconds"] for x in votes])))
                    row["candidate_start_seconds"]=row["expected_seconds"]+shift
                    row["status"]="candidate" if abs(shift)<=45 else "large_shift_review"
                else:
                    row["status"]="needs_review"
                print("BGM_CHAPTER",row["label"],row["status"],
                      row.get("candidate_start_seconds"),json.dumps(votes,ensure_ascii=False),flush=True)
            except Exception as exc:
                row={"label":"#"+str(chapter["episode"]),"expected_seconds":chapter["start_seconds"],
                     "status":"unavailable","error":str(exc)[:350]}
                print("BGM_CHAPTER",row["label"],row["status"],row["error"],flush=True)
            scanned.append(row)
    scans=[c for c in chapters if c["kind"]=="special" and c.get("special_key")=="2025-sp52-400min-live"]
    sheets=[]
    for c in scans:
        sheets.append(contact(target_url,int(c["start_seconds"]),"sp52_start"))
        sheets.append(contact(target_url,int(c["stop_seconds"]),"sp52_end"))
    report={"mode":"review_only","vod_id":VOD,"duration":vod["duration_seconds"],
           "reference_states":read_state,"manual_anchor":anchor,
           "manual_calibration_offsets":calibration,
           "broadcast_order":[c.get("episode") or c.get("special_key") for c in chapters],
           "bounds":sorted(scanned,key=lambda x:x["expected_seconds"]),
           "special_sheets":sheets,"production_changed":False}
    (OUTPUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("GCCX_397_REPORT",json.dumps(
        {"candidates":sum(r["status"]=="candidate" for r in scanned),
         "unmatched":[r["label"] for r in scanned if r["status"]!="candidate"],
         "special_sheets":sheets},ensure_ascii=False),flush=True)

if __name__=="__main__":
    main()
