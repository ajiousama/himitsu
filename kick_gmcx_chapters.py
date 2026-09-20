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
REPLAY_BASE = "https://himitsu-six.vercel.app/api/kick?vod="
# Clean archive #90-106 is 59,517 sec / 17 = 3,501 sec per regular episode.
REFERENCE_EPISODE_SECONDS = 3501
AI_WINDOW_SECONDS = 600

# Known mixed archive bundles. Regular episodes are first, then the listed special(s).
# A final special with duration_seconds=None consumes the remainder so no footage is lost.
KNOWN_SPECIALS: dict[tuple[int, int], list[dict]] = {
    (107, 116): [
        {
            "key": "2010-oomisoka-gccx",
            "title": "GMCX 大みそかだよ! 有野課長! ～8年間の軌跡…今夜はコントローラーを握らない!?～",
            "duration_seconds": 18000,
            "expected_broadcast_seconds": 18000,
        },
        {
            "key": "2010-yoi-matsuri",
            "title": "よゐこの企画案 年越しスペシャル",
            "duration_seconds": None,
            "expected_broadcast_seconds": 25200,
        },
    ],
    (117, 130): [
        {
            "key": "2011-usa",
            "title": "GMCX in U.S.A. ～有野課長ロサンゼルスへ行く～",
            "duration_seconds": None,
            "expected_broadcast_seconds": 7200,
        },
    ],
    (131, 136): [
        {
            "key": "2012-last30s-live",
            "title": "GMCX 有野30代最後の生挑戦",
            "duration_seconds": None,
            "expected_broadcast_seconds": 43200,
        },
    ],
}

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


def clip_url(vod_id: str, start: int, duration: int) -> str:
    return f"{REPLAY_BASE}{urllib.parse.quote(vod_id)}&start={start}&duration={duration}"


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
        clip_duration = max(0, stop - start)
        title = titles.get(str(ep), f"第{ep}回")
        chapters.append({
            "kind": "episode",
            "episode": ep,
            "title": title,
            "start_seconds": start,
            "stop_seconds": stop,
            "duration_seconds": clip_duration,
            "replay_url": clip_url(str(vod.get("vod_id")), start, clip_duration),
            "method": "uniform-from-clean-vod",
            "confidence": "high" if abs(unit - REFERENCE_EPISODE_SECONDS) <= 120 else "medium",
        })
    return chapters


def make_mixed_chapters(vod: dict, start_ep: int, end_ep: int, titles: dict[str, str]) -> list[dict]:
    count = end_ep - start_ep + 1
    duration = int(vod.get("duration_seconds") or 0)
    regular_total = count * REFERENCE_EPISODE_SECONDS
    if duration < regular_total:
        return []

    vod_id = str(vod.get("vod_id"))
    chapters = []
    for index, ep in enumerate(range(start_ep, end_ep + 1)):
        start = index * REFERENCE_EPISODE_SECONDS
        stop = min(duration, start + REFERENCE_EPISODE_SECONDS)
        clip_duration = max(0, stop - start)
        chapters.append({
            "kind": "episode",
            "episode": ep,
            "title": titles.get(str(ep), f"第{ep}回"),
            "start_seconds": start,
            "stop_seconds": stop,
            "duration_seconds": clip_duration,
            "replay_url": clip_url(vod_id, start, clip_duration),
            "method": "reference-episode-cadence",
            "confidence": "high",
        })

    cursor = regular_total
    for spec in KNOWN_SPECIALS.get((start_ep, end_ep), []):
        if cursor >= duration:
            break
        requested = spec.get("duration_seconds")
        if requested is None:
            stop = duration
        else:
            stop = min(duration, cursor + int(requested))
        clip_duration = max(0, stop - cursor)
        if clip_duration <= 0:
            continue
        chapters.append({
            "kind": "special",
            "special_key": spec["key"],
            "title": spec["title"],
            "start_seconds": cursor,
            "stop_seconds": stop,
            "duration_seconds": clip_duration,
            "expected_broadcast_seconds": spec.get("expected_broadcast_seconds"),
            "replay_url": clip_url(vod_id, cursor, clip_duration),
            "method": "known-program-order",
            "confidence": "high" if requested is not None else "medium",
        })
        cursor = stop

    if cursor < duration:
        clip_duration = duration - cursor
        chapters.append({
            "kind": "special",
            "special_key": f"{start_ep}-{end_ep}-tail",
            "title": "GMCX 追加映像",
            "start_seconds": cursor,
            "stop_seconds": duration,
            "duration_seconds": clip_duration,
            "replay_url": clip_url(vod_id, cursor, clip_duration),
            "method": "unclassified-tail",
            "confidence": "low",
        })
    return chapters


