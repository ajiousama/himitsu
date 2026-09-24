#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
import statistics
import subprocess
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from pathlib import Path

SRC = Path("kick_replay.json")
TITLE_MAP = Path("gmcx_episode_titles.json")
OUT_JSON = Path("kick_gmcx_chapters.json")
OUT_M3U = Path("kick_gmcx_chapters.m3u")
JST = timezone(timedelta(hours=9))
REPLAY_BASE = "https://kick-resolver.onrender.com/kick?vod="
# Clean archive #90-106 is 59,517 sec / 17 = 3,501 sec per regular episode.
REFERENCE_EPISODE_SECONDS = 3501
AI_WINDOW_SECONDS = 600

# Real-video boundary refinement. GMCX repeats a characteristic title/opening
# frame at the beginning of regular episodes. We learn that recurring visual
# signature inside each VOD and place every split on the same visual cue.
TITLECARD_WINDOW_SECONDS = 150
TITLECARD_SAMPLE_SECONDS = 2
TITLECARD_BOUNDARY_VERSION = 3
TITLECARD_INTRO_SECONDS = 8
TITLECARD_HASH_BITS = 256
TITLECARD_MATCH_DISTANCE = 42
TITLECARD_NEAR_BEST = 4
TITLECARD_MIN_CONTRAST = 28
TITLECARD_MAX_ANALYZE_EPISODES = 24

