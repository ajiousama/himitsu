#!/usr/bin/env python3
"""Locate GCCX title-audio candidates near unresolved recording boundaries.

Cross-check against TWO distinct KICK VOD intro references that matched each
other but not two negative mid-show controls on 2026-11-13. Requires strong
agreement of both recordings. Produces read-only JSON with potential *audio*
offsets; a result is NOT an episode identity or playback-verified cut.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from gmcx_auto_cut_audio import fingerprint, read_audio
from gmcx_title_bgm_probe import match_pair
from kick_gmcx_chapters import _lowest_hls_variant

JST = timezone(timedelta(hours=9))
REFERENCE_IDS = (
    "df1386fd-4bd1-41ae-ac64-743ff49a838f",
    "de35f5fe-ef68-477c-b44e-d591632facf8",
)
# First 58-minute navigation boundaries and one known false-positive special.
# These are search centres ONLY; not presupposed episode boundaries.
SEEDS = (
    ("5847ae05-893e-4ae8-986e-bf0abf888ecf", 3480, "nov11_part2"),
    ("5847ae05-893e-4ae8-986e-bf0abf888ecf", 6960, "nov11_part3"),
    ("f622346e-33ac-454d-92a5-33b97f89f936", 3480, "nov09_morning_part2"),
    ("df1386fd-4bd1-41ae-ac64-743ff49a838f", 59096, "nov09_false_special_control"),
)
REFERENCE_SECONDS = 105
SEARCH_BEFORE = 180
SEARCH_AFTER = 300
MAX_OFFSET_FROM_SEED = 170
MAX_REFERENCE_DISAGREEMENT = 6


def inspect_seed(seed: int, start: int, references: list[tuple[str, object]],
                 target_fp: object, video_veto: list[dict], vod_id: str) -> dict:
    """Return a candidate only when both audio references independently agree."""
    hits = []
    for ref_id, ref_fp in references:
        summary = match_pair(ref_fp, target_fp)["summary"]
        hit = {"ref": ref_id[:8], "status": summary.get("status"),
               "coherent_windows": summary.get("coherent_windows", 0),
               "similarity": summary.get("mean_similarity")}
        if summary.get("status") == "common_audio_detected":
            position = start + float(summary["relative_shift_seconds"])
            hit["candidate_seconds"] = round(position, 2)
            hit["within_search_guard"] = abs(position - seed) <= MAX_OFFSET_FROM_SEED
        hits.append(hit)
    matched = [x for x in hits if x.get("status") == "common_audio_detected"
               and x.get("within_search_guard")]
    result = {"seed_seconds": seed, "source_id": vod_id,
              "reference_results": hits, "publish_as_episode": False}
    if len(matched) != len(references):
        result["status"] = "insufficient_independent_audio_evidence"
        return result
    proposed = sum(x["candidate_seconds"] for x in matched) / len(matched)
    difference = max(x["candidate_seconds"] for x in matched) - min(
        x["candidate_seconds"] for x in matched
    )
    result["reference_disagreement_seconds"] = round(difference, 2)
    if difference > MAX_REFERENCE_DISAGREEMENT:
        result["status"] = "audio_references_disagree"
        return result
    for finding in video_veto:
        if (str(vod_id).startswith(str(finding.get("vod_prefix") or "#notfound"))
            and abs(proposed - float(finding.get("seconds") or -99999)) <= 10):
            result.update(status="video_review_veto",
                          candidate_seconds=round(proposed, 1),
                          veto_reason=finding.get("context"))
            return result
    result.update(status="two_source_audio_candidate_needs_video_review",
                  candidate_seconds=round(proposed, 1))
    return result


def main() -> int:
    data = json.loads(Path("kick_replay.json").read_text(encoding="utf-8"))
    vods = {str(v.get("vod_id")): v for v in data.get("vods", [])}
    reference_fp = []
    rows = []
    for ref_id in REFERENCE_IDS:
        ref = vods.get(ref_id) or {}
        if not ref.get("playable") or not ref.get("source_url"):
            raise RuntimeError("Independent positive opener recording missing: " + ref_id)
        url = _lowest_hls_variant(str(ref["source_url"]))
        reference_fp.append((ref_id, fingerprint(read_audio(url, 0, REFERENCE_SECONDS))))
    reference_check = match_pair(reference_fp[0][1], reference_fp[1][1])["summary"]
    if reference_check.get("status") != "common_audio_detected":
        raise RuntimeError("Independent intro audio references no longer match")
    try:
        video_veto = json.loads(Path("gmcx_unresolved_frame_findings.json").read_text(encoding="utf-8"))["findings"]
    except (OSError, ValueError, KeyError):
        raise RuntimeError("Verified false-positive veto list missing or corrupt")
    for vod_id, center, label in SEEDS:
        row = {"label": label, "vod_id": vod_id, "seed_seconds": center}
        source = vods.get(vod_id) or {}
        if not source.get("playable") or not source.get("source_url"):
            row["status"] = "source_unavailable"
        elif int(source.get("duration_seconds") or 0) < center + SEARCH_AFTER:
            row["status"] = "insufficient_recording_length"
        else:
            try:
                url = _lowest_hls_variant(str(source["source_url"]))
                window_start = max(0, center - SEARCH_BEFORE)
                target = fingerprint(read_audio(url, window_start, SEARCH_BEFORE + SEARCH_AFTER))
                row.update(inspect_seed(center, window_start, reference_fp, target, video_veto, vod_id))
            except Exception as exc:
                row["status"] = "probe_error"
                row["reason"] = str(exc)[:300]
        print("GCCX_AUDIO_ALIGNMENT " + json.dumps(row, ensure_ascii=False), flush=True)
        rows.append(row)
    output = {
        "generated_at": datetime.now(JST).isoformat(),
        "mode": "read_only_two_independent_intro_sources",
        "reference_validation": reference_check,
        "rows": rows, "production_modified": False,
    }
    Path("gmcx_intro_alignment_review.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
