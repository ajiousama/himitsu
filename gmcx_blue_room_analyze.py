#!/usr/bin/env python3
import json
import statistics
from pathlib import Path

SRC = Path("gmcx_blue_room_candidates.json")
OUT = Path("gmcx_blue_room_gaps.json")

def fmt(sec: float) -> str:
    sec = int(round(sec))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"

def main() -> int:
    if not SRC.exists():
        OUT.write_text(json.dumps({
            "status": "waiting_for_blue_room_candidates",
            "ranges": []
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return 0

    payload = json.loads(SRC.read_text(encoding="utf-8"))
    out_ranges = []

    for block in payload.get("ranges", []):
        rows = sorted(block.get("candidates", []), key=lambda x: int(x["time_seconds"]))
        if len(rows) < 2:
            out_ranges.append({
                **block,
                "status": "too_few_candidates",
                "gaps": []
            })
            continue

        raw_gaps = [
            int(rows[i + 1]["time_seconds"]) - int(rows[i]["time_seconds"])
            for i in range(len(rows) - 1)
        ]

        # Regular episodes cluster around ~58 minutes. Use only plausible
        # 50-70 minute gaps to learn the baseline, so specials don't skew it.
        regular_like = [g for g in raw_gaps if 3000 <= g <= 4200]
        baseline = int(round(statistics.median(regular_like))) if regular_like else int(round(statistics.median(raw_gaps)))

        gaps = []
        for i, gap in enumerate(raw_gaps):
            extra = gap - baseline
            likely_special = extra >= 600  # 10+ min beyond normal cadence
            gaps.append({
                "from_index": i + 1,
                "to_index": i + 2,
                "from_time_seconds": int(rows[i]["time_seconds"]),
                "to_time_seconds": int(rows[i + 1]["time_seconds"]),
                "gap_seconds": gap,
                "gap_display": fmt(gap),
                "baseline_regular_seconds": baseline,
                "baseline_regular_display": fmt(baseline),
                "extra_seconds": max(0, extra),
                "extra_display": fmt(max(0, extra)),
                "likely_special_between": likely_special,
            })

        out_ranges.append({
            "range_start": block.get("range_start"),
            "range_end": block.get("range_end"),
            "vod_id": block.get("vod_id"),
            "source_title": block.get("source_title"),
            "status": "ok",
            "regular_baseline_seconds": baseline,
            "regular_baseline_display": fmt(baseline),
            "candidate_count": len(rows),
            "candidates": rows,
            "gaps": gaps,
        })

    OUT.write_text(json.dumps({
        "status": "ok",
        "ranges": out_ranges
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
