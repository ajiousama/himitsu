#!/usr/bin/env python3
"""Read-only audio-based cut detector using independent GCCX title-music exemplars.

Available title-BGM openings (#378/#388/#398/#404, one per independent VOD)
are searched near regular chapter boundaries. Two references have manually
confirmed boundaries. For #404-416 only, strict independent-source consensus
can propose cuts without a same-recording manual anchor.

No list, chapter, or previously confirmed cut is rewritten. The JSON report
is intended for review before any changes to published FreeWiFi/VOD5.
"""
from __future__ import annotations
import argparse
import json
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path
import numpy as np
from gmcx_auto_cut_audio import read_audio, fingerprint, SAMPLE_RATE, HOP
from kick_gmcx_chapters import _lowest_hls_variant

# Title samples from independent, currently present KICK VOD files.
# 378 and 388 were manually confirmed; 398 has a previously BGM-refined start.
# 404 is only a provisional recording-head reference and can never be
# considered a manual reference.
REFERENCE_SOURCES = (
    (377, 378, "manual-playback-confirmed", "confirmed"),
    (387, 388, "manual-playback-confirmed", "confirmed"),
    (397, 398, "auto-title-bgm-three-source", "high"),
    (404, 404, "user-test-broadcast-order", "provisional"),
)
MANUALLY_VERIFIED_REFERENCES = frozenset((378, 388))
REFERENCE_EPISODES = tuple(ep for _, ep, _, _ in REFERENCE_SOURCES)
TEMPLATE_OFFSETS = (10, 15, 20, 55, 60)
TEMPLATE_LENGTH = 6  # seconds: capture distinctive score and transitions
REFERENCE_CAPTURE = 85
WINDOW_BEFORE = 65
WINDOW_AFTER = 105
RADIUS = 55
FRAME_RATE = SAMPLE_RATE // HOP
# Each template is evaluated independently. A single catchy sound is not enough.
MIN_SIMILARITY = 0.72
MIN_MARGIN = 0.035
MIN_STRONG_TEMPLATES = 3
MAX_DISAGREEMENT_SECONDS = 2.5
MAX_CUT_SHIFT = 50
JST = timezone(timedelta(hours=9))


def read_reference_sources(vods: list[dict], groups: list[dict]) -> tuple[dict[int,np.ndarray], list[dict], dict[int,str]]:
    """Decode multiple independent *available* KICK recordings; never use vanished legacy VODs."""
    vectors, entries, owners = {}, [], {}
    by_vod = {str(v.get("vod_id")): v for v in vods}
    by_first = {int(g.get("episode_start") or -1): g for g in groups}
    for first, ep, required_method, required_confidence in REFERENCE_SOURCES:
        group = by_first.get(first) or {}
        vod_id = str(group.get("vod_id") or "")
        chapter = next((c for c in (group.get("chapters") or [])
                        if c.get("kind") == "episode" and int(c.get("episode") or -1) == ep), None)
        source = by_vod.get(vod_id)
        if not chapter or (chapter.get("method"), chapter.get("confidence")) != (required_method, required_confidence):
            entries.append({"reference_episode": ep, "status": "unavailable",
                            "reason": "missing_or_changed_verified_chapter"})
            continue
        if not source or not source.get("playable") or not source.get("source_url"):
            entries.append({"reference_episode": ep, "status": "unavailable",
                            "reason": "source_recording_unavailable"})
            continue
        try:
            seconds = int(chapter.get("start_seconds") or 0)
            signal = read_audio(_lowest_hls_variant(str(source["source_url"])),
                                seconds, REFERENCE_CAPTURE)
            vectors[ep] = fingerprint(signal)
            owners[ep] = vod_id
            entries.append({"reference_episode": ep, "status": "decoded",
                            "vod_id": vod_id, "verified_manual": ep in MANUALLY_VERIFIED_REFERENCES,
                            "start_seconds": seconds})
        except Exception as exc:
            entries.append({"reference_episode": ep, "status": "unavailable",
                            "reason": str(exc)[:250]})
    print("BGM_REFERENCES", json.dumps(entries, ensure_ascii=False), flush=True)
    return vectors, entries, owners


