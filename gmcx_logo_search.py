#!/usr/bin/env python3
"""Read-only search for visually distinctive GCCX title-logo moments.

Unlike fixed 58-minute slicing, search a *region* of the source recording.
A black-background horizontal yellow title-logo shape is a discovery clue,
NOT a verified episode boundary. Two positive and two negative clip controls
must pass before new candidates are reported. Does not edit VOD5/FreeWiFi.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

import numpy as np
from kick_gmcx_chapters import _lowest_hls_variant

JST = timezone(timedelta(hours=9))
WIDTH, HEIGHT = 96, 54
FRAME_SIZE = WIDTH * HEIGHT * 3
SAMPLE_EVERY_SECONDS = 2
SOURCES = {
    "positive_nov09_evening": "df1386fd",
    "positive_nov07_morning": "de35f5fe",
    "negative_nov11_evening": "5847ae05",
    "negative_nov09_morning": "f622346e",
}
# Broad +-7 min probes around previously unverified ~58-minute cuts.
SEEDS = (
    ("5847ae05", 3480, "nov11_second"),
    ("f622346e", 3480, "nov09_morning_second"),
    ("df1386fd", 59096, "nov09_special_false-positive_probe"),
)
RADIUS = 420
BLACK_MIN = 0.74
GOLD_MIN = 0.018


def logo_metrics(frame: bytes) -> dict:
    if len(frame) != FRAME_SIZE:
        raise ValueError("unexpected raw frame length")
    rgb = np.frombuffer(frame, dtype=np.uint8).reshape(HEIGHT, WIDTH, 3).astype(np.int16)
    red, green, blue = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    black = (red < 62) & (green < 62) & (blue < 62)
    gold = ((red > 120) & (green > 95) & (blue < 150)
            & ((red - blue) > 45) & ((green - blue) > 22))
    # The GCCX full-screen logo is central on a near-black frame. Gold
    # patterns elsewhere (games, menus, overlays) should rarely pass both.
    central = gold[12:42, 8:88]
    return {
        "black": round(float(black.mean()), 4),
        "gold": round(float(gold.mean()), 4),
        "central_gold": round(float(central.mean()), 4),
    }


def looks_like_logo(metrics: dict) -> bool:
    return (
        metrics["black"] >= BLACK_MIN
        and metrics["gold"] >= GOLD_MIN
        and metrics["central_gold"] >= GOLD_MIN * 1.2
    )


def scan_bytes(raw: bytes, start_seconds: int) -> list[dict]:
    hits = []
    for frame_index in range(len(raw) // FRAME_SIZE):
        block = raw[frame_index * FRAME_SIZE:(frame_index + 1) * FRAME_SIZE]
        metrics = logo_metrics(block)
        if looks_like_logo(metrics):
            hits.append({
                "seconds": start_seconds + frame_index * SAMPLE_EVERY_SECONDS,
                **metrics,
            })
    # Collapse consecutive 2-second sampled frames of the same title.
    collapsed = []
    for hit in hits:
        if collapsed and hit["seconds"] - collapsed[-1]["last_seconds"] <= 6:
            collapsed[-1]["last_seconds"] = hit["seconds"]
            if hit["gold"] > collapsed[-1]["peak_gold"]:
                collapsed[-1]["peak_gold"] = hit["gold"]
        else:
            collapsed.append({
                "first_seconds": hit["seconds"],
                "last_seconds": hit["seconds"],
                "peak_gold": hit["gold"],
            })
    return collapsed


def decode_window(url: str, start: int, duration: int) -> bytes:
    cmd = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-rw_timeout", "15000000",
        "-ss", str(start), "-i", url, "-t", str(duration),
        "-an", "-vf",
        f"fps=1/{SAMPLE_EVERY_SECONDS},scale={WIDTH}:{HEIGHT}:flags=area,format=rgb24",
        "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1",
    ]
    proc = subprocess.run(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=160, check=False
    )
    if proc.returncode or not proc.stdout:
        raise RuntimeError(
            "video decoder failed: " + proc.stderr.decode("utf-8", "replace")[-180:]
        )
    return proc.stdout


def vetoed(vod_id: str, seconds: float, vetoes: list[dict]) -> bool:
    return any(
        vod_id.startswith(str(veto.get("vod_prefix") or "#none"))
        and abs(seconds - float(veto.get("seconds") or -99999)) <= 10
        for veto in vetoes
    )


def main() -> int:
    replay = json.loads(Path("kick_replay.json").read_text(encoding="utf-8"))
    vods = replay.get("vods", [])
    refs = {}
    for name, prefix in SOURCES.items():
        hits = [v for v in vods if str(v.get("vod_id") or "").startswith(prefix)
                and str(v.get("tvg_id") or "").startswith("kick.gccx")]
        if len(hits) != 1 or not hits[0].get("playable") or not hits[0].get("source_url"):
            raise RuntimeError(f"reference unavailable {name}")
        refs[name] = hits[0]

    def source_url(row: dict) -> str:
        return _lowest_hls_variant(str(row["source_url"]))

    controls = {}
    for name, row in refs.items():
        raw = decode_window(source_url(row), 0, 120)
        controls[name] = scan_bytes(raw, 0)
        print("GCCX_LOGO_CONTROL " + json.dumps({
            "name": name, "logo_like_events": controls[name],
        }, ensure_ascii=False), flush=True)

    valid_positive = all(
        any(20 <= ev["first_seconds"] <= 50 for ev in controls[name])
        for name in SOURCES if name.startswith("positive_")
    )
    valid_negative = all(
        not controls[name] for name in SOURCES if name.startswith("negative_")
    )
    if not valid_positive or not valid_negative:
        result = {
            "generated_at": datetime.now(JST).isoformat(),
            "status": "rejected_by_control_clips",
            "positive_pass": valid_positive, "negative_pass": valid_negative,
            "controls": controls, "rows": [], "production_modified": False,
        }
    else:
        try:
            vetoes = json.loads(Path("gmcx_unresolved_frame_findings.json").read_text(encoding="utf-8"))["findings"]
        except (OSError, KeyError, ValueError):
            raise RuntimeError("video-reviewed false cut veto file missing")
        rows = []
        for prefix, center, label in SEEDS:
            item = next(v for v in refs.values() if str(v["vod_id"]).startswith(prefix))
            start = max(0, center - RADIUS)
            stop = min(int(item.get("duration_seconds") or 0), center + RADIUS)
            row = {"label": label, "vod_id": item["vod_id"], "seed_seconds": center}
            try:
                events = scan_bytes(decode_window(source_url(item), start, stop - start), start)
                row["events"] = [{
                    **e, "video_veto": vetoed(str(item["vod_id"]), e["first_seconds"], vetoes)
                } for e in events]
                row["status"] = "logo_like_candidates_need_audio_and_video_confirmation" if events else "no_logo_found_within_window"
            except Exception as exc:
                row["status"] = "probe_error"
                row["reason"] = str(exc)[:250]
            rows.append(row)
            print("GCCX_LOGO_SEARCH " + json.dumps(row, ensure_ascii=False), flush=True)
        result = {
            "generated_at": datetime.now(JST).isoformat(),
            "status": "read_only_candidates",
            "positive_pass": valid_positive, "negative_pass": valid_negative,
            "controls": controls, "rows": rows, "production_modified": False,
        }
    Path("gmcx_logo_search_review.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("GCCX_LOGO_CONCLUSION " + json.dumps({
        "status": result["status"],
        "tested": len(result["rows"]),
        "candidates": sum(len(x.get("events", [])) for x in result["rows"]),
    }, ensure_ascii=False), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
