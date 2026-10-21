#!/usr/bin/env python3
"""Audio-only diagnostic for GCCX episode boundaries.

Dry-run: decode short HLS audio windows; search for a recurring opening
sound using a spectral fingerprint learned from a manually confirmed episode.
Never edits chapter files, playlists, or the protected manual boundaries.
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

from kick_gmcx_chapters import _lowest_hls_variant

JST = timezone(timedelta(hours=9))
SAMPLE_RATE = 8000
HOP = 800                # one spectral frame each 0.1 seconds
FFT_SIZE = 2048
TEMPLATE_SECONDS = 5
TEMPLATE_OFFSETS = (2, 10, 18, 26, 34)
SEARCH_BEFORE = 52
SEARCH_DURATION = 126
MIN_SIMILARITY = 0.65
MIN_MARGIN = 0.04
MAX_SEED_SHIFT = 45


def read_audio(source: str, start: float, duration: int) -> np.ndarray:
    command = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-rw_timeout", "25000000",
        "-ss", f"{start:.3f}", "-i", source, "-t", str(duration),
        "-vn", "-ac", "1", "-ar", str(SAMPLE_RATE), "-f", "f32le", "pipe:1",
    ]
    process = subprocess.run(
        command, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=150, check=False,
    )
    if process.returncode:
        raise RuntimeError(
            "ffmpeg audio extract failed: "
            + process.stderr.decode("utf-8", "replace")[-350:]
        )
    signal = np.frombuffer(process.stdout, dtype="<f4")
    if signal.size < SAMPLE_RATE * min(duration // 2, 10):
        raise RuntimeError("short decoded audio; stream may have expired")
    return signal


def fingerprint(signal: np.ndarray) -> np.ndarray:
    if len(signal) < FFT_SIZE:
        raise ValueError("audio too short for fingerprint")
    blocks = np.lib.stride_tricks.sliding_window_view(signal, FFT_SIZE)[::HOP]
    # Short-time spectral shape, resilient to overall loudness differences.
    spectrum = abs(np.fft.rfft(
        blocks * np.hanning(FFT_SIZE), axis=1
    )) ** 2
    freqs = np.fft.rfftfreq(FFT_SIZE, 1 / SAMPLE_RATE)
    bounds = np.geomspace(100, 3700, 17)
    out = []
    for left, right in zip(bounds[:-1], bounds[1:]):
        band = (freqs >= left) & (freqs < right)
        out.append(np.log1p(spectrum[:, band].mean(axis=1)))
    matrix = np.asarray(out, dtype=np.float32).T
    # Remove broad-band loudness and mostly-static segments, so that
    # musical/speech transitions matter more than overall volume.
    matrix -= matrix.mean(axis=1, keepdims=True)
    difference = np.diff(matrix, axis=0, prepend=matrix[:1])
    matrix = np.concatenate((matrix, difference * 1.3), axis=1)
    return matrix.astype(np.float32)


def candidate_matches(anchor: np.ndarray, target: np.ndarray,
                      expected_shift: int = 0) -> list[dict]:
    """Cross-match multiple independent 5-second moments of the opener."""
    template_size = TEMPLATE_SECONDS * SAMPLE_RATE // HOP
    matches = []
    for offset in TEMPLATE_OFFSETS:
        frame_start = int(offset * SAMPLE_RATE / HOP)
        template = anchor[frame_start:frame_start + template_size]
        if template.shape[0] != template_size:
            continue
        tnorm = float(np.linalg.norm(template))
        if tnorm < 0.5:
            continue
        windows = np.lib.stride_tricks.sliding_window_view(
            target, template_size, axis=0
        ).transpose(0, 2, 1)
        cosine = np.sum(windows * template[None], axis=(1, 2)) / (
            np.linalg.norm(windows, axis=(1, 2)) * tnorm + 1e-10
        )
        # Target starts 52s before the existing cut, while anchor begins
        # exactly at the confirmed opening. An offset-matched cue implies
        # the corrected chapter start: old - 52 + match_time - offset.
        shifts = -SEARCH_BEFORE + (
            np.arange(len(cosine), dtype=np.float64) * HOP / SAMPLE_RATE
        ) - offset
        mask = abs(shifts - expected_shift) <= MAX_SEED_SHIFT
        if not mask.any():
            continue
        scores = np.where(mask, cosine, -2.0)
        best_i = int(np.argmax(scores))
        best = float(scores[best_i])
        separated = abs(shifts - shifts[best_i]) >= 8
        second = float(np.max(np.where(mask & separated, scores, -2.0)))
        margin = best - second
        matches.append({
            "template_offset": offset,
            "candidate_shift": round(float(shifts[best_i]), 1),
            "similarity": round(best, 4),
            "margin": round(margin, 4),
            "strong": bool(best >= MIN_SIMILARITY and margin >= MIN_MARGIN),
        })
    return matches


def consensus(matches: list[dict]) -> dict:
    credible = [m for m in matches if m["strong"]]
    if len(credible) < 2:
        return {"status": "insufficient", "strong_matches": len(credible)}
    # Cross-template agreement must hold: one similar jingle later in
    # the episode is not evidence of an episode opening.
    values = sorted(m["candidate_shift"] for m in credible)
    median = float(np.median(values))
    agreeing = [m for m in credible if abs(m["candidate_shift"] - median) <= 3.0]
    if len(agreeing) < 2 or len(agreeing) < math.ceil(len(credible)*0.7):
        return {"status": "ambiguous", "strong_matches": len(credible)}
    return {
        "status": "candidate",
        "shift_seconds": round(float(np.median([m["candidate_shift"] for m in agreeing])), 1),
        "strong_matches": len(agreeing),
        "mean_similarity": round(float(np.mean([m["similarity"] for m in agreeing])), 3),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--range-start", type=int, default=387)
    parser.add_argument("--anchor", type=int, default=388)
    parser.add_argument("--episodes", nargs="+", type=int,
                        default=[389, 390, 393, 394])
    parser.add_argument("--output", default="gmcx_auto_cut_audio_review.json")
    args = parser.parse_args()

    catalog = json.loads(Path("kick_replay.json").read_text(encoding="utf-8"))
    existing = json.loads(Path("kick_gmcx_chapters.json").read_text(encoding="utf-8"))
    result = next(
        r for r in existing["results"]
        if int(r.get("episode_start") or -1) == args.range_start
    )
    vod_id = str(result["vod_id"])
    source = next(v for v in catalog["vods"] if str(v.get("vod_id")) == vod_id)
    chapters = {
        int(c["episode"]): c for c in result["chapters"]
        if c.get("kind") == "episode"
    }
    confirmed = chapters[args.anchor]
    if (
        confirmed.get("method") != "manual-playback-confirmed"
        or confirmed.get("confidence") != "confirmed"
    ):
        raise ValueError("anchor must have a manually confirmed starting time")
    if source.get("playable") is not True:
        raise RuntimeError("source HLS is not marked playable")
    stream = _lowest_hls_variant(str(source["source_url"]))
    anchor_start = int(confirmed["start_seconds"])
    anchor_audio = read_audio(stream, anchor_start, 50)
    anchor_fp = fingerprint(anchor_audio)
    rows = []
    for episode in args.episodes:
        if episode == args.anchor or episode not in chapters:
            continue
        position = int(chapters[episode]["start_seconds"])
        row = {"episode": episode, "current_start_seconds": position}
        try:
            # Audio at the source position may be a few seconds early/late:
            # search a bounded interval without redownloading the full VOD.
            start = max(0, position - SEARCH_BEFORE)
            if start != position - SEARCH_BEFORE:
                raise ValueError("cut too close to the beginning of recording")
            signal = read_audio(stream, start, SEARCH_DURATION)
            matches = candidate_matches(anchor_fp, fingerprint(signal))
            choice = consensus(matches)
            row.update({"audio_matches": matches, **choice})
            if choice["status"] == "candidate":
                row["proposed_start_seconds"] = int(round(position + choice["shift_seconds"]))
                row["verification"] = "pending-video-and-playback-check"
        except Exception as exc:
            row.update({"status": "error", "reason": str(exc)[:400]})
        rows.append(row)
        print(json.dumps({
            k:v for k,v in row.items() if k!="audio_matches"
        }, ensure_ascii=False), flush=True)

    report = {
        "generated_at": datetime.now(JST).isoformat(),
        "mode": "audio_fingerprint_dry_run_only",
        "source_range": result["source_title"],
        "anchor_episode": args.anchor,
        "anchor_start_seconds": anchor_start,
        "manual_overrides_preserved": True,
        "production_changed": False,
        "rows": rows,
    }
    Path(args.output).write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("Audio review candidate count:",
          sum(1 for x in rows if x.get("status") == "candidate"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