# Known mixed archive bundles. Regular episodes are first, then the listed special(s).
# A final special with duration_seconds=None consumes the remainder so no footage is lost.
KNOWN_SPECIALS: dict[tuple[int, int], list[dict]] = {
    (107, 116): [
        {
            "key": "2010-oomisoka-gccx",
            "title": "GMCX 大みそかだよ! 有野課長! ～8年間の軌跡…今夜はコントローラーを握らない!?～",
            "after_episode": 116,
            "duration_seconds": 18000,
            "expected_broadcast_seconds": 18000,
        },
        {
            "key": "2010-yoi-matsuri",
            "title": "よゐこの企画案 年越しスペシャル",
            "after_episode": 116,
            "duration_seconds": None,
            "expected_broadcast_seconds": 25200,
        },
    ],
    (117, 130): [
        {
            "key": "2011-usa",
            "title": "GMCX in U.S.A. ～有野課長ロサンゼルスへ行く～",
            "after_episode": 127,
            "duration_seconds": None,
            "expected_broadcast_seconds": 7200,
        },
    ],
    (131, 136): [
        {
            "key": "2012-last30s-live",
            "title": "GMCX 有野30代最後の生挑戦",
            "after_episode": 135,
            "duration_seconds": None,
            "expected_broadcast_seconds": 28800,
        },
    ],
    (137, 156): [
        {
            "key": "2012-in-asia",
            "title": "GMCX in ASIA ～目指せカンボジア代表!～",
            "after_episode": 147,
            "duration_seconds": None,
            "expected_broadcast_seconds": 7200,
        },
    ],
    (157, 166): [
        {
            "key": "2013-famicom30-live",
            "title": "GMCX ファミコン30周年生放送SP",
            "after_episode": 164,
            "duration_seconds": 7200,
            "expected_broadcast_seconds": 7200,
        },
        {
            "key": "2013-terrestrial-live",
            "title": "GMCX 地上波生挑戦",
            "after_episode": 164,
            "duration_seconds": None,
            "expected_broadcast_seconds": 5400,
        },
    ],
    (167, 176): [
        {
            "key": "2013-paris",
            "title": "GMCX in PARIS ～有野課長ジャパンエキスポ参戦～",
            "after_episode": 167,
            "duration_seconds": 7200,
            "expected_broadcast_seconds": 7200,
        },
        {
            "key": "2013-budokan",
            "title": "GMCX 有野の挑戦 in 武道館",
            "after_episode": 171,
            "duration_seconds": None,
            "expected_broadcast_seconds": 7200,
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



def _lowest_hls_variant(url: str) -> str:
    """Prefer the lowest HLS rendition so title-card analysis stays cheap."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 GMCX-titlecard/1.0",
                "Cache-Control": "no-cache",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as res:
            text = res.read(262144).decode("utf-8", "replace")
        if "#EXT-X-STREAM-INF" not in text:
            return url

        lines = [x.strip() for x in text.splitlines()]
        variants = []
        for i, line in enumerate(lines):
            if not line.startswith("#EXT-X-STREAM-INF:"):
                continue
            m = re.search(r"(?:AVERAGE-)?BANDWIDTH=(\d+)", line)
            bw = int(m.group(1)) if m else 10**12
            j = i + 1
            while j < len(lines) and (not lines[j] or lines[j].startswith("#")):
                j += 1
            if j < len(lines):
                variants.append((bw, urllib.parse.urljoin(url, lines[j])))
        if variants:
            variants.sort(key=lambda x: x[0])
            return variants[0][1]
    except Exception as exc:
        print(f"::warning::GMCX title-card master inspect failed: {exc}")
    return url


def _frame_signature(frame: bytes) -> tuple[int, float, int] | None:
    # ffmpeg supplies 17x16 grayscale. dHash => 16 comparisons x 16 rows.
    if len(frame) != 17 * 16:
        return None
    lo, hi = min(frame), max(frame)
    contrast = hi - lo
    mean = sum(frame) / len(frame)
    if contrast < TITLECARD_MIN_CONTRAST or mean < 18 or mean > 238:
        return None

    bits = 0
    bit = 0
    for y in range(16):
        row = y * 17
        for x in range(16):
            if frame[row + x] > frame[row + x + 1]:
                bits |= 1 << bit
            bit += 1
    return bits, mean, contrast


def _sample_titlecard_window(url: str, center: int, total_duration: int) -> list[dict]:
    if total_duration <= 0:
        return []
    if center <= TITLECARD_WINDOW_SECONDS:
        start = 0
        span = min(total_duration, max(1, center + TITLECARD_WINDOW_SECONDS))
    else:
        start = max(0, center - TITLECARD_WINDOW_SECONDS)
        stop = min(total_duration, center + TITLECARD_WINDOW_SECONDS)
        span = max(1, stop - start)

    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-rw_timeout", "15000000",
        "-ss", str(start),
        "-i", url,
        "-t", str(span),
        "-an",
        "-vf", f"fps=1/{TITLECARD_SAMPLE_SECONDS},scale=17:16:flags=area,format=gray",
        "-pix_fmt", "gray",
        "-f", "rawvideo", "pipe:1",
    ]
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=55,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"::warning::GMCX title-card sample failed center={center}: {exc}")
        return []
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace")[-300:]
        print(f"::warning::GMCX title-card ffmpeg failed center={center}: {err}")
        return []

    size = 17 * 16
    frames = []
    raw = proc.stdout
    for idx in range(len(raw) // size):
        sig = _frame_signature(raw[idx * size:(idx + 1) * size])
        if not sig:
            continue
        bits, mean, contrast = sig
        frames.append({
            "time": min(total_duration - 1, start + idx * TITLECARD_SAMPLE_SECONDS),
            "hash": bits,
            "mean": mean,
            "contrast": contrast,
        })
    return frames


def _hdist(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def _learn_titlecard_reference(windows: list[list[dict]]) -> tuple[dict | None, dict]:
    usable = [w for w in windows if w]
    if len(usable) < 3:
        return None, {"reason": "too_few_windows", "usable_windows": len(usable)}

    anchor = usable[0]
    best = None
    for frame in anchor:
        distances = []
        matches = 0
        for w in usable[1:]:
            d = min((_hdist(frame["hash"], x["hash"]) for x in w), default=999)
            distances.append(d)
            if d <= TITLECARD_MATCH_DISTANCE:
                matches += 1
        if not distances:
            continue
        # Require the visual cue to recur in a majority of episode windows.
        required = max(2, int(round((len(usable) - 1) * 0.55)))
        if matches < required:
            continue
        score = statistics.median(distances)
        candidate = (score, -matches, frame["time"], frame)
        if best is None or candidate[:3] < best[:3]:
            best = candidate

    if best is None:
        return None, {"reason": "no_recurring_visual", "usable_windows": len(usable)}
    return best[3], {
        "reason": "ok",
        "usable_windows": len(usable),
        "reference_time_seconds": best[3]["time"],
        "median_distance": best[0],
        "matching_windows": -best[1],
    }


def _best_titlecard_match(reference: dict, frames: list[dict]) -> tuple[int | None, int | None]:
    if not frames:
        return None, None
    scored = [(_hdist(reference["hash"], x["hash"]), x["time"]) for x in frames]
    best_dist = min(x[0] for x in scored)
    if best_dist > TITLECARD_MATCH_DISTANCE:
        return None, best_dist
    # Pick the first frame in the recurring title-card run, not a later frame
    # from the same static card.
    near = [t for d, t in scored if d <= min(TITLECARD_MATCH_DISTANCE, best_dist + TITLECARD_NEAR_BEST)]
    return min(near), best_dist


def _apply_refined_episode_starts(chapters: list[dict], starts: dict[int, int], duration: int) -> list[dict]:
    if not starts:
        return chapters
    out = [dict(x) for x in chapters]

    # Keep VOD start at 0 so pre-roll before the first card is never discarded.
    for item in out:
        if item.get("kind") != "episode":
            continue
        ep = int(item.get("episode") or 0)
        if ep in starts and int(item.get("start_seconds") or 0) > 0:
            item["start_seconds"] = max(0, min(duration - 1, int(starts[ep])))
            item["method"] = "titlecard-consensus"
            item["confidence"] = "high"

    # Guard monotonicity. A dubious match is ignored instead of corrupting VOD.
    for i in range(1, len(out)):
        if int(out[i]["start_seconds"]) <= int(out[i - 1]["start_seconds"]):
            return chapters

    # Rebuild every stop from the next chapter boundary. This also makes a
    # special immediately before a regular episode end exactly at the same
    # recurring title-card cue.
    for i, item in enumerate(out):
        start = int(item["start_seconds"])
        stop = duration if i == len(out) - 1 else int(out[i + 1]["start_seconds"])
        if stop <= start:
            return chapters
        item["stop_seconds"] = stop
        item["duration_seconds"] = stop - start
        item["replay_url"] = clip_url(str(item.get("vod_id") or ""), start, stop - start)
    return out


def refine_with_titlecard(
    vod: dict,
    chapters: list[dict],
    previous_result: dict | None = None,
) -> tuple[list[dict], dict]:
    duration = int(vod.get("duration_seconds") or 0)
    vod_id = str(vod.get("vod_id") or "")
    source_url = str(vod.get("source_url") or "")
    episodes = [x for x in chapters if x.get("kind") == "episode"]
    if duration <= 0 or not source_url or len(episodes) < 3:
        return chapters, {"status": "skipped", "reason": "insufficient_source_or_episodes"}

    # Reuse exact visual boundaries on unchanged VODs.
    if previous_result and int(previous_result.get("duration_seconds") or 0) == duration:
        prev = previous_result.get("titlecard_refinement") or {}
        cached = prev.get("episode_starts") or {}
        if prev.get("status") == "applied" and prev.get("boundary_version") == TITLECARD_BOUNDARY_VERSION and cached:
            starts = {int(k): int(v) for k, v in cached.items()}
            rebuilt = _apply_refined_episode_starts(
                [{**x, "vod_id": vod_id} for x in chapters], starts, duration
            )
            for x in rebuilt:
                x.pop("vod_id", None)
            meta = dict(prev)
            meta["status"] = "applied"
            meta["cache_reused"] = True
            return rebuilt, meta

    if os.environ.get("GMCX_TITLECARD_REFINE", "1") == "0":
        return chapters, {"status": "skipped", "reason": "disabled"}

    analysis_url = _lowest_hls_variant(source_url)
    episode_subset = episodes[:TITLECARD_MAX_ANALYZE_EPISODES]
    windows = []
    window_eps = []
    for item in episode_subset:
        center = int(item.get("start_seconds") or 0)
        frames = _sample_titlecard_window(analysis_url, center, duration)
        windows.append(frames)
        window_eps.append(int(item.get("episode") or 0))

    reference, learned = _learn_titlecard_reference(windows)
    if not reference:
        return chapters, {
            "status": "no_consensus",
            "method": "repeated-titlecard-dhash",
            **learned,
        }

    # The recurring title card is not the episode start. Every regular episode uses
    # the same cartridge-blow intro immediately before the title card. Keep that
    # shared bumper by cutting a fixed amount before every detected title card.
    # 8 seconds was measured on the clean #137 boundary and is reused across VODs.
    lead_in_seconds = TITLECARD_INTRO_SECONDS

    starts = {}
    match_rows = []
    for ep, frames, item in zip(window_eps, windows, episode_subset):
        t, dist = _best_titlecard_match(reference, frames)
        original = int(item.get("start_seconds") or 0)
        if t is None:
            match_rows.append({"episode": ep, "matched": False, "distance": dist, "original": original})
            continue
        refined = max(0, int(t) - lead_in_seconds)
        # Preserve the exact first-episode boundary; it is the source of the intro offset.
        if ep == window_eps[0]:
            refined = original
        starts[ep] = refined
        match_rows.append({
            "episode": ep,
            "matched": True,
            "distance": dist,
            "original": original,
            "refined": refined,
            "shift_seconds": refined - original,
        })

    nonfirst = [x for x in match_rows if x["episode"] != window_eps[0]]
    matched_nonfirst = [x for x in nonfirst if x.get("matched")]
    required = max(2, int(round(len(nonfirst) * 0.55)))
    if len(matched_nonfirst) < required:
        return chapters, {
            "status": "no_consensus",
            "method": "repeated-titlecard-dhash",
            **learned,
            "required_matches": required,
            "matches": match_rows,
        }

    rebuilt = _apply_refined_episode_starts(
        [{**x, "vod_id": vod_id} for x in chapters], starts, duration
    )
    if rebuilt == [{**x, "vod_id": vod_id} for x in chapters]:
        return chapters, {
            "status": "no_consensus",
            "method": "repeated-titlecard-dhash",
            "reason": "monotonicity_guard",
            "matches": match_rows,
        }
    for x in rebuilt:
        x.pop("vod_id", None)

    return rebuilt, {
        "status": "applied",
        "method": "repeated-titlecard-dhash",
        "window_seconds": TITLECARD_WINDOW_SECONDS,
        "sample_seconds": TITLECARD_SAMPLE_SECONDS,
        "boundary_version": TITLECARD_BOUNDARY_VERSION,
        "lead_in_seconds": lead_in_seconds,
        **learned,
        "episode_starts": {str(k): v for k, v in starts.items()},
        "matches": match_rows,
        "cache_reused": False,
    }


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

    specs = [dict(x) for x in KNOWN_SPECIALS.get((start_ep, end_ep), [])]
    extra_total = duration - regular_total
    fixed_extra = sum(int(x.get("duration_seconds") or 0) for x in specs)
    flexible = [x for x in specs if x.get("duration_seconds") is None]

    # The KICK bundle duration tells us exactly how much non-regular footage
    # exists. Known broadcast lengths are hints, but the archive remainder is
    # authoritative for the final flexible special.
    if fixed_extra > extra_total:
        return []
    flexible_total = extra_total - fixed_extra
    if len(flexible) > 1:
        return []
    if flexible:
        flexible[0]["duration_seconds"] = flexible_total
    elif fixed_extra != extra_total:
        return []

    vod_id = str(vod.get("vod_id"))
    by_after: dict[int, list[dict]] = {}
    for spec in specs:
        after_ep = int(spec.get("after_episode") or end_ep)
        by_after.setdefault(after_ep, []).append(spec)

    chapters = []
    cursor = 0
    for ep in range(start_ep, end_ep + 1):
        stop = min(duration, cursor + REFERENCE_EPISODE_SECONDS)
        clip_duration = max(0, stop - cursor)
        chapters.append({
            "kind": "episode",
            "episode": ep,
            "title": titles.get(str(ep), f"第{ep}回"),
            "start_seconds": cursor,
            "stop_seconds": stop,
            "duration_seconds": clip_duration,
            "replay_url": clip_url(vod_id, cursor, clip_duration),
            "method": "chronological-reference-cadence",
            "confidence": "high",
        })
        cursor = stop

        for spec in by_after.get(ep, []):
            requested = int(spec.get("duration_seconds") or 0)
            if requested <= 0 or cursor >= duration:
                continue
            stop = min(duration, cursor + requested)
            clip_duration = max(0, stop - cursor)
            chapters.append({
                "kind": "special",
                "special_key": spec["key"],
                "title": spec["title"],
                "start_seconds": cursor,
                "stop_seconds": stop,
                "duration_seconds": clip_duration,
                "expected_broadcast_seconds": spec.get("expected_broadcast_seconds"),
                "replay_url": clip_url(vod_id, cursor, clip_duration),
                "method": "chronological-known-program-order",
                "confidence": "high",
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

    previous_results = {}
    if OUT_JSON.exists():
        try:
            previous_payload = json.loads(OUT_JSON.read_text(encoding="utf-8"))
            previous_results = {
                str(x.get("vod_id")): x
                for x in previous_payload.get("results", [])
                if x.get("vod_id")
            }
        except Exception:
            previous_results = {}

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

        titlecard_refinement = {"status": "not_applicable"}
        if status == "ready" and chapters:
            chapters, titlecard_refinement = refine_with_titlecard(
                vod,
                chapters,
                previous_results.get(str(vod.get("vod_id"))),
            )

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
            "titlecard_refinement": titlecard_refinement,
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
            label = f"📼 {item['title']} #{ep}"
        lines.append(
            '#EXTINF:-1 group-title="GMCX Replay" '
            f'tvg-id="{tvg_id}" tvg-logo="https://pbs.twimg.com/profile_images/826592912389451777/PnXfhxJD_400x400.jpg",{label}'
        )
        lines.append(item["replay_url"])
    OUT_M3U.write_text("\n".join(lines) + "\n", encoding="utf-8")

    ready = sum(1 for x in results if x.get("status") == "ready")
    ai = sum(1 for x in results if x.get("status") == "ai_required")
    waiting = sum(1 for x in results if x.get("status") == "waiting_live_end")
    unavailable = sum(1 for x in results if x.get("status") == "source_unavailable")
    refined = sum(
        1 for x in results
        if (x.get("titlecard_refinement") or {}).get("status") == "applied"
    )
    print(
        f"GMCX chapters: ready_vods={ready} chapters={len(all_chapters)} "
        f"ai_required={ai} waiting={waiting} source_unavailable={unavailable} "
        f"titlecard_refined={refined}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
