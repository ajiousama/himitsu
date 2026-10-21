#!/usr/bin/env python3
"""Read-only wide scan to find the true #400 title after extra-long SP52."""
from __future__ import annotations
import json
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor,as_completed
import numpy as np
import gmcx_bgm_autocut as bm
from gmcx_397_sp52_probe import scan,contact
from kick_gmcx_chapters import _lowest_hls_variant

OUT=Path("gmcx_397_sp52_wide_review")
OUT.mkdir(exist_ok=True)
ARCHIVE="c60eb405-0e1a-4679-beca-79d8c95b2e7f"
ANCHOR="a640717e-6b99-4a10-a0d4-152d50117319"

def seek_many(url,centers,refs,calibration,stage):
    answers=[]
    def scan_one(center):
        row=scan(url,center,refs,str(center))
        votes=[]
        for k,m in row["matches"].items():
            if m.get("status")!="matched" or k not in calibration:continue
            difference=m["raw_delay_seconds"]-calibration[k]
            votes.append({"ref":int(k),"shift":difference,"similarity":m["mean_similarity"]})
        if len(votes)>=2 and max(v["shift"] for v in votes)-min(v["shift"] for v in votes)<=3:
            row["candidate_start"]=round(center+float(np.median([v["shift"] for v in votes])))
            row["status"]="matched"
        else:row["status"]="unmatched"
        row["votes"]=votes
        return row
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures={pool.submit(scan_one,c):c for c in centers}
        for f in as_completed(futures):
            c=futures[f]
            try:
                row=f.result()
                print("WIDE",stage,c,row["status"],row.get("candidate_start"),
                      json.dumps(row.get("votes",[]),ensure_ascii=False),flush=True)
            except Exception as ex:
                row={"expected_seconds":c,"status":"failed","error":str(ex)[:350]}
                print("WIDE",stage,c,"FAILED",row["error"],flush=True)
            answers.append(row)
    return sorted(answers,key=lambda x:x["expected_seconds"])

def main():
    d=json.loads(Path("kick_replay.json").read_text(encoding="utf-8"))
    v={r["vod_id"]:r for r in d["vods"]}
    refs,_=bm.read_reference_sources(d["vods"])
    url=_lowest_hls_variant(v[ARCHIVE]["source_url"])
    original_url=_lowest_hls_variant(v[ANCHOR]["source_url"])
    anchor=scan(original_url,3488,refs,"#388")
    calibration={k:r["raw_delay_seconds"] for k,r in anchor["matches"].items() if r["status"]=="matched"}
    if len(calibration)<2:raise RuntimeError("Manual anchor could not be calibrated")
    # Scan all plausible first regular-episode heads from immediately after
    # 400 advertised broadcast minutes to 65 minutes after it.
    coarse=list(range(34440,38341,115))
    first=seek_many(url,coarse,refs,calibration,"#400")
    hits=sorted({int(r["candidate_start"]) for r in first if r["status"]=="matched"})
    print("ALL_400_HITS",json.dumps(hits),flush=True)
    if not hits:
        follow=[]
        chosen=None
    else:
        # Choose a reference-supported hit and test the following episodes
        # at 58-min intervals; do not blindly assume all source breaks.
        chosen=min(hits,key=lambda c:abs(c-37500))
        follow_centers=[chosen+3480*n+diff for n in (1,2,3)
                       for diff in (-160,0,160)]
        follow=seek_many(url,follow_centers,refs,calibration,"#401-403")
    reviews=[]
    for start in hits[:8]:
        reviews.append(contact(url,start,"possible_400_"+str(start)))
    report={"mode":"review_only","duration":v[ARCHIVE]["duration_seconds"],
        "anchor_offsets":calibration,"raw_candidates_400":hits,
        "selected_400_hypothesis":chosen,"raw_coarse":first,
        "later_candidates":follow,"image_sheets":reviews,
        "production_changed":False}
    (OUT/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("WIDE_SUMMARY",json.dumps({"#400":hits,"selected":chosen,
        "later":[r.get("candidate_start") for r in follow if r["status"]=="matched"]}),flush=True)
if __name__=="__main__":
    main()
