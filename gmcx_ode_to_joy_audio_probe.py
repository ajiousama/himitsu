#!/usr/bin/env python3
"""GCCX 'Ode to Joy' recurring opener audio search — evidence only, never auto-split.

Learn an actual recurring audio motif from separate early programme starts in
the same owned KICK recording. An unrelated passage or background performance
must not become an episode boundary without title-video confirmation.

This deliberately does not use a synthetic Beethoven track: a different
recording/arrangement is a poor waveform template. It reuses the project's
audio fingerprint matcher on the recorded broadcast soundtrack.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from gmcx_auto_cut_audio import (read_audio, fingerprint, candidate_matches,
                                 consensus)
from gmcx_long_nav import hms

OUTPUT = Path("gmcx_ode_to_joy_audio_review.json")
SEED_VOD = "df1386fd-4bd1-41ae-ac64-743ff49a838f"
# Provisional #46/#47/#48 etc. These are NOT verified programme starts.
SEEDS = (3487, 6968, 10448, 13929, 20890, 24370)
# Search the likely first opening positions, then the reappearance of ordinary
# episodes following a live special. All times are seconds into a source VOD.
CHECKS = {
  SEED_VOD: [3487,6968,10448,13929,17409,20890,24370,27850,31331,
             34821,38291,41772,45375,48734,90493,93973,97453,
             100933,104413,107893,111373,114853,118333],
  "5847ae05-893e-4ae8-986e-bf0abf888ecf":
      [0,3480,6960,10440,13920,17400,20880,24360,121800,125280,128760],
  "e4f91158-8a0e-4c75-9fb4-eab36c247464":
      [0,3480,6960,10440,13920,17400,97440,100920,104400,107880,111360],
}
MAX_SEARCHES = 30
REFERENCE_DURATION = 75
TARGET_BEFORE = 52
TARGET_DURATION = 126


def main() -> int:
    replay = json.loads(Path("kick_replay.json").read_text(encoding="utf-8"))
    by_id = {v.get("vod_id"): v for v in replay.get("vods", [])
             if v.get("playable") is True and v.get("source_url")}
    report = {
      "generated_utc": datetime.now(timezone.utc).isoformat(),
      "reference_name": "GCCX recurring opening audio candidate (歓喜の歌 / 第九)",
      "reference_status": "unverified_until_video_confirms_title",
      "mode": "audio_fingerprint_dry_run_only",
      "production_changed": False,
      "candidate_starts_are_not_verified_boundaries": True,
      "source_vod_id": SEED_VOD,
      "seed_positions": list(SEEDS),
      "seed_comparisons": [],
      "best_reference": None,
      "checks": [],
    }
    candidates = by_id.get(SEED_VOD)
    if not candidates:
        report["status"] = "source_unavailable"
        OUTPUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
        return 0

    source = candidates["source_url"]
    fp_by_seed = {}
    # Use candidate episode starts rather than a third-party copyrighted
    # recording. Two other episodes must corroborate the picked audio patch.
    for sec in SEEDS:
        try:
            fp_by_seed[sec] = fingerprint(
                read_audio(source, sec, REFERENCE_DURATION))
            print("REFERENCE_AUDIO_OK",sec,flush=True)
        except Exception as exc:
            print("REFERENCE_AUDIO_FAILED",sec,str(exc)[:160],flush=True)
            report["seed_comparisons"].append({
                "second":sec,"status":"decode_failed","reason":str(exc)[:250]})
    best = None
    for ref_sec, fp in fp_by_seed.items():
        comparison = []
        for other_sec in SEEDS:
            if ref_sec==other_sec or other_sec not in fp_by_seed:
                continue
            # Those early candidate starts are within +/-~15 sec of real cuts.
            # A 'candidate' match is evidence for recurring audio, not that
            # the melody is necessarily the Ninth.
            # Reframe the second seed's 75-second audio as a 126-second
            # comparison with an on-schedule expected shift.
            try:
                target = fingerprint(
                    read_audio(source, max(0,other_sec-TARGET_BEFORE),TARGET_DURATION))
                hits=candidate_matches(fp,target)
                decision=consensus(hits)
                comparison.append({"other_start":other_sec,
                                   "result":decision})
            except Exception as exc:
                comparison.append({"other_start":other_sec,
                                   "result":{"status":"decode_failed",
                                             "reason":str(exc)[:160]}})
        strong=[x for x in comparison if x["result"].get("status")=="candidate"]
        weight=sum(x["result"].get("strong_matches",0) for x in strong)
        item={"reference_start":ref_sec, "corroborated_episodes":len(strong),
              "total_votes":weight, "comparisons":comparison}
        report["seed_comparisons"].append(item)
        if len(strong)>=2 and (best is None or (len(strong),weight) > (best[0],best[1])):
            best=(len(strong),weight,ref_sec)
    if not best:
        report["status"] = "no_reproducible_opening_motif_found"
        OUTPUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
        print("OPENER_NO_CORROBORATED_AUDIO_REFERENCE",flush=True)
        return 0
    ref_sec=best[2]
    report["best_reference"]={"vod_id":SEED_VOD,"start_seconds":ref_sec,
                               "corroborating_early_episodes":best[0],
                               "strong_template_votes":best[1]}
    print("OPENER_REFERENCE",ref_sec,"corroborations",best[0],flush=True)
    ref_fp=fp_by_seed[ref_sec]
    inspected=0
    for vod_id, starts in CHECKS.items():
        vod=by_id.get(vod_id)
        if not vod:
            continue
        for nominal_start in starts:
            if inspected >= MAX_SEARCHES:
                break
            if nominal_start<TARGET_BEFORE or nominal_start+100>=int(vod.get("duration_seconds") or 0):
                continue
            inspected+=1
            row={"vod_id":vod_id,"nominal_start_seconds":nominal_start,
                 "status":"unchecked"}
            try:
                audio=read_audio(vod["source_url"],nominal_start-TARGET_BEFORE,TARGET_DURATION)
                hits=candidate_matches(ref_fp,fingerprint(audio))
                found=consensus(hits)
                row.update(found)
                if found.get("status")=="candidate":
                    proposed=nominal_start+float(found["shift_seconds"])
                    row["candidate_start_seconds"]=round(proposed,1)
                    row["time_hms"]=hms(round(proposed))
                    row["requires_video_validation"]=True
            except Exception as exc:
                row.update({"status":"decode_failed","reason":str(exc)[:240]})
            report["checks"].append(row)
            print("OPENER_CHECK",vod_id[:8],nominal_start,
                  row["status"],row.get("candidate_start_seconds"),flush=True)
    report["status"]="audio_candidates_only"
    OUTPUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n")
    print("OPENER_REVIEW_SUMMARY",len(report["checks"]),
          "audio candidate(s)",sum(r.get("status")=="candidate"
                                    for r in report["checks"]),flush=True)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
