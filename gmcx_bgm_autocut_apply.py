#!/usr/bin/env python3
"""Safely merge independently matched GCCX BGM boundaries into VOD catalog.

Run AFTER kick_gmcx_chapters.py and BEFORE kick_replay_freewifi.py.
Only applies 3-source-consensus audio matches within a small correction
radius. Keeps playback-confirmed starts immutable. A per-VOD ledger prevents
hourly regeneration from reverting prior valid automatic corrections when
the source HLS is temporarily unavailable. Never changes a different VOD ID
or a source with changed duration.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from kick_gmcx_chapters import _apply_refined_chapter_starts

REPORT=Path("gmcx_bgm_autocut_review.json")
LEDGER=Path("gmcx_bgm_auto_starts.json")
CHAPTERS=Path("kick_gmcx_chapters.json")
M3U=Path("kick_gmcx_chapters.m3u")
MAX_CORRECTION=15
# Earlier single-source audio suggested a different offset for #390.
# Require an independent playback/video check before unlocking it.
HOLD_EPISODES={390}


def protected(row:dict)->bool:
    return row.get("method")=="manual-playback-confirmed" and row.get("confidence")=="confirmed"


def read_json(path:Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def report_candidate_valid(row:dict, episode:int, existing:int)->bool:
    if row.get("status")!="candidate" or episode in HOLD_EPISODES:
        return False
    if int(row.get("existing_start_seconds",-1))!=existing:
        return False
    proposals=row.get("independent_reference_proposals") or []
    if len(proposals)!=3:
        return False
    sources={int(x.get("reference_episode",-1)) for x in proposals}
    # Any three DIFFERENT available recordings may be used, but at least
    # one must have a human-verified title-head boundary. The local anchor,
    # when present, is protected separately.
    if len(sources)!=3 or not sources.issubset({378,388,398,404}):
        return False
    if not sources.intersection({378,388}):
        return False
    if any(int(x.get("support_templates",0))<3 or
           float(x.get("similarity",0))<.74 for x in proposals):
        return False
    proposed=int(row.get("proposed_start_seconds",-1))
    votes=[float(x.get("correction_seconds",999)) for x in proposals]
    return (
        existing>0 and proposed>0 and
        abs(proposed-existing)<=MAX_CORRECTION and
        max(votes)-min(votes)<=1.5
    )


def main():
    catalog=read_json(CHAPTERS,None)
    if not catalog or not isinstance(catalog.get("results"),list):
        raise SystemExit("GCCX chapter JSON missing")
    report=read_json(REPORT,{"bundles":[]})
    prior=read_json(LEDGER,{"schema_version":1,"vods":{}})
    if int(prior.get("schema_version",1))!=1:
        raise SystemExit("unknown auto BGM ledger schema")
    saved=prior.get("vods",{})
    incoming={int(g.get("episode_start",-1)):g
              for g in report.get("bundles",[]) if g.get("status")=="review_only"}
    updated={}
    published={}
    all_m3u_edits={}
    for group in catalog["results"]:
        vod_id=str(group.get("vod_id") or "")
        start_ep=int(group.get("episode_start") or -1)
        duration=int(group.get("duration_seconds") or 0)
        if start_ep not in {377,387,397,404} or not vod_id or duration<=0:
            continue
        chapters=group.get("chapters") or []
        if len(chapters)<2: continue

        existing_by_ep={
            int(c["episode"]):(i,c) for i,c in enumerate(chapters)
            if c.get("kind")=="episode" and c.get("episode")
        }
        cached=saved.get(vod_id) or {}
        if int(cached.get("duration_seconds") or 0)==duration:
            old_starts={str(k):int(v) for k,v in (cached.get("starts") or {}).items()}
        else:
            old_starts={}
        original={str(ep):int(c["start_seconds"]) for ep,(i,c) in existing_by_ep.items()}
        # Cached entries remain valid only if their original manual baseline
        # has not moved since approval, avoiding stale adjustments on replays.
        chosen={}
        for k, old_val in old_starts.items():
            if not k.isdecimal(): continue
            ep=int(k)
            if ep in HOLD_EPISODES or ep not in existing_by_ep:continue
            i,c=existing_by_ep[ep]
            if protected(c):continue
            if abs(old_val-int(c["start_seconds"]))>MAX_CORRECTION:continue
            chosen[k]=old_val

        trial=incoming.get(start_ep,{})
        if trial.get("status")=="review_only" and trial.get("reference_sources_used")==3:
            trial_rows=trial.get("rows") or []
            anchor_eps=set(trial.get("manual_anchor_episodes") or [])
            local_manual = bool(anchor_eps and any(ep in existing_by_ep
                and protected(existing_by_ep[ep][1]) for ep in anchor_eps))
            # A source with no local verified chapter may be cut automatically
            # ONLY for #404-416, with two externally manual-confirmed references
            # and a third independently BGM-confirmed source.
            external_manual = (
                start_ep == 404
                and trial.get("calibration_mode") == "cross-recording-manual-anchor"
                and trial.get("external_calibration_anchor_episode") == 378
                and set(trial.get("external_manual_reference_episodes") or []) == {378,388}
            )
            if local_manual or external_manual:
                for row in trial_rows:
                    ep=int(row.get("episode") or -1)
                    if ep not in existing_by_ep:continue
                    i,c=existing_by_ep[ep]
                    if protected(c):continue
                    original_start=int(c.get("start_seconds") or 0)
                    if report_candidate_valid(row,ep,original_start):
                        chosen[str(ep)]=int(row["proposed_start_seconds"])

        # A single invalid boundary must never prevent other valid chapters
        # from retaining their already-verified positions.
        starts={}
        for ep, (i,c) in existing_by_ep.items():
            if str(ep) in chosen and int(chosen[str(ep)])!=int(c["start_seconds"]):
                starts[i]=int(chosen[str(ep)])
        if not starts:
            if chosen: updated[vod_id]={"duration_seconds":duration,"starts":chosen}
            continue

        with_vod=[{**c,"vod_id":vod_id} for c in chapters]
        revised=_apply_refined_chapter_starts(with_vod,starts,duration)
        if revised==with_vod:
            print(f"::warning::BGM corrections rejected for #{start_ep}: invalid chronology")
            continue
        for c in revised: c.pop("vod_id",None)
        for idx in starts:
            c=revised[idx]
            c["method"]="auto-title-bgm-three-source"
            c["confidence"]="high"
            ep=int(c["episode"])
            all_m3u_edits[f"kick.gmcx.chapter.{ep}"]=str(c["replay_url"])
        # A prior chapter's duration changes when the next start moves,
        # so ALL replay URLs for this bundle must be rewritten.
        for c in revised:
            if c.get("kind")=="episode":
                key=f'kick.gmcx.chapter.{int(c["episode"])}'
            elif c.get("kind")=="special":
                key="kick.gmcx.special."+re.sub(r"[^a-zA-Z0-9._-]+","-",str(c.get("special_key") or "special")).strip("-")
            else:continue
            all_m3u_edits[key]=str(c["replay_url"])
        group["chapters"]=revised
        group["bgm_auto_refinement"]={
            "status":"applied","method":"three-source-title-BGM",
            "manual_anchor_preserved":True,"auto_episodes":[int(revised[i]["episode"]) for i in starts],
            "hold_episodes":sorted(HOLD_EPISODES),
        }
        updated[vod_id]={"duration_seconds":duration,"starts":chosen}
        published[start_ep]={str(revised[i]["episode"]):int(revised[i]["start_seconds"]) for i in starts}
    if all_m3u_edits:
        original=M3U.read_text(encoding="utf-8")
        lines=original.splitlines()
        found=set()
        for i,line in enumerate(lines):
            if not line.startswith("#EXTINF:"):continue
            m=re.search(r'tvg-id="([^"]+)"',line)
            if not m or m.group(1) not in all_m3u_edits:continue
            if i+1 >= len(lines) or not lines[i+1].startswith("http"):continue
            lines[i+1]=all_m3u_edits[m.group(1)]
            found.add(m.group(1))
        if found != set(all_m3u_edits):
            raise SystemExit("M3U metadata mismatch; refusing to publish incomplete BGM adjustment")
        CHAPTERS.write_text(json.dumps(catalog,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
        M3U.write_text("\n".join(lines)+"\n",encoding="utf-8")
    # Keep still-active cache entries for this exact VOD and runtime only.
    LEDGER.write_text(json.dumps({"schema_version":1,"vods":updated},ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("BGM_AUTO_PUBLISHED",json.dumps(published,ensure_ascii=False),flush=True)
    print("BGM_AUTO_CACHED",sum(len(x["starts"]) for x in updated.values()),flush=True)


if __name__=="__main__":
    main()