def main() -> int:
    payload = json.loads(SRC.read_text(encoding="utf-8"))
    titles = json.loads(TITLE_MAP.read_text(encoding="utf-8"))
    vods = [x for x in payload.get("vods", []) if str(x.get("tvg_id") or "").startswith("kick.gccx")]

    results = []
    all_chapters = []
    for vod in vods:
        source_title = str(vod.get("title") or "")
        parsed = parse_range(source_title)
        duration = int(vod.get("duration_seconds") or 0)
        if not parsed:
            results.append({
                "vod_id": vod.get("vod_id"),
                "title": source_title,
                "status": "range_unknown",
                "chapters": [],
            })
            continue

        start_ep, end_ep, tail = parsed
        count = end_ep - start_ep + 1
        average = (duration / count) if duration > 0 else 0
        clean_range_only = not tail
        plausible_hour_blocks = 2700 <= average <= 4500 if average else False
        known_mixed = (start_ep, end_ep) in KNOWN_SPECIALS

        if duration <= 0:
            status = "waiting_live_end"
            chapters = []
        elif not vod.get("ready_for_publish"):
            status = "source_unavailable"
            chapters = []
        elif known_mixed:
            chapters = make_mixed_chapters(vod, start_ep, end_ep, titles)
            status = "ready" if chapters else "ai_required"
        elif clean_range_only and plausible_hour_blocks:
            status = "ready"
            chapters = make_uniform_chapters(vod, start_ep, end_ep, titles)
        else:
            status = "ai_required"
            chapters = []

        all_chapters.extend([
            {
                **chapter,
                "vod_id": vod.get("vod_id"),
                "source_title": source_title,
                "range_start": start_ep,
            }
            for chapter in chapters
        ])

        results.append({
            "vod_id": vod.get("vod_id"),
            "source_title": source_title,
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

    core = {
        "reference_episode_seconds": REFERENCE_EPISODE_SECONDS,
        "results": results,
    }
    generated_at = datetime.now(JST).isoformat()
    if OUT_JSON.exists():
        try:
            previous = json.loads(OUT_JSON.read_text(encoding="utf-8"))
            previous_core = {k: v for k, v in previous.items() if k != "generated_at"}
            if previous_core == core and previous.get("generated_at"):
                generated_at = previous["generated_at"]
        except Exception:
            pass
    out = {"generated_at": generated_at, **core}
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    lines = ["#EXTM3U"]
    ordered = sorted(all_chapters, key=lambda x: (int(x.get("range_start") or 9999), int(x.get("start_seconds") or 0)))
    for item in ordered:
        if item.get("kind") == "special":
            key = re.sub(r"[^a-zA-Z0-9._-]+", "-", str(item.get("special_key") or "special")).strip("-")
            tvg_id = f"kick.gmcx.special.{key}"
            label = f"📼 {item['title']}"
        else:
            ep = int(item["episode"])
            tvg_id = f"kick.gmcx.chapter.{ep}"
            label = f"📼 GMCX #{ep} {item['title']}"
        lines.append(
            '#EXTINF:-1 group-title="GMCX Replay" '
            f'tvg-id="{tvg_id}" tvg-logo="https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/kick_gccx2.svg",{label}'
        )
        lines.append(item["replay_url"])
    OUT_M3U.write_text("\n".join(lines) + "\n", encoding="utf-8")

    ready = sum(1 for x in results if x.get("status") == "ready")
    ai = sum(1 for x in results if x.get("status") == "ai_required")
    waiting = sum(1 for x in results if x.get("status") == "waiting_live_end")
    unavailable = sum(1 for x in results if x.get("status") == "source_unavailable")
    print(
        f"GMCX chapters: ready_vods={ready} chapters={len(all_chapters)} "
        f"ai_required={ai} waiting={waiting} source_unavailable={unavailable}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
