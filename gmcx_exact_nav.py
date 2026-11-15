#!/usr/bin/env python3
"""Use observed programme starts to correct nearby 58-minute GCCX navigation cuts.

This moves ONLY an existing navigation boundary. An observed programme START
does not prove its end or any other episode boundary.
"""
from __future__ import annotations

import json
from pathlib import Path

BOUNDARIES = Path("gmcx_exact_boundaries.json")
MAX_SNAP_SECONDS = 120
MIN_SEGMENT_SECONDS = 120
MAX_SEGMENT_SECONDS = 3605


def validated_starts(vod: dict, range_start: int, range_end: int,
                     source: Path = BOUNDARIES) -> list[int]:
    if not source.is_file():
        return []
    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    if payload.get("schema_version") != 1:
        return []
    vod_id = str(vod.get("vod_id") or "")
    url = str(vod.get("source_url") or "")
    duration = int(vod.get("duration_seconds") or 0)
    if not vod_id or not url or not duration:
        return []
    found: set[int] = set()
    for row in payload.get("boundaries", []):
        if not isinstance(row, dict):
            continue
        if (row.get("source_vod_id") != vod_id
            or row.get("source_url") != url
            or row.get("kind") != "programme_start"
            or row.get("confidence") != "video_intro_observed_episode_end_unverified"):
            continue
        try:
            position = int(row["start_seconds"])
            uncertainty = int(row["start_uncertainty_seconds"])
            recorded_duration = int(row["source_duration_seconds"])
        except (KeyError, TypeError, ValueError):
            continue
        if (not range_start < position < range_end or
            not 0 <= uncertainty <= 3 or
            abs(recorded_duration-duration) > 10):
            continue
        found.add(position)
    return sorted(found)


def snap_verified_starts(spans: list[tuple[int, int]],
                         verified: list[int]) -> list[tuple[int, int]]:
    """Shift adjacent clip edges, preserving every original second exactly once."""
    if len(spans) < 2 or not verified:
        return spans[:]
    output = [list(p) for p in spans]
    for position in sorted(set(verified)):
        matches = [(abs(position-output[i][1]), i)
                   for i in range(len(output)-1)
                   if output[i][1] == output[i+1][0]]
        if not matches:
            continue
        diff, index = min(matches)
        if diff > MAX_SNAP_SECONDS:
            continue
        if (not MIN_SEGMENT_SECONDS <= position-output[index][0] <= MAX_SEGMENT_SECONDS
            or not MIN_SEGMENT_SECONDS <= output[index+1][1]-position <= MAX_SEGMENT_SECONDS):
            continue
        output[index][1] = position
        output[index+1][0] = position
    if (output[0][0] != spans[0][0] or output[-1][1] != spans[-1][1]
        or any(a >= b for a,b in output)
        or any(output[i][1] != output[i+1][0] for i in range(len(output)-1))):
        raise ValueError("Precisely aligned GCCX navigation lost time coverage")
    return [tuple(p) for p in output]
