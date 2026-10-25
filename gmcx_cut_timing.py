#!/usr/bin/env python3
"""Guard GCCX title-BGM cuts with ordinary episode runtime, not sound alone."""
from __future__ import annotations
from statistics import median

NOMINAL_REGULAR_SECONDS = 58 * 60
MAX_REGULAR_DEVIATION_SECONDS = 90
MIN_CADENCE_SECONDS = 3300
MAX_CADENCE_SECONDS = 3650

def check_chapter_time(chapters: list[dict], index: int, proposed: int,
                       total_duration: int, max_baseline_shift: int = 15) -> dict:
    """Check normal adjacent ~58-min slots; never force specials into that slot."""
    if index <= 0 or index >= len(chapters) or chapters[index].get("kind") != "episode":
        return {"ok": False, "status": "not_regular_episode"}
    original = int(chapters[index].get("start_seconds") or 0)
    if proposed <= 0 or proposed >= total_duration:
        return {"ok": False, "status": "out_of_recording"}
    if abs(proposed-original) > max_baseline_shift:
        return {"ok": False, "status": "too_far_from_existing_schedule"}
    durations = [
        int(b.get("start_seconds") or 0)-int(a.get("start_seconds") or 0)
        for a,b in zip(chapters,chapters[1:])
        if a.get("kind")==b.get("kind")=="episode"
    ]
    normal = [n for n in durations if MIN_CADENCE_SECONDS<=n<=MAX_CADENCE_SECONDS]
    cadence = int(round(median(normal))) if normal else NOMINAL_REGULAR_SECONDS
    observations=[]
    if chapters[index-1].get("kind")=="episode":
        observations.append({"side":"previous","length_seconds":
            proposed-int(chapters[index-1].get("start_seconds") or 0)})
    if index+1<len(chapters) and chapters[index+1].get("kind")=="episode":
        observations.append({"side":"next","length_seconds":
            int(chapters[index+1].get("start_seconds") or 0)-proposed})
    if not observations:
        return {"ok":True,"status":"special_neighbours_baseline_only",
                "cadence_seconds":cadence,"observations":[]}
    passed=all(abs(o["length_seconds"]-cadence)<=MAX_REGULAR_DEVIATION_SECONDS
               for o in observations)
    return {"ok":passed,"status":"audio_and_time_consistent" if passed else "bad_regular_duration",
            "cadence_seconds":cadence,"observations":observations}