def correlate_one(reference: np.ndarray, observed: np.ndarray) -> dict:
    """Find a consistent BGM signature offset, not an arbitrary loud event."""
    win = TEMPLATE_LENGTH * FRAME_RATE
    searches = np.lib.stride_tricks.sliding_window_view(
        observed, win, axis=0
    ).transpose(0, 2, 1)
    search_norm = np.linalg.norm(searches, axis=(1, 2))
    rows = []
    for offset in TEMPLATE_OFFSETS:
        segment = reference[offset*FRAME_RATE: offset*FRAME_RATE + win]
        if len(segment) != win:
            continue
        norm = float(np.linalg.norm(segment))
        if norm < 0.25: continue
        scores = np.einsum("ijk,jk->i", searches, segment) / (search_norm*norm+1e-9)
        # Ignore matches beyond the reasonable coarse cut window.
        shifts = np.arange(len(scores)) / FRAME_RATE - WINDOW_BEFORE - offset
        eligible = abs(shifts) <= RADIUS
        if not eligible.any(): continue
        constrained = np.where(eligible, scores, -2.0)
        idx = int(np.argmax(constrained))
        best = float(constrained[idx])
        separated = eligible & (abs(shifts-shifts[idx]) >= 8)
        second = float(np.max(np.where(separated, constrained, -2.0)))
        margin = best-second
        rows.append({"template_second":offset,"raw_delay_seconds":round(float(shifts[idx]),2),
                     "similarity":round(best,4),"margin":round(margin,4),
                     "strong": bool(best>=MIN_SIMILARITY and margin>=MIN_MARGIN)})
    credible = [x for x in rows if x["strong"]]
    if len(credible)<MIN_STRONG_TEMPLATES:
        return {"status":"insufficient","templates":rows,"strong":len(credible)}
    # Use majority cluster rather than the arithmetic average of wrong hits.
    candidates=[]
    for seed in credible:
        agreeing=[x for x in credible if abs(x["raw_delay_seconds"]-seed["raw_delay_seconds"])<=MAX_DISAGREEMENT_SECONDS]
        if len(agreeing)>=MIN_STRONG_TEMPLATES:
            candidates.append(agreeing)
    if not candidates:
        return {"status":"ambiguous","templates":rows,"strong":len(credible)}
    best=max(candidates,key=lambda group:(len(group),sum(x["similarity"] for x in group)))
    if len(best) < math.ceil(len(credible)*.7):
        return {"status":"ambiguous","templates":rows,"strong":len(credible)}
    return {"status":"matched","raw_delay_seconds":round(float(np.median([x["raw_delay_seconds"] for x in best])),2),
            "mean_similarity":round(float(np.mean([x["similarity"] for x in best])),4),
            "strong":len(best),"templates":rows}


