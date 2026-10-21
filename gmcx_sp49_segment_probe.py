#!/usr/bin/env python3
"""Read-only comparison of HLS segment-aligned playback starts for SP49/392."""
import json
from pathlib import Path
from kick_gmcx_chapters import _fetch_hls_segment_timeline, _segment_aligned_clip

VOD_ID="a640717e-6b99-4a10-a0d4-152d50117319"
def main():
    j=json.loads(Path("kick_replay.json").read_text(encoding="utf-8"))
    url=next(x["source_url"] for x in j["vods"] if x.get("vod_id")==VOD_ID)
    timeline=_fetch_hls_segment_timeline(url)
    if not timeline:
        raise RuntimeError("No HLS segment timeline")
    report={}
    for name,center in [("SP49",22294),("EP392",23196)]:
        neighbors=[{k:round(v,3) for k,v in seg.items()}
                   for seg in timeline if center-27<=seg["start"]<=center+27]
        checks={}
        for shift in range(-8,18):
            wanted=center+shift
            diag=_segment_aligned_clip(timeline,wanted,100)
            checks[str(wanted)]={
                "actual_start":diag["actual_segment_start_seconds"],
                "lead":diag["lead_overlap_seconds"],
            }
        report[name]={"current_start":center,"segments":neighbors,"requested_candidate_starts":checks}
        print("SEGMENTS",name,json.dumps(neighbors,ensure_ascii=False),flush=True)
        print("PLAYBACK_CANDIDATES",name,json.dumps(checks,ensure_ascii=False),flush=True)
    Path("gmcx_sp49_segment_review.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
if __name__=="__main__":
    main()
