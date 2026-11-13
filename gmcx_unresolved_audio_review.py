#!/usr/bin/env python3
"""Cross-check strong visual GCCX opener candidates against opening audio.

The reference itself is visual-only and provisional, so even a matched BGM is
evidence, not user/playback confirmation. Never alters VOD5 or chapter metadata.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from gmcx_auto_cut_audio import fingerprint, read_audio
from gmcx_bgm_autocut import (
    REFERENCE_CAPTURE, WINDOW_BEFORE, WINDOW_AFTER, correlate_one,
)
from kick_gmcx_chapters import _lowest_hls_variant

JST = timezone(timedelta(hours=9))
STATUS_VISUAL = "strong_visual_candidate_requires_audio_and_playback"


def assess_audio_match(row: dict, match: dict) -> dict:
    status = str(match.get("status") or "")
    offset = float(match.get("raw_delay_seconds") or 9999)
    supported = status == "matched" and abs(offset) <= 12
    return {
        "status": "audio_consistent_needs_manual_video_playback" if supported
        else "audio_not_corrobated",
        "source_vod_id": row.get("source_vod_id"),
        "visual_start_seconds": row["proposed_seconds"],
        "audio_offset_seconds": offset if status == "matched" else None,
        "audio_estimated_start_seconds": round(float(row["proposed_seconds"]) + offset, 1) if supported else None,
        "audio_details": match,
        "publish_as_confirmed_episode": False,
    }


def main() -> int:
    review = json.loads(Path("gmcx_unresolved_review.json").read_text(encoding="utf-8"))
    vods = json.loads(Path("kick_replay.json").read_text(encoding="utf-8")).get("vods", [])
    entries = review.get("results") or []
    reference = next(
        (r for r in entries if r.get("label") == "control-visual-map-episode-46"
         and r.get("status") == STATUS_VISUAL), None
    )
    if reference is None:
        raise RuntimeError("No strong control visual reference; cannot compare BGM reliably")
    by_id = {str(x.get("vod_id")): x for x in vods}
    control_source = by_id.get(str(reference["source_vod_id"]))
    if not control_source or not control_source.get("playable"):
        raise RuntimeError("Control GCCX HLS is not available")

    ref_url = _lowest_hls_variant(str(control_source["source_url"]))
    ref_start = float(reference["proposed_seconds"])
    ref_fp = fingerprint(read_audio(ref_url, ref_start, REFERENCE_CAPTURE))
    output = []
    for row in entries:
        if row is reference or row.get("status") != STATUS_VISUAL:
            continue
        item = {
            "label": row.get("label"),
            "vod_id": row.get("source_vod_id"),
            "visual_seconds": row.get("proposed_seconds"),
        }
        source = by_id.get(str(row.get("source_vod_id")))
        if not source or not source.get("playable"):
            item["status"] = "unavailable"
            output.append(item)
            continue
        try:
            candidate = float(row["proposed_seconds"])
            if candidate <= WINDOW_BEFORE:
                raise ValueError("Candidate too close to recording head")
            analysis_url = _lowest_hls_variant(str(source["source_url"]))
            signal = read_audio(analysis_url, candidate-WINDOW_BEFORE, WINDOW_BEFORE+WINDOW_AFTER)
            match = correlate_one(ref_fp, fingerprint(signal))
            item.update(assess_audio_match(row, match))
        except Exception as exc:
            item.update({"status": "failed", "reason": str(exc)[:300]})
        output.append(item)
        print("GCCX_AUDIO_REVIEW "+json.dumps(item, ensure_ascii=False), flush=True)
    report = {
        "generated_at": datetime.now(JST).isoformat(),
        "status": "read_only_provisional_reference",
        "anchor": {"vod_id": reference["source_vod_id"], "start_seconds": ref_start, "manual_confirmed": False},
        "results": output,
    }
    Path("gmcx_unresolved_audio_review.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8"
    )
    print("GCCX_AUDIO_TOTAL "+json.dumps({
        "checked": len(output),
        "corroborated": sum(x.get("status") == "audio_consistent_needs_manual_video_playback" for x in output),
    }, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
