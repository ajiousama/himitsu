#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import urllib.parse
from datetime import datetime, timezone, timedelta
from pathlib import Path

SRC = Path("kick_replay.json")
TITLE_MAP = Path("gmcx_episode_titles.json")
OUT_JSON = Path("kick_gmcx_chapters.json")
OUT_M3U = Path("kick_gmcx_chapters.m3u")
JST = timezone(timedelta(hours=9))
REPLAY_BASE = "https://himitsu-six.vercel.app/api/kick-replay?vod="
# One clean VOD (#90-106) currently measures 59,517 sec / 17 = 3,501 sec.
# Use this only to propose AI search windows for irregular/SP-mixed VODs.
REFERENCE_EPISODE_SECONDS = 3501
AI_WINDOW_SECONDS = 600

RANGE_RE = re.compile(r"[＃#]\s*(\d+)\s*[-‐‑‒–—―〜~～]\s*(\d+)")


def parse_range(title: str) -> tuple[int, int, str] | None:
    m = RANGE_RE.search(title or "")
    if not m:
        return None
    start, end = int(m.group(1)), int(m.group(2))
    if end < start or end - start > 100:
        return None
    tail = (title[m.end():] or "").strip(" \t　/／-—–")
    return start, end, tail


def build_ai_windows(start_ep: int, end_ep: int, duration: int) -> list[dict]:
    windows = []
    for index, next_ep in enumerate(range(start_ep + 1, end_ep + 1), start=1):
        expected = index * REFERENCE_EPISODE_SECONDS
        if duration > 0:
            expected = min(expected, max(0, duration - 1))
        windows.append({
            "before_episode": next_ep - 1,
            "next_episode": next_ep,
            "expected_offset_seconds": expected,
            "search_from_seconds": max(0, expected - AI_WINDOW_SECONDS),
            "search_to_seconds": min(duration, expected + AI_WINDOW_SECONDS) if duration > 0 else expected + AI_WINDOW_SECONDS,
        })
    return windows


def make_uniform_chapters(vod: dict, start_ep: int, end_ep: int, titles: dict[str, str]) -> list[dict]:
    count = end_ep - start_ep + 1
    duration = int(vod.get("duration_seconds") or 0)
    if count <= 0 or duration <= 0:
        return []
    unit = duration / count
    chapters = []
    for index, ep in enumerate(range(start_ep, end_ep + 1)):
        start = int(round(index * unit))
        stop = duration if index == count - 1 else int(round((index + 1) * unit))
        title = titles.get(str(ep), f"第{ep}回")
        chapters.append({
            "episode": ep,
            "title": title,
            "start_seconds": start,
            "stop_seconds": stop,
            "duration_seconds": max(0, stop - start),
            "replay_url": f"{REPLAY_BASE}{urllib.parse.quote(str(vod.get('vod_id')))}&start={start}",
            "method": "uniform-from-clean-vod",
            "confidence": "high" if abs(unit - REFERENCE_EPISODE_SECONDS) <= 120 else "medium",
        })
    return chapters


def main() -> int:
    payload = json.loads(SRC.read_text(encoding="utf-8"))
    titles = json.loads(TITLE_MAP.read_text(encoding="utf-8"))
    vods = [x for x in payload.get("vods", []) if str(x.get("tvg_id") or "").startswith("kick.gccx")]

    results = []
    all_chapters = []
    for vod in vods:
        title = str(vod.get("title") or "")
        parsed = parse_range(title)
        duration = int(vod.get("duration_seconds") or 0)
        if not parsed:
            results.append({
                "vod_id": vod.get("vod_id"),
                "title": title,
                "status": "range_unknown",
                "chapters": [],
            })
            continue

        start_ep, end_ep, tail = parsed
        count = end_ep - start_ep + 1
        average = (duration / count) if duration > 0 else 0
        clean_range_only = not tail
        plausible_hour_blocks = 2700 <= average <= 4500 if average else False

        if duration <= 0:
            status = "waiting_live_end"
            chapters = []
        elif clean_range_only and plausible_hour_blocks:
            status = "ready"
            chapters = make_uniform_chapters(vod, start_ep, end_ep, titles)
            all_chapters.extend([{**c, "vod_id": vod.get("vod_id"), "source_title": title} for c in chapters])
        else:
            status = "ai_required"
            chapters = []

        results.append({
            "vod_id": vod.get("vod_id"),
            "source_title": title,
            "episode_start": start_ep,
            "episode_end": end_ep,
            "episode_count": count,
            "duration_seconds": duration,
            "average_seconds": round(average, 3) if average else 0,
            "extra_label": tail or None,
            "status": status,
            "chapters": chapters,
            "ai_windows": build_ai_windows(start_ep, end_ep, duration) if status == "ai_required" else [],
        })

    out = {
        "generated_at": datetime.now(JST).isoformat(),
        "reference_episode_seconds": REFERENCE_EPISODE_SECONDS,
        "results": results,
    }
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = ["#EXTM3U"]
    for item in sorted(all_chapters, key=lambda x: (str(x.get("vod_id")), int(x.get("episode") or 0))):
        ep = int(item["episode"])
        label = f"📼 GMCX #{ep} {item['title']}"
        lines.append(
            '#EXTINF:-1 group-title="GMCX Replay" '
            f'tvg-id="kick.gmcx.chapter.{ep}" tvg-logo="https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/kick_gccx2.svg",{label}'
        )
        lines.append(item["replay_url"])
    OUT_M3U.write_text("\n".join(lines) + "\n", encoding="utf-8")

    ready = sum(1 for x in results if x.get("status") == "ready")
    ai = sum(1 for x in results if x.get("status") == "ai_required")
    waiting = sum(1 for x in results if x.get("status") == "waiting_live_end")
    print(f"GMCX chapters: ready_vods={ready} chapters={len(all_chapters)} ai_required={ai} waiting={waiting}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
