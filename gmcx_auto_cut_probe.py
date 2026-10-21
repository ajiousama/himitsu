#!/usr/bin/env python3
"""Review-only automatic GCCX episode-head finder.

Finds the recurring king-entry / lower-caption opening in a bounded window
around each 58-minute seed. Calibrates detected cue timing against one
playback-confirmed chapter *in the same source VOD*.

This NEVER rewrites VOD5, chapter JSON, M3U, or manual overrides.
It produces evidence for deciding whether automatic publication is safe.
"""
from __future__ import annotations

import argparse
import json
import statistics
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

from kick_gmcx_chapters import (
    _lowest_hls_variant,
    _scan_unclassified_king_title_sequence,
)

JST = timezone(timedelta(hours=9))
MAX_CANDIDATE_DISTANCE = 45
MAX_CALIBRATION_OFFSET = 25
MAX_SHIFT_FROM_EXISTING = 40


def find_candidate(url: str, center: int, radius: int) -> dict:
    """Reject ambiguous openings; never choose an arbitrary later eye-catch."""
    raw = _scan_unclassified_king_title_sequence(
        url, max(0, center - radius), center + radius
    )
    near = sorted(
        (x for x in raw if abs(float(x["king_entry_seconds"]) - center) <= MAX_CANDIDATE_DISTANCE),
        key=lambda x: abs(float(x["king_entry_seconds"]) - center),
    )
    if not near:
        return {"state": "no_opening_cue", "candidates": raw}
    best = near[0]
    # Multiple credible openings in one short interval need human review.
    if len(near) > 1 and abs(
        float(near[1]["king_entry_seconds"]) - float(best["king_entry_seconds"])
    ) >= 8:
        return {"state": "ambiguous", "candidates": near}
    return {"state": "unique", "candidate": best, "candidates": near}


def review_group(result: dict, source: dict, radius: int, workers: int) -> dict:
    start_ep = int(result.get("episode_start") or 0)
    vod_id = str(result.get("vod_id") or "")
    chapters = result.get("chapters") or []
    output = {
        "range_start": start_ep,
        "source_title": result.get("source_title"),
        "vod_id": vod_id,
        "status": "unavailable",
        "rows": [],
        "recommended_starts": {},
        "publication_safe": False,
    }
    if (
        start_ep < 307 or result.get("status") != "ready"
        or not source or source.get("playable") is not True
        or not source.get("source_url")
    ):
        output["reason"] = "no_usable_hls_or_supported_episode_range"
        return output

    indexes = [
        i for i, c in enumerate(chapters)
        if i > 0 and c.get("kind") == "episode"
    ]
    if not indexes:
        output["reason"] = "no_episode_boundaries"
        return output

    url = _lowest_hls_variant(str(source["source_url"]))
    detected = {}
    with ThreadPoolExecutor(max_workers=max(1, min(workers, 3))) as pool:
        futures = {
            pool.submit(
                find_candidate,
                url,
                int(chapters[i]["start_seconds"]),
                radius,
            ): i
            for i in indexes
        }
        for f in as_completed(futures):
            i = futures[f]
            try:
                detected[i] = f.result()
            except Exception as exc:
                detected[i] = {"state": "error", "reason": str(exc)[:250]}

    # A human-confirmed cut is the timing reference. Provisional shifts
    # propagated from the prior episode are explicitly NOT a reference.
    anchors = []
    for i in indexes:
        c = chapters[i]
        candidate = detected[i]
        if (
            c.get("method") == "manual-playback-confirmed"
            and c.get("confidence") == "confirmed"
            and candidate.get("state") == "unique"
        ):
            observed = float(candidate["candidate"]["king_entry_seconds"])
            anchor_start = int(c["start_seconds"])
            offset = observed - anchor_start
            if abs(offset) <= MAX_CALIBRATION_OFFSET:
                anchors.append({
                    "episode": c.get("episode"),
                    "cue_offset_seconds": offset,
                })

    calibration = None
    if anchors:
        offsets = [x["cue_offset_seconds"] for x in anchors]
        if max(offsets) - min(offsets) <= 4:
            calibration = statistics.median(offsets)
    output["anchors"] = anchors
    output["calibrated_cue_offset_seconds"] = calibration
    output["status"] = "candidates_found" if calibration is not None else "needs_reference"

    for i in indexes:
        c = chapters[i]
        ep = int(c["episode"])
        original = int(c["start_seconds"])
        candidate = detected[i]
        row = {
            "episode": ep,
            "existing_start_seconds": original,
            "detection_state": candidate.get("state"),
            "verified_manual": (
                c.get("method") == "manual-playback-confirmed"
                and c.get("confidence") == "confirmed"
            ),
        }
        if candidate.get("reason"):
            row["reason"] = candidate["reason"]
        if candidate.get("state") == "unique":
            cue = float(candidate["candidate"]["king_entry_seconds"])
            row["detected_king_entry_seconds"] = cue
            row["caption_onset_seconds"] = candidate["candidate"]["caption_onset_seconds"]
            if calibration is not None:
                proposed = int(round(cue - calibration))
                shift = proposed - original
                row["proposed_start_seconds"] = proposed
                row["proposed_shift_seconds"] = shift
                # No blind publishing: only mark independent, nearby detections.
                row["confidence"] = (
                    "manual-locked" if row["verified_manual"]
                    else "high" if abs(shift) <= MAX_SHIFT_FROM_EXISTING
                    else "review"
                )
                if row["verified_manual"]:
                    row["proposed_start_seconds"] = original
                    row["proposed_shift_seconds"] = 0
                elif row["confidence"] == "high":
                    output["recommended_starts"][str(ep)] = proposed
            else:
                row["confidence"] = "uncalibrated"
        else:
            row["confidence"] = "review"
            row["candidate_count"] = len(candidate.get("candidates") or [])
        output["rows"].append(row)

    # A single failed/missing match is not permission to move that chapter.
    # Publication stays disabled until video-sample validation is completed.
    output["requires_review"] = [
        r["episode"] for r in output["rows"]
        if r.get("confidence") in ("review", "uncalibrated")
    ]
    output["status"] = (
        "review_ready" if calibration is not None
        else "needs_reference"
    )
    return output


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--range-start", type=int, default=387,
                    help="First episode number of the VOD bundle")
    ap.add_argument("--radius", type=int, default=40,
                    help="Seconds to scan before and after each current cut (20-90)")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--output", default="gmcx_auto_cut_review.json")
    args = ap.parse_args()
    if not 20 <= args.radius <= 90:
        ap.error("--radius must be between 20 and 90")
    replay = json.loads(Path("kick_replay.json").read_text(encoding="utf-8"))
    chapters = json.loads(Path("kick_gmcx_chapters.json").read_text(encoding="utf-8"))
    source_by_id = {
        str(x.get("vod_id")): x for x in replay.get("vods", [])
        if x.get("vod_id")
    }
    targets = [
        r for r in chapters.get("results", [])
        if int(r.get("episode_start") or 0) == args.range_start
    ]
    if not targets:
        ap.error("requested VOD range was not found")
    result = review_group(targets[0], source_by_id.get(str(targets[0].get("vod_id"))), args.radius, args.workers)
    report = {
        "generated_at": datetime.now(JST).isoformat(),
        "mode": "dry_run_only_no_playlist_changes",
        "radius": args.radius,
        **result,
    }
    Path(args.output).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({
        "status": report["status"],
        "range_start": report["range_start"],
        "anchors": report.get("anchors", []),
        "suggested": report["recommended_starts"],
        "requires_review": report.get("requires_review", []),
        "production_changed": False,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
