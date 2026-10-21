#!/usr/bin/env python3
"""Compare the *actual* title music at the start of GCCX #357/#367/#377.

Read-only. No VOD5 or chapter edits. Looks for repeatable, temporally
consistent audio signatures in the first 105 seconds of separate recordings.
If a music motif is shared, these source VOD heads become independent
reference material for later episode detection.
"""
from __future__ import annotations

import json
import math
import traceback
from datetime import datetime, timezone, timedelta
from pathlib import Path
import numpy as np

from kick_gmcx_chapters import _lowest_hls_variant
from gmcx_auto_cut_audio import read_audio, fingerprint, SAMPLE_RATE, HOP

JST = timezone(timedelta(hours=9))
TARGETS = (357, 367, 377)
INTRO_SECONDS = 105
TEMPLATE_SECONDS = 8
STEP_SECONDS = 5
MIN_COSINE = 0.68
MIN_MARGIN = 0.025
SHIFT_TOLERANCE = 1.5
fps = SAMPLE_RATE / HOP


def similarity_rows(ref: np.ndarray, target: np.ndarray) -> list[dict]:
    """Compare 8-second windows in the two opening recordings."""
    width = int(TEMPLATE_SECONDS * fps)
    rows = []
    windows = np.lib.stride_tricks.sliding_window_view(
        target, width, axis=0
    ).transpose(0, 2, 1)
    wnorms = np.linalg.norm(windows, axis=(1, 2))
    for offset in range(0, 77, STEP_SECONDS):
        idx = round(offset * fps)
        sample = ref[idx:idx + width]
        if len(sample) < width:
            continue
        norm = np.linalg.norm(sample)
        if norm < 0.01:
            continue
        correlation = np.einsum("ijk,jk->i", windows, sample) / (
            wnorms * norm + 1e-8
        )
        best_idx = int(np.argmax(correlation))
        best = float(correlation[best_idx])
        far = abs(np.arange(len(correlation)) - best_idx) >= (8 * fps)
        runnerup = float(np.max(correlation[far])) if far.any() else 0.0
        shift = best_idx / fps - offset
        rows.append({
            "reference_second": offset,
            "matched_second": round(best_idx / fps, 1),
            "shift_seconds": round(shift, 1),
            "similarity": round(best, 4),
            "margin": round(best - runnerup, 4),
            "strong": bool(best >= MIN_COSINE and best-runnerup >= MIN_MARGIN),
        })
    return rows


def cluster_consistent(rows: list[dict]) -> dict:
    valid = [r for r in rows if r["strong"]]
    clusters = []
    for seed in valid:
        members = [r for r in valid if abs(r["shift_seconds"] - seed["shift_seconds"]) <= SHIFT_TOLERANCE]
        if len(members) < 2:
            continue
        if max(x["reference_second"] for x in members) - min(x["reference_second"] for x in members) < 10:
            continue
        clusters.append(members)
    if not clusters:
        return {
            "status": "not_confirmed",
            "strong_windows": len(valid),
            "total_windows": len(rows),
            "reason": "no_multiple_temporally_coherent_music_windows"
        }
    best = max(clusters, key=lambda v: (
        len(v), max(r["reference_second"] for r in v) -
                min(r["reference_second"] for r in v),
        sum(r["similarity"] for r in v)
    ))
    starts = [r["reference_second"] for r in best]
    return {
        "status": "common_audio_detected",
        "strong_windows": len(valid),
        "coherent_windows": len(best),
        "total_windows": len(rows),
        "relative_shift_seconds": round(float(np.median([r["shift_seconds"] for r in best])), 2),
        "common_reference_from_seconds": min(starts),
        "common_reference_to_seconds": max(starts) + TEMPLATE_SECONDS,
        "reference_windows": starts,
        "mean_similarity": round(float(np.mean([r["similarity"] for r in best])), 4),
    }


def match_pair(left: np.ndarray, right: np.ndarray) -> dict:
    rows = similarity_rows(left, right)
    return {"summary": cluster_consistent(rows), "windows": rows}


def main() -> int:
    replay = json.loads(Path("kick_replay.json").read_text(encoding="utf-8"))
    matches = {}
    for ep in TARGETS:
        entry = next((r for r in replay["vods"]
                      if str(r.get("tvg_id") or "").startswith("kick.gccx")
                      and str(r.get("title") or "").split("＃")[-1].startswith(str(ep))), None)
        if not entry:
            raise RuntimeError(f"Cannot locate the source VOD starting at #{ep}")
        matches[ep] = entry

    report = {
        "generated_at": datetime.now(JST).isoformat(),
        "mode": "read_only_title_bgm_source_comparison",
        "sources": [],
        "comparisons": {},
        "production_modified": False,
    }
    vectors = {}
    for ep in TARGETS:
        source = matches[ep]
        row = {
            "first_episode": ep, "vod_id": source["vod_id"],
            "title": source["title"], "audio_window_start_seconds": 0
        }
        try:
            url = _lowest_hls_variant(str(source["source_url"]))
            signal = read_audio(url, 0, INTRO_SECONDS)
            vectors[ep] = fingerprint(signal)
            row.update(status="decoded", samples=int(len(signal)), spectral_frames=int(len(vectors[ep])))
        except Exception as exc:
            row.update(status="failed", error=str(exc)[:500])
        report["sources"].append(row)
        print("AUDIO_SOURCE", json.dumps(row, ensure_ascii=False), flush=True)

    for left, right in ((357, 367), (357, 377), (367, 377)):
        key = f"{left}-{right}"
        if left not in vectors or right not in vectors:
            report["comparisons"][key] = {"summary": {"status": "source_unavailable"}}
            continue
        compared = match_pair(vectors[left], vectors[right])
        report["comparisons"][key] = compared
        print("BGM_MATCH", key, json.dumps(compared["summary"], ensure_ascii=False), flush=True)

    valid_pairs = [x["summary"] for x in report["comparisons"].values()
                   if x["summary"]["status"] == "common_audio_detected"]
    report["conclusion"] = (
        "shared_intro_sound_in_all_three_sources" if len(valid_pairs) == 3
        else "partial_shared_intro" if valid_pairs
        else "no_consistent_common_intro_detected"
    )
    # This program only locates *matching* audio, not the absolute music onset.
    # A confirmed source-head video/music onset alignment is still needed.
    report["title_bgm_absolute_onset_confirmed"] = False
    Path("gmcx_title_bgm_review.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("CONCLUSION", report["conclusion"], flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