def analyze_group(result: dict, source: dict, references: dict[int,np.ndarray]) -> dict:
    if result.get("status")!="ready" or not result.get("chapters"):
        return {"status":"skipped","reason":"missing_chapters","rows":[]}
    duration = int(result.get("duration_seconds") or 0)
    rows = [x for x in result["chapters"] if x.get("kind")=="episode" and x.get("episode")]
    if not source or not source.get("playable") or not source.get("source_url"):
        return {"status":"skipped","reason":"source_unavailable","rows":[]}
    anchor = [x for x in rows if x.get("method")=="manual-playback-confirmed"
              and x.get("confidence")=="confirmed" and int(x.get("start_seconds") or 0)>100]
    if len(references) < 3:
        return {"status":"needs_three_independent_references","rows":[]}
    # Without a same-recording manual anchor, permit only the 404-416
    # ordinary-episode bundle, whose baseline is an already catalogued chapter
    # sequence. Strict 3-source agreement is still required before publication.
    absolute_mode = not bool(anchor)
    if absolute_mode and int(result.get("episode_start") or -1) != 404:
        return {"status":"needs_local_manual_anchor","rows":[]}
    candidates=[x for x in rows if int(x.get("start_seconds") or 0)>WINDOW_BEFORE
                and int(x.get("start_seconds") or 0)+WINDOW_AFTER < duration]
    url = _lowest_hls_variant(str(source["source_url"]))
    # Extract one short window per chapter, in parallel, not full multi-hour VOD.
    def scan_chapter(chapter):
        ep=int(chapter["episode"])
        start=int(chapter["start_seconds"])
        out={"episode":ep,"existing_start_seconds":start,
             "verified_manual":chapter.get("method")=="manual-playback-confirmed"
                 and chapter.get("confidence")=="confirmed",
             "reference_matches":{}}
        try:
            wave=read_audio(url,start-WINDOW_BEFORE,WINDOW_BEFORE+WINDOW_AFTER)
            feat=fingerprint(wave)
            for ref_ep, ref_feat in references.items():
                out["reference_matches"][str(ref_ep)]=correlate_one(ref_feat,feat)
        except Exception as exc:
            out["error"]=str(exc)[:400]
        return out
    all_rows=[]
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures=[pool.submit(scan_chapter,c) for c in candidates]
        for f in as_completed(futures):
            all_rows.append(f.result())
    all_rows.sort(key=lambda x:x["episode"])
    # Calibrate EACH source separately to the best same-VOD confirmed boundary.
    calibrations={}
    for ref_ep in references:
        verified=[r for r in all_rows if r["verified_manual"]
            and r["reference_matches"].get(str(ref_ep),{}).get("status")=="matched"]
        if verified:
            calibrations[str(ref_ep)]=float(np.median([
                r["reference_matches"][str(ref_ep)]["raw_delay_seconds"] for r in verified]))
    if absolute_mode:
        # Both manual references are independently aligned to the chapter start.
        # The third BGM-derived reference must agree; do not invent a calibration.
        calibrations = {str(ep): 0.0 for ep in references}
    confirmed_eps=set(int(x["episode"]) for x in anchor)
    for row in all_rows:
        proposals=[]
        for ref_ep, calibration in calibrations.items():
            hit=row["reference_matches"].get(ref_ep) or {}
            if hit.get("status")!="matched":continue
            correction=hit["raw_delay_seconds"]-calibration
            proposals.append({"reference_episode":int(ref_ep),
                              "correction_seconds":round(correction,2),
                              "similarity":hit["mean_similarity"],
                              "support_templates":hit["strong"]})
        row["independent_reference_proposals"]=proposals
        if row["episode"] in confirmed_eps:
            row["status"]="protected_confirmed"
        elif len(proposals)<2:
            row["status"]="insufficient_references"
        else:
            corrections=[x["correction_seconds"] for x in proposals]
            if max(corrections)-min(corrections)>3.0:
                row["status"]="disagreement"
            else:
                shift=float(np.median(corrections))
                row["proposed_start_seconds"]=int(round(row["existing_start_seconds"]+shift))
                row["proposed_shift_seconds"]=round(shift,2)
                row["status"]="candidate" if abs(shift)<=MAX_CUT_SHIFT else "large_shift_review"
        print("CUT",json.dumps({"episode":row["episode"],"status":row["status"],
            "proposed_start_seconds":row.get("proposed_start_seconds"),
            "reference_votes":len(proposals)},ensure_ascii=False),flush=True)
    return {"status":"review_only","calibration_from_manual_anchor":calibrations,
            "calibration_mode": "absolute-manual-references" if absolute_mode else "local-manual-anchor",
            "external_manual_reference_episodes": sorted(MANUALLY_VERIFIED_REFERENCES.intersection(references)),
            "manual_anchor_episodes":sorted(confirmed_eps),
            "reference_sources_used":len(references),
            "candidates":sum(r["status"]=="candidate" for r in all_rows),
            "rows":all_rows}


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--ranges",nargs="+",type=int,default=[357,377,387])
    parser.add_argument("--output",default="gmcx_bgm_autocut_review.json")
    args=parser.parse_args()
    catalog=json.loads(Path("kick_replay.json").read_text(encoding="utf-8"))
    state=json.loads(Path("kick_gmcx_chapters.json").read_text(encoding="utf-8"))
    refs,ref_status,ref_owners=read_reference_sources(catalog["vods"],state["results"])
    report={"generated_at":datetime.now(JST).isoformat(),
            "mode":"BGM_audio_fingerprint_cuts_review_only",
            "production_changed":False,"references":ref_status,"bundles":[]}
    by_vod={str(x.get("vod_id")):x for x in catalog["vods"]}
    for start in args.ranges:
        group=next((r for r in state["results"] if r.get("episode_start")==start),None)
        if not group:
            report["bundles"].append({"episode_start":start,"status":"not_found"})
            continue
        # One recording must never vote for itself as an independent reference.
        independent = {ep: audio for ep, audio in refs.items()
                       if ref_owners.get(ep) != str(group.get("vod_id"))}
        result=analyze_group(group,by_vod.get(str(group["vod_id"])),independent)
        result["episode_start"]=start
        report["bundles"].append(result)
    Path(args.output).write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print("SUMMARY",json.dumps([{"start":r.get("episode_start"),"status":r["status"],
        "candidates":r.get("candidates"),"calibration":r.get("calibration_from_manual_anchor")}
        for r in report["bundles"]],ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()
