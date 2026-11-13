#!/usr/bin/env python3
"""Review true GCCX opening candidates in still-unidentified long KICK archives.

Conservative read-only diagnostic. A provisional ~58-minute timestamp is a
SEARCH SEED, not proof of a broadcast episode boundary. Never edits VOD5,
chapter JSON, episode titles, manual cuts, or the legacy visual map.
"""
from __future__ import annotations

import argparse
import json
import shutil
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

from kick_gmcx_chapters import (
    _lowest_hls_variant,
    _scan_unclassified_king_title_sequence,
)

JST = timezone(timedelta(hours=9))

# Small first-pass batch. Probe an already-detected historical head as a
# control and a few unclassified heads. Deliberately avoids scanning a full
# 48-hour archive and triggering KICK's rate limit.
TARGETS = (
    ("df1386fd", 3487, 90, "control-visual-map-episode-46"),
    ("df1386fd", 55693, 130, "unknown-tail-first-seed"),
    ("df1386fd", 59173, 130, "unknown-tail-second-seed"),
    ("5847ae05", 3480, 130, "2026-11-11-first-slice"),
    ("f622346e", 3480, 130, "2026-11-09-428-first-slice"),
)


def judge(seed: int, radius: int, candidates: list[dict]) -> dict:
    """Accept a single distinct *candidate*, not a confirmed episode head."""
    near = sorted(
        (c for c in candidates if abs(float(c["king_entry_seconds"]) - seed) <= radius),
        key=lambda c: abs(float(c["king_entry_seconds"]) - seed),
    )
    if not near:
        return {"status": "no_visual_opening_cue", "candidates": []}
    if len(near) >= 2 and abs(
        float(near[0]["king_entry_seconds"]) - float(near[1]["king_entry_seconds"])
    ) >= 8:
        return {"status": "ambiguous", "candidates": near}
    best = near[0]
    proposed = round(float(best["king_entry_seconds"]), 1)
    # "candidate" cannot be published as exact until independent audio and
    # direct playback validate that this is an episode start, not an eyecatch.
    return {
        "status": "visual_candidate_requires_audio_and_playback",
        "proposed_seconds": proposed,
        "shift_from_seed_seconds": round(proposed - seed, 1),
        "cue": best,
        "candidate_count": len(near),
    }


def report(vods: list[dict], targets=TARGETS, detector=None) -> dict:
    detector = detector or _scan_unclassified_king_title_sequence
    rows = []
    for prefix, seed, radius, label in targets:
        source = next(
            (v for v in vods if str(v.get("vod_id") or "").startswith(prefix)
             and str(v.get("tvg_id") or "").startswith("kick.gccx")), None
        )
        row = {
            "label": label, "vod_prefix": prefix,
            "expected_seconds": seed, "radius_seconds": radius,
        }
        if not source or source.get("playable") is not True or not source.get("source_url"):
            row["status"] = "source_unavailable"
        elif not source.get("ready_for_publish") or int(source.get("duration_seconds") or 0) < seed + radius:
            row["status"] = "source_not_finished_or_too_short"
        else:
            try:
                url = _lowest_hls_variant(str(source["source_url"]))
                candidates = detector(url, max(0, seed - radius), seed + radius)
                row.update(judge(seed, radius, candidates))
                row["source_vod_id"] = str(source["vod_id"])
            except Exception as exc:
                row["status"] = "probe_error"
                row["reason"] = str(exc)[:300]
        rows.append(row)
        print("GCCX_OPENING_REVIEW " + json.dumps(row, ensure_ascii=False), flush=True)
        # Avoid launching a tight burst of remote requests. Rate-limit errors
        # are not evidence of a missing title card.
        time.sleep(2)
    return {
        "generated_at": datetime.now(JST).isoformat(),
        "mode": "review_only_no_playlist_changes",
        "results": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--catalog", default="kick_replay.json")
    ap.add_argument("--output", default="gmcx_unresolved_review.json")
    args = ap.parse_args()
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg is missing; refusing to interpret decoder errors as absent title cues")
    vods = json.loads(Path(args.catalog).read_text(encoding="utf-8")).get("vods", [])
    result = report(vods)
    Path(args.output).write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("GCCX_REVIEW_TOTAL " + json.dumps({
        "checked": len(result["results"]),
        "visual_candidates": sum(
            r.get("status") == "visual_candidate_requires_audio_and_playback"
            for r in result["results"]
        ),
        "needs_review": sum(r.get("status") == "ambiguous" for r in result["results"]),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
