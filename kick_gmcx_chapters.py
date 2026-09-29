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
from concurrent.futures import ThreadPoolExecutor, as_completed
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
KNOWN_OP_TEMPLATE_URL = "https://stream.kick.com/0f3cb0ebce7/ivs/v1/196233775518/59bB9isG3qqM/2026/9/27/23/54/mGizRKSX3j3d/media/hls/master.m3u8"
KNOWN_OP_TEMPLATE_SECONDS = 35

# Range-specific cadence measured from clean same-season KICK bundles.
# Season 18's clean #177-196 archive is 77,992 sec / 20 ~= 3,900 sec.
RANGE_EPISODE_SECONDS: dict[tuple[int, int], int] = {
    (177, 196): 3480,
    (197, 206): 3871,
    (207, 216): 3900,
    (217, 226): 3541,
}

# Numbered episodes that are actually long-form specials.
FILELIST_CONFIRMED_RANGES = {
    (177, 196),
    (197, 206),
}

EPISODE_DURATION_OVERRIDES: dict[int, int] = {
    226: 7200,  # in 四国 / 奇々怪界: official 2-hour special
}

# Real-video boundary refinement. GMCX repeats a characteristic title/opening
# frame at the beginning of regular episodes. We learn that recurring visual
# signature inside each VOD and place every split on the same visual cue.
TITLECARD_WINDOW_SECONDS = 240
TITLECARD_SAMPLE_SECONDS = 2
TITLECARD_BOUNDARY_VERSION = 38
TITLECARD_INTRO_SECONDS = 8
TITLECARD_HASH_BITS = 256
TITLECARD_MATCH_DISTANCE = 42
TITLECARD_NEAR_BEST = 4
TITLECARD_MIN_CONTRAST = 28
TITLECARD_MAX_ANALYZE_EPISODES = 24
TITLECARD_STATIC_DISTANCE = 18
TITLECARD_STATIC_TRANSITION_DISTANCE = 30
TITLECARD_STATIC_MAX_FRAME_GAP = TITLECARD_SAMPLE_SECONDS + 1
TITLECARD_REFERENCE_MAX_SECONDS = 30
TITLECARD_SEQUENCE_FRAMES = 3
TITLECARD_SEQUENCE_MATCH_DISTANCE = 34
TITLECARD_SPECIAL_MAX_SHIFT_SECONDS = 150
TITLECARD_REGULAR_MAX_SHIFT_SECONDS = 300
BLUE_ROOM_MIN_BLUE = 48
BLUE_ROOM_BLUE_RED_GAP = 10
BLUE_ROOM_BLUE_GREEN_GAP = 2
BLUE_ROOM_HASH_DISTANCE = 76
BLUE_ROOM_SAMPLE_SECONDS = 2
TITLE_LOGO_SAMPLE_SECONDS = 1
TITLE_LOGO_MIN_YELLOW_RATIO = 0.055
TITLE_LOGO_MIN_DARK_RATIO = 0.55
TITLE_LOGO_MIN_COLUMN_COVERAGE = 0.50
TITLE_LOGO_MIN_ROW_COVERAGE = 0.32
TITLE_LOGO_MIN_RUN_FRAMES = 2
TITLE_LOGO_TEMPLATE_WIDTH = 48
TITLE_LOGO_TEMPLATE_HEIGHT = 12
TITLE_LOGO_TEMPLATE_JACCARD_MIN = 0.24
TITLE_LOGO_EXPECTED_OFFSET_SECONDS = 30
TITLE_LOGO_ANCHOR_FROM_SECONDS = 0
TITLE_LOGO_ANCHOR_TO_SECONDS = 120
ACCESS_FRAME_FROM_SECONDS = 20
ACCESS_FRAME_TO_SECONDS = 45
ACCESS_FRAME_MATCH_DISTANCE = 72
ACCESS_FRAME_CROP = "crop=iw*0.72:ih*0.34:iw*0.14:ih*0.28"
ACCESS_RGB_WIDTH = 32
ACCESS_RGB_HEIGHT = 16
ACCESS_YELLOW_MASK_MIN_PIXELS = 18
ACCESS_YELLOW_JACCARD_MIN = 0.32
ACCESS_YELLOW_MIN_WIDTH_RATIO = 0.38
ACCESS_YELLOW_MIN_HEIGHT_RATIO = 0.18
ACCESS_YELLOW_MIN_RUN_FRAMES = 3
TITLE_LOGO_FEATURE_DISTANCE_MAX = 0.65
TITLE_LOGO_MAX_EXPECTED_DISTANCE_SECONDS = 60
TITLE_LOGO_COMPONENT_MIN_WIDTH_RATIO = 0.42
TITLE_LOGO_COMPONENT_MIN_HEIGHT_RATIO = 0.12
TITLE_LOGO_COMPONENT_MIN_ASPECT = 1.8
TITLE_LOGO_COMPONENT_MAX_ASPECT = 7.5
TITLE_LOGO_COMPONENT_CENTER_TOLERANCE = 0.28
TITLE_LOGO_TEMPLATE_ROWS = (
    "000000000000000000000000000000000000000000000000",
    "000000001111111111111111111110000111110011001100",
    "000100001111111111111111111110001111110011011100",
    "000111100011000100000001000000001111110001111000",
    "000111100010001111110101111000001000110001110000",
    "001101011010111111000001011011011000000001100000",
    "000001011011110111000000011111011001100011100000",
    "000001000010000111011100001000011010100011100000",
    "000010000000000111011000000000011111001100110000",
    "011111111111111111111100000000011110001000110000",
    "011111110110111111111000000000011100000000110000",
    "000000000000000000000000000000000000000000000000",
)
TITLE_LOGO_REFERENCE_SEARCH_SECONDS = 120

# Known mixed archive bundles. Specials are inserted in chronological order before/after episodes.
# A single special with duration_seconds=None consumes the remaining non-regular footage.
KNOWN_SPECIALS: dict[tuple[int, int], list[dict]] = {
    (177, 196): [
        {
            "key": "2014-gccx-the-movie-prefix",
            "title": "ゲームセンターCX THE MOVIE",
            "before_episode": 177,
            "duration_seconds": 3235,
            "expected_broadcast_seconds": 3235,
        },
        {
            "key": "2014-2015-newyear-15min",
            "title": "ゲームセンターCX 年越し15分ミニ枠",
            "after_episode": 191,
            "duration_seconds": 900,
            "expected_broadcast_seconds": 900,
        },
        {
            "key": "2014-dvdbox-vol11-extra",
            "title": "ゲームセンターCX DVD-BOX VOL.11 特典映像",
            "after_episode": 196,
            "duration_seconds": None,
        },
    ],
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
    (197, 206): [
        {
            "key": "2015-niconico-chokaigi",
            "title": "GMCX in ニコニコ超会議2015",
            "after_episode": 199,
            "duration_seconds": 2700,
            "expected_broadcast_seconds": 2700,
        },
        {
            "key": "2015-vietnam",
            "title": "GMCX in VIETNAM ～ベトナムのゲーム事情 徹底調査&カジノにもリベンジしちゃうよ!SP～",
            "after_episode": 203,
            "duration_seconds": 7200,
            "expected_broadcast_seconds": 7200,
        },
    ],
    (207, 216): [
        {
            "key": "2015-mario-maker-prelive",
            "title": "GMCX 生放送直前SP",
            "after_episode": 210,
            "duration_seconds": 300,
            "expected_broadcast_seconds": 300,
        },
        {
            "key": "2015-mario-maker-live",
            "title": "GMCX スーパーマリオメーカーに生挑戦SP ～有野課長VS10000人のクリエーター～",
            "after_episode": 210,
            "duration_seconds": 7200,
            "expected_broadcast_seconds": 7200,
        },
        {
            "key": "2015-link-newyear",
            "title": "GMCX 年越しSP 今年のリベンジ、今年のうちに",
            "after_episode": 210,
            "duration_seconds": 900,
            "expected_broadcast_seconds": 900,
        },
        {
            "key": "2015-season19-unclassified-extra",
            "title": "GMCX 未分類映像（#207〜216 ファイル一覧確認待ち）",
            "after_episode": 210,
            "duration_seconds": None,
            "expected_broadcast_seconds": None,
        },
    ],
    (217, 226): [
        {
            "key": "2016-pokemon-1",
            "title": "GMCX 特別篇 ポケットモンスター赤・緑 #1",
            "after_episode": 219,
            "duration_seconds": 1980,
            "expected_broadcast_seconds": 1980,
        },
        {
            "key": "2016-pokemon-2",
            "title": "GMCX 特別篇 ポケットモンスター赤・緑 #2",
            "after_episode": 222,
            "duration_seconds": 2220,
            "expected_broadcast_seconds": 2220,
        },
        {
            "key": "2016-pokemon-3",
            "title": "GMCX 特別篇 ポケットモンスター赤・緑 #3",
            "after_episode": 224,
            "duration_seconds": 2220,
            "expected_broadcast_seconds": 2220,
        },
        {
            "key": "2016-pokemon-4",
            "title": "GMCX 特別篇 ポケットモンスター赤・緑 #4",
            "after_episode": 225,
            "duration_seconds": 2100,
            "expected_broadcast_seconds": 2100,
        },
        {
            "key": "2016-pokemon-5",
            "title": "GMCX 特別篇 ポケットモンスター赤・緑 #5",
            "after_episode": 226,
            "duration_seconds": 2580,
            "expected_broadcast_seconds": 2580,
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


def _fetch_hls_segment_timeline(url: str) -> list[dict]:
    """Fetch one media playlist and build the same segment timeline used by the resolver."""
    media = _lowest_hls_variant(url)
    try:
        req = urllib.request.Request(
            media,
            headers={
                "User-Agent": "Mozilla/5.0 GMCX-hls-diagnostics/1.0",
                "Cache-Control": "no-cache",
            },
        )
        with urllib.request.urlopen(req, timeout=25) as res:
            text = res.read(4 * 1024 * 1024).decode("utf-8", "replace")
    except Exception as exc:
        print(f"::warning::GMCX HLS diagnostic fetch failed: {exc}")
        return []

    if "#EXT-X-STREAM-INF" in text:
        media2 = _lowest_hls_variant(media)
        if media2 != media:
            try:
                req = urllib.request.Request(
                    media2,
                    headers={
                        "User-Agent": "Mozilla/5.0 GMCX-hls-diagnostics/1.0",
                        "Cache-Control": "no-cache",
                    },
                )
                with urllib.request.urlopen(req, timeout=25) as res:
                    text = res.read(4 * 1024 * 1024).decode("utf-8", "replace")
                media = media2
            except Exception:
                pass

    timeline = []
    cursor = 0.0
    pending = None
    for raw in text.replace("\r", "").split("\n"):
        line = raw.strip()
        if line.startswith("#EXTINF:"):
            try:
                pending = float(line.split(":", 1)[1].split(",", 1)[0])
            except Exception:
                pending = None
            continue
        if not line or line.startswith("#") or pending is None:
            continue
        start = cursor
        stop = cursor + max(0.0, pending)
        timeline.append({
            "start": start,
            "stop": stop,
            "duration": max(0.0, pending),
        })
        cursor = stop
        pending = None
    return timeline


def _segment_aligned_clip(timeline: list[dict], start: int, duration: int) -> dict | None:
    """Mirror services/kick/handler.js clipPlaylist segment selection."""
    if not timeline or duration <= 0:
        return None
    requested_stop = start + duration
    selected = []
    for seg in timeline:
        if float(seg["stop"]) <= start + 0.001:
            continue
        if float(seg["start"]) >= requested_stop - 0.001:
            break
        selected.append(seg)
    if not selected:
        return None
    actual_start = float(selected[0]["start"])
    actual_stop = float(selected[-1]["stop"])
    return {
        "requested_start_seconds": start,
        "requested_duration_seconds": duration,
        "actual_segment_start_seconds": round(actual_start, 3),
        "actual_segment_stop_seconds": round(actual_stop, 3),
        "actual_hls_duration_seconds": round(actual_stop - actual_start, 3),
        "lead_overlap_seconds": round(max(0.0, start - actual_start), 3),
        "tail_overlap_seconds": round(max(0.0, actual_stop - requested_stop), 3),
    }


def _annotate_hls_diagnostics(vod: dict, chapters: list[dict]) -> list[dict]:
    source_url = str(vod.get("source_url") or "")
    if not source_url or not vod.get("playable") or not chapters:
        return chapters
    timeline = _fetch_hls_segment_timeline(source_url)
    if not timeline:
        return chapters
    out = []
    for chapter in chapters:
        row = dict(chapter)
        diag = _segment_aligned_clip(
            timeline,
            int(chapter.get("start_seconds") or 0),
            int(chapter.get("duration_seconds") or 0),
        )
        if diag:
            row["hls_diagnostics"] = diag
        out.append(row)
    return out


def _fetch_hls_join_markers(url: str) -> dict:
    """Inspect the media playlist for hard joins and unusual segment durations."""
    media = _lowest_hls_variant(url)
    try:
        req = urllib.request.Request(media, headers={"User-Agent": "Mozilla/5.0 GMCX-hls-joins/1.0", "Cache-Control": "no-cache"})
        with urllib.request.urlopen(req, timeout=25) as res:
            text = res.read(8 * 1024 * 1024).decode("utf-8", "replace")
    except Exception as exc:
        return {"error": str(exc), "discontinuities": [], "duration_outliers": []}
    durations = []
    discontinuities = []
    cursor = 0.0
    pending = None
    for raw in text.replace("\r", "").split("\n"):
        line = raw.strip()
        if line == "#EXT-X-DISCONTINUITY":
            discontinuities.append(round(cursor, 3))
            continue
        if line.startswith("#EXTINF:"):
            try:
                pending = float(line.split(":", 1)[1].split(",", 1)[0])
            except Exception:
                pending = None
            continue
        if not line or line.startswith("#") or pending is None:
            continue
        durations.append((round(cursor, 3), pending))
        cursor += max(0.0, pending)
        pending = None
    vals = sorted(d for _, d in durations if d > 0)
    median = vals[len(vals)//2] if vals else 0.0
    outliers = [{"time": t, "duration": round(d, 6)} for t, d in durations if median and abs(d-median) >= 0.05][:200]
    return {"media_url": media, "segment_count": len(durations), "median_segment_duration": round(median, 6), "discontinuities": discontinuities, "duration_outliers": outliers}


def _probe_audio_packet_gaps(url: str, center: int, radius: int = 4) -> dict:
    """Probe audio packet timestamp continuity around a suspected episode join."""
    start = max(0, int(center) - int(radius))
    span = max(2, int(radius) * 2)
    cmd = [
        "ffprobe", "-v", "error",
        "-rw_timeout", "15000000",
        "-read_intervals", f"{start}%+{span}",
        "-select_streams", "a:0",
        "-show_entries", "packet=pts_time,duration_time",
        "-of", "json",
        url,
    ]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=35, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"center": center, "error": str(exc), "gaps": []}
    if proc.returncode != 0:
        return {"center": center, "error": proc.stderr.decode("utf-8", "replace")[-300:], "gaps": []}
    try:
        payload = json.loads(proc.stdout.decode("utf-8", "replace"))
    except Exception as exc:
        return {"center": center, "error": f"json: {exc}", "gaps": []}
    gaps = []
    prev_end = None
    for packet in payload.get("packets") or []:
        try:
            pts = float(packet.get("pts_time"))
            dur = float(packet.get("duration_time") or 0.0)
        except Exception:
            continue
        if prev_end is not None:
            gap = pts - prev_end
            if abs(gap) >= 0.004:
                gaps.append({"time": round(pts, 6), "gap_seconds": round(gap, 6)})
        prev_end = pts + dur
    gaps.sort(key=lambda x: abs(float(x["gap_seconds"])), reverse=True)
    return {"center": center, "start": start, "span": span, "gap_count": len(gaps), "gaps": gaps[:12]}


def _probe_video_packet_joins(url: str, center: int, radius: int = 6) -> dict:
    """Probe video DTS continuity and keyframe layout around a suspected join."""
    # HLS seeks may land well before the requested timestamp. Read a wider span,
    # then filter packets back to the real +/- radius window around the join.
    start = max(0, int(center) - 18)
    span = 36
    window_lo = float(center - radius)
    window_hi = float(center + radius)
    cmd = [
        "ffprobe", "-v", "error",
        "-rw_timeout", "15000000",
        "-read_intervals", f"{start}%+{span}",
        "-select_streams", "v:0",
        "-show_entries", "packet=pts_time,dts_time,duration_time,flags",
        "-of", "json",
        url,
    ]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        return {"center": center, "error": str(exc), "dts_gaps": [], "keyframes": []}
    if proc.returncode != 0:
        return {"center": center, "error": proc.stderr.decode("utf-8", "replace")[-300:], "dts_gaps": [], "keyframes": []}
    try:
        payload = json.loads(proc.stdout.decode("utf-8", "replace"))
    except Exception as exc:
        return {"center": center, "error": f"json: {exc}", "dts_gaps": [], "keyframes": []}
    gaps = []
    keyframes = []
    prev_end = None
    for packet in payload.get("packets") or []:
        try:
            dts = float(packet.get("dts_time"))
            pts = float(packet.get("pts_time") or dts)
            dur = float(packet.get("duration_time") or 0.0)
        except Exception:
            continue
        flags = str(packet.get("flags") or "")
        if "K" in flags and window_lo <= pts <= window_hi:
            keyframes.append(round(pts, 6))
        if prev_end is not None and window_lo <= dts <= window_hi:
            gap = dts - prev_end
            if abs(gap) >= 0.002:
                gaps.append({"time": round(dts, 6), "gap_seconds": round(gap, 6)})
        prev_end = dts + dur
    gaps.sort(key=lambda x: abs(float(x["gap_seconds"])), reverse=True)
    return {
        "center": center,
        "start": start,
        "span": span,
        "window_lo": window_lo,
        "window_hi": window_hi,
        "dts_gap_count": len(gaps),
        "dts_gaps": gaps[:12],
        "keyframes": keyframes,
        "nearest_keyframe_offset": round(min((k - center for k in keyframes), key=lambda x: abs(x)), 6) if keyframes else None,
    }


def _probe_selected_episode_joins(url: str, chapters: list[dict]) -> list[dict]:
    out = []
    for chapter in chapters:
        ep = chapter.get("episode")
        if ep not in {184, 185, 186, 187, 188}:
            continue
        center = int(chapter.get("start_seconds") or 0)
        out.append({
            "episode": ep,
            "center": center,
            "audio": _probe_audio_packet_gaps(url, center),
            "video": _probe_video_packet_joins(url, center),
        })
    return out


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


def _sample_titlecard_window(
    url: str,
    center: int,
    total_duration: int,
    window_seconds: int | None = None,
) -> list[dict]:
    if total_duration <= 0:
        return []
    radius = int(window_seconds or TITLECARD_WINDOW_SECONDS)
    if center <= radius:
        start = 0
        span = min(total_duration, max(1, center + radius))
    else:
        start = max(0, center - radius)
        stop = min(total_duration, center + radius)
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


def _sample_blue_room_window(url: str, center: int, total_duration: int) -> list[dict]:
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
        "-vf", f"fps=1/{BLUE_ROOM_SAMPLE_SECONDS},scale=17:16:flags=area,format=rgb24",
        "-pix_fmt", "rgb24",
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
        print(f"::warning::GMCX blue-room sample failed center={center}: {exc}")
        return []
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace")[-300:]
        print(f"::warning::GMCX blue-room ffmpeg failed center={center}: {err}")
        return []

    size = 17 * 16 * 3
    frames = []
    raw = proc.stdout
    for idx in range(len(raw) // size):
        frame = raw[idx * size:(idx + 1) * size]
        rs = frame[0::3]
        gs = frame[1::3]
        bs = frame[2::3]
        if not rs or not gs or not bs:
            continue
        rmean = sum(rs) / len(rs)
        gmean = sum(gs) / len(gs)
        bmean = sum(bs) / len(bs)
        if (
            bmean < BLUE_ROOM_MIN_BLUE
            or bmean - rmean < BLUE_ROOM_BLUE_RED_GAP
            or bmean - gmean < BLUE_ROOM_BLUE_GREEN_GAP
        ):
            continue

        gray = bytearray(len(rs))
        for p in range(len(rs)):
            gray[p] = int(0.299 * rs[p] + 0.587 * gs[p] + 0.114 * bs[p])
        sig = _frame_signature(bytes(gray))
        if not sig:
            continue
        bits, mean, contrast = sig
        frames.append({
            "time": min(total_duration - 1, start + idx * BLUE_ROOM_SAMPLE_SECONDS),
            "hash": bits,
            "mean": mean,
            "contrast": contrast,
            "blue_mean": round(bmean, 2),
            "blue_red_gap": round(bmean - rmean, 2),
            "blue_green_gap": round(bmean - gmean, 2),
        })
    return frames


def _learn_blue_room_reference(windows: list[list[dict]]) -> tuple[dict | None, dict]:
    usable = [w for w in windows if w]
    if len(usable) < 3:
        return None, {"reason": "too_few_blue_windows", "usable_windows": len(usable)}

    # Learn the recurring opening from every usable episode window.
    anchor = [frame for w in usable for frame in w]
    best = None
    for frame in anchor:
        matches = 0
        distances = []
        for w in usable:
            d = min((_hdist(frame["hash"], x["hash"]) for x in w), default=999)
            distances.append(d)
            if d <= BLUE_ROOM_HASH_DISTANCE:
                matches += 1
        required = max(3, int(round(len(usable) * 0.55)))
        if matches < required:
            continue
        score = statistics.median(distances)
        candidate = (score, -matches, frame["time"], frame)
        if best is None or candidate[:3] < best[:3]:
            best = candidate

    if best is None:
        return None, {"reason": "no_recurring_blue_room", "usable_windows": len(usable)}
    return best[3], {
        "reason": "ok",
        "usable_windows": len(usable),
        "reference_time_seconds": int(best[3]["time"]),
        "median_distance": round(float(best[0]), 3),
        "matching_windows": -best[1],
    }


def _best_blue_room_match(reference: dict, frames: list[dict]) -> tuple[int | None, int | None]:
    if not frames:
        return None, None
    scored = [(_hdist(reference["hash"], x["hash"]), int(x["time"])) for x in frames]
    best_dist = min(x[0] for x in scored)
    if best_dist > BLUE_ROOM_HASH_DISTANCE:
        return None, best_dist
    near = [t for d, t in scored if d <= min(BLUE_ROOM_HASH_DISTANCE, best_dist + 4)]
    return min(near), best_dist


def _title_logo_template_mask() -> int:
    bits = 0
    bit = 0
    for row in TITLE_LOGO_TEMPLATE_ROWS:
        for ch in row:
            if ch == "1":
                bits |= 1 << bit
            bit += 1
    return bits


TITLE_LOGO_TEMPLATE_MASK = _title_logo_template_mask()


def _normalise_yellow_logo(frame: bytes, width: int, height: int) -> dict | None:
    yellow = [[False for _ in range(width)] for _ in range(height)]
    dark_count = 0
    for y in range(height):
        for x in range(width):
            p = (y * width + x) * 3
            rr, gg, bb = frame[p], frame[p + 1], frame[p + 2]
            yellow[y][x] = (
                rr > 110 and gg > 100 and bb < 155
                and rr - bb > 30 and gg - bb > 25
            )
            if rr < 75 and gg < 75 and bb < 75:
                dark_count += 1

    # One-pixel dilation connects the border and letters of the large GMCX logo.
    dilated = [[False for _ in range(width)] for _ in range(height)]
    for y in range(height):
        for x in range(width):
            if not yellow[y][x]:
                continue
            for dy in (-1, 0, 1):
                yy = y + dy
                if yy < 0 or yy >= height:
                    continue
                for dx in (-1, 0, 1):
                    xx = x + dx
                    if 0 <= xx < width:
                        dilated[yy][xx] = True

    seen = [[False for _ in range(width)] for _ in range(height)]
    components = []
    for sy in range(height):
        for sx in range(width):
            if not dilated[sy][sx] or seen[sy][sx]:
                continue
            stack = [(sx, sy)]
            seen[sy][sx] = True
            min_x = max_x = sx
            min_y = max_y = sy
            pixels = 0
            while stack:
                x, y = stack.pop()
                pixels += 1
                min_x = min(min_x, x)
                max_x = max(max_x, x)
                min_y = min(min_y, y)
                max_y = max(max_y, y)
                for dx, dy in ((1,0),(-1,0),(0,1),(0,-1)):
                    xx, yy = x + dx, y + dy
                    if (
                        0 <= xx < width and 0 <= yy < height
                        and dilated[yy][xx] and not seen[yy][xx]
                    ):
                        seen[yy][xx] = True
                        stack.append((xx, yy))
            bw = max_x - min_x + 1
            bh = max_y - min_y + 1
            aspect = bw / max(1, bh)
            cx = (min_x + max_x) / 2 / width
            cy = (min_y + max_y) / 2 / height
            components.append({
                "pixels": pixels,
                "min_x": min_x, "max_x": max_x,
                "min_y": min_y, "max_y": max_y,
                "width": bw, "height": bh,
                "aspect": aspect,
                "cx": cx, "cy": cy,
            })

    candidates = []
    for c in components:
        width_ratio = c["width"] / width
        height_ratio = c["height"] / height
        if width_ratio < TITLE_LOGO_COMPONENT_MIN_WIDTH_RATIO:
            continue
        if height_ratio < TITLE_LOGO_COMPONENT_MIN_HEIGHT_RATIO:
            continue
        if not (TITLE_LOGO_COMPONENT_MIN_ASPECT <= c["aspect"] <= TITLE_LOGO_COMPONENT_MAX_ASPECT):
            continue
        if abs(c["cx"] - 0.5) > TITLE_LOGO_COMPONENT_CENTER_TOLERANCE:
            continue
        if not (0.30 <= c["cy"] <= 0.62):
            continue

        # Count actual yellow pixels inside the connected component's box.
        yellow_count = 0
        total = c["width"] * c["height"]
        for y in range(c["min_y"], c["max_y"] + 1):
            for x in range(c["min_x"], c["max_x"] + 1):
                if yellow[y][x]:
                    yellow_count += 1
        yellow_fill = yellow_count / max(1, total)
        if yellow_fill < 0.10:
            continue

        score = (
            -width_ratio,
            abs(c["cx"] - 0.5),
            abs(c["cy"] - 0.49),
            -yellow_fill,
        )
        candidates.append((score, c, yellow_fill))

    if not candidates:
        return None

    candidates.sort(key=lambda x: x[0])
    _, c, yellow_fill = candidates[0]
    dark_ratio = dark_count / (width * height)
    return {
        "mask": 0,
        "jaccard": 1.0,
        "bbox_width": c["width"],
        "bbox_height": c["height"],
        "width_ratio": round(c["width"] / width, 4),
        "height_ratio": round(c["height"] / height, 4),
        "aspect": round(c["aspect"], 3),
        "center_x": round(c["cx"], 4),
        "center_y": round(c["cy"], 4),
        "yellow_fill": round(yellow_fill, 4),
        "dark_ratio": round(dark_ratio, 4),
    }
def _yellow_mask_signature(frame: bytes, width: int, height: int) -> tuple[int, int] | None:
    if len(frame) != width * height * 3:
        return None
    yellow_points = []
    bits = 0
    bit = 0
    count = 0
    for y in range(height):
        for x in range(width):
            p = (y * width + x) * 3
            r, g, b = frame[p], frame[p + 1], frame[p + 2]
            is_yellow = (
                r >= 105 and g >= 95 and b <= 150
                and r - b >= 28 and g - b >= 22
                and abs(int(r) - int(g)) <= 95
            )
            if is_yellow:
                bits |= 1 << bit
                count += 1
                yellow_points.append((x, y))
            bit += 1

    if count < ACCESS_YELLOW_MASK_MIN_PIXELS or not yellow_points:
        return None

    min_x = min(x for x, _ in yellow_points)
    max_x = max(x for x, _ in yellow_points)
    min_y = min(y for _, y in yellow_points)
    max_y = max(y for _, y in yellow_points)
    width_ratio = (max_x - min_x + 1) / width
    height_ratio = (max_y - min_y + 1) / height
    center_x = ((min_x + max_x) / 2) / width
    center_y = ((min_y + max_y) / 2) / height

    # Reject small persistent corner bugs/watermarks. The real title is a
    # large object centered in the frame.
    if width_ratio < ACCESS_YELLOW_MIN_WIDTH_RATIO:
        return None
    if height_ratio < ACCESS_YELLOW_MIN_HEIGHT_RATIO:
        return None
    if abs(center_x - 0.5) > 0.24 or abs(center_y - 0.5) > 0.30:
        return None

    return bits, count


def _shift_mask(bits: int, width: int, height: int, dx: int, dy: int) -> int:
    out = 0
    for y in range(height):
        yy = y + dy
        if yy < 0 or yy >= height:
            continue
        for x in range(width):
            xx = x + dx
            if xx < 0 or xx >= width:
                continue
            src = y * width + x
            if bits & (1 << src):
                out |= 1 << (yy * width + xx)
    return out


def _yellow_mask_similarity(a: int, b: int) -> float:
    best = 0.0
    for dy in (-1, 0, 1):
        for dx in (-2, -1, 0, 1, 2):
            shifted = _shift_mask(b, ACCESS_RGB_WIDTH, ACCESS_RGB_HEIGHT, dx, dy)
            union = (a | shifted).bit_count()
            if not union:
                continue
            score = (a & shifted).bit_count() / union
            if score > best:
                best = score
    return best


def _sample_access_frame_signatures(
    url: str,
    start: int,
    span: int,
    total_duration: int,
) -> list[dict]:
    if total_duration <= 0 or span <= 0:
        return []
    start = max(0, min(start, total_duration - 1))
    span = min(span, max(1, total_duration - start))
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-rw_timeout", "15000000",
        "-ss", str(start),
        "-i", url,
        "-t", str(span),
        "-an",
        "-vf",
        f"fps=1,{ACCESS_FRAME_CROP},scale={ACCESS_RGB_WIDTH}:{ACCESS_RGB_HEIGHT}:flags=area,format=rgb24",
        "-pix_fmt", "rgb24",
        "-f", "rawvideo", "pipe:1",
    ]
    try:
        proc = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=45,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"::warning::GMCX access-frame sample failed start={start}: {exc}")
        return []
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace")[-300:]
        print(f"::warning::GMCX access-frame ffmpeg failed start={start}: {err}")
        return []

    frame_size = ACCESS_RGB_WIDTH * ACCESS_RGB_HEIGHT * 3
    raw = proc.stdout
    out = []
    for idx in range(len(raw) // frame_size):
        frame = raw[idx * frame_size:(idx + 1) * frame_size]
        sig = _yellow_mask_signature(frame, ACCESS_RGB_WIDTH, ACCESS_RGB_HEIGHT)
        if not sig:
            continue
        mask, yellow_pixels = sig
        out.append({
            "time": start + idx,
            "yellow_mask": mask,
            "yellow_pixels": yellow_pixels,
        })
    return out


def _pick_access_reference(frames: list[dict]) -> tuple[dict | None, dict]:
    candidates = [
        x for x in frames
        if ACCESS_FRAME_FROM_SECONDS <= int(x["time"]) <= ACCESS_FRAME_TO_SECONDS
        and int(x.get("yellow_pixels") or 0) >= ACCESS_YELLOW_MASK_MIN_PIXELS
    ]
    if not candidates:
        return None, {"reason": "no_access_yellow_logo_reference"}

    candidates.sort(
        key=lambda x: (
            abs(int(x["time"]) - 30),
            -int(x.get("yellow_pixels") or 0),
        )
    )
    ref = candidates[0]
    return ref, {
        "reason": "ok",
        "reference_time_seconds": int(ref["time"]),
        "yellow_pixels": int(ref.get("yellow_pixels") or 0),
        "source": "vod-access-yellow-logo-20-45s",
    }

def _match_access_reference(reference: dict, frames: list[dict], expected_time: int) -> tuple[int | None, dict]:
    if not frames:
        return None, {"reason": "no_access_frames"}

    ref_mask = int(reference.get("yellow_mask") or 0)
    matched = []
    for x in sorted(frames, key=lambda row: int(row["time"])):
        time_distance = abs(int(x["time"]) - expected_time)
        if time_distance > TITLE_LOGO_MAX_EXPECTED_DISTANCE_SECONDS:
            continue
        similarity = _yellow_mask_similarity(
            ref_mask,
            int(x.get("yellow_mask") or 0),
        )
        if similarity < ACCESS_YELLOW_JACCARD_MIN:
            continue
        matched.append({
            "time": int(x["time"]),
            "similarity": float(similarity),
            "yellow_pixels": int(x.get("yellow_pixels") or 0),
        })

    runs = []
    current = []
    for row in matched:
        if not current or row["time"] - current[-1]["time"] <= 1:
            current.append(row)
        else:
            if len(current) >= ACCESS_YELLOW_MIN_RUN_FRAMES:
                runs.append(current)
            current = [row]
    if len(current) >= ACCESS_YELLOW_MIN_RUN_FRAMES:
        runs.append(current)

    if not runs:
        return None, {
            "reason": "yellow_logo_no_stable_run",
            "candidate_frames": len(matched),
        }

    candidates = []
    for run in runs:
        run_start = int(run[0]["time"])
        best_similarity = max(x["similarity"] for x in run)
        avg_similarity = sum(x["similarity"] for x in run) / len(run)
        distance = abs(run_start - expected_time)
        candidates.append((
            distance,
            -round(avg_similarity, 5),
            -len(run),
            run_start,
            best_similarity,
            avg_similarity,
        ))

    # Stay close to the expected chronological boundary first. The visual
    # match must be stable, but a gameplay lookalike far away must never win.
    candidates.sort()
    distance, _, run_len_neg, best_time, best_sim, avg_sim = candidates[0]
    return best_time, {
        "reason": "ok",
        "yellow_jaccard": round(float(best_sim), 4),
        "yellow_jaccard_avg": round(float(avg_sim), 4),
        "run_frames": -run_len_neg,
        "expected_time": expected_time,
        "distance_from_expected": best_time - expected_time,
    }


def _sample_title_logo_window(url: str, center: int, total_duration: int) -> list[dict]:
    if total_duration <= 0:
        return []
    if center <= TITLECARD_WINDOW_SECONDS:
        start = 0
        span = min(total_duration, max(1, center + TITLECARD_WINDOW_SECONDS))
    else:
        start = max(0, center - TITLECARD_WINDOW_SECONDS)
        stop = min(total_duration, center + TITLECARD_WINDOW_SECONDS)
        span = max(1, stop - start)

    width, height = 64, 36
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-rw_timeout", "15000000",
        "-ss", str(start),
        "-i", url,
        "-t", str(span),
        "-an",
        "-vf", f"fps=1/{TITLE_LOGO_SAMPLE_SECONDS},scale={width}:{height}:flags=area,format=rgb24",
        "-pix_fmt", "rgb24",
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
        print(f"::warning::GMCX title-logo sample failed center={center}: {exc}")
        return []
    if proc.returncode != 0:
        err = proc.stderr.decode("utf-8", "replace")[-300:]
        print(f"::warning::GMCX title-logo ffmpeg failed center={center}: {err}")
        return []

    frame_size = width * height * 3
    raw = proc.stdout
    out = []
    for idx in range(len(raw) // frame_size):
        frame = raw[idx * frame_size:(idx + 1) * frame_size]
        logo = _normalise_yellow_logo(frame, width, height)
        if not logo:
            continue
        out.append({
            "time": min(total_duration - 1, start + idx * TITLE_LOGO_SAMPLE_SECONDS),
            **logo,
        })
    return out


def _title_logo_runs(frames: list[dict]) -> list[list[dict]]:
    runs = []
    current = []
    for frame in sorted(frames, key=lambda x: int(x["time"])):
        if not current:
            current = [frame]
            continue
        gap = int(frame["time"]) - int(current[-1]["time"])
        if 0 < gap <= TITLE_LOGO_SAMPLE_SECONDS + 1:
            current.append(frame)
        else:
            if len(current) >= TITLE_LOGO_MIN_RUN_FRAMES:
                runs.append(current)
            current = [frame]
    if len(current) >= TITLE_LOGO_MIN_RUN_FRAMES:
        runs.append(current)
    return runs


def _mask_jaccard(a: int, b: int) -> float:
    union = (a | b).bit_count()
    if union <= 0:
        return 0.0
    return (a & b).bit_count() / union


def _pick_anchor_title_logo(frames: list[dict], chapter_start: int = 0) -> tuple[dict | None, dict]:
    candidates = []
    for run in _title_logo_runs(frames):
        start = int(run[0]["time"])
        offset = start - int(chapter_start)
        if offset < TITLE_LOGO_ANCHOR_FROM_SECONDS or offset > TITLE_LOGO_ANCHOR_TO_SECONDS:
            continue
        best = max(
            run,
            key=lambda x: (
                float(x.get("width_ratio") or 0),
                float(x.get("yellow_fill") or 0),
            ),
        )
        score = (
            abs(offset - TITLE_LOGO_EXPECTED_OFFSET_SECONDS),
            -len(run),
            -float(best.get("width_ratio") or 0),
            -float(best.get("yellow_fill") or 0),
        )
        candidates.append((score, start, offset, best, run))

    if not candidates:
        return None, {"reason": "no_title_logo_in_vod_opening"}

    candidates.sort(key=lambda x: x[0])
    _, start, offset, best, run = candidates[0]
    ref = dict(best)
    ref["run_start"] = start
    return ref, {
        "reason": "ok",
        "title_time": start,
        "offset_seconds": offset,
        "run_frames": len(run),
        "width_ratio": best.get("width_ratio"),
        "height_ratio": best.get("height_ratio"),
        "aspect": best.get("aspect"),
        "center_x": best.get("center_x"),
        "center_y": best.get("center_y"),
        "yellow_fill": best.get("yellow_fill"),
        "source": "episode-opening-title-logo",
    }

def _match_title_logo(reference: dict, frames: list[dict], expected_time: int) -> tuple[int | None, dict]:
    candidates = []
    ref_w = float(reference.get("width_ratio") or 0)
    ref_h = float(reference.get("height_ratio") or 0)
    ref_a = float(reference.get("aspect") or 0)
    ref_x = float(reference.get("center_x") or 0.5)
    ref_y = float(reference.get("center_y") or 0.5)
    ref_fill = float(reference.get("yellow_fill") or 0)

    for run in _title_logo_runs(frames):
        start = int(run[0]["time"])
        best = max(
            run,
            key=lambda x: (
                float(x.get("width_ratio") or 0),
                float(x.get("yellow_fill") or 0),
            ),
        )

        w = float(best.get("width_ratio") or 0)
        h = float(best.get("height_ratio") or 0)
        a = float(best.get("aspect") or 0)
        cx = float(best.get("center_x") or 0.5)
        cy = float(best.get("center_y") or 0.5)
        fill = float(best.get("yellow_fill") or 0)

        feature_distance = (
            abs(w - ref_w) / 0.30
            + abs(h - ref_h) / 0.22
            + abs(a - ref_a) / 3.0
            + abs(cx - ref_x) / 0.22
            + abs(cy - ref_y) / 0.20
            + abs(fill - ref_fill) / 0.35
        ) / 6.0

        if feature_distance > TITLE_LOGO_FEATURE_DISTANCE_MAX:
            continue

        time_distance = abs(start - int(expected_time))
        if time_distance > TITLE_LOGO_MAX_EXPECTED_DISTANCE_SECONDS:
            continue

        score = (
            time_distance,
            round(feature_distance, 4),
            -len(run),
            -w,
        )
        candidates.append((score, start, best, len(run), feature_distance))

    if not candidates:
        return None, {"reason": "no_matching_vod_title_logo"}

    candidates.sort(key=lambda x: x[0])
    _, start, best, run_frames, feature_distance = candidates[0]
    return start, {
        "reason": "ok",
        "run_frames": run_frames,
        "expected_title_time": int(expected_time),
        "distance_from_expected": start - int(expected_time),
        "feature_distance": round(float(feature_distance), 4),
        "bbox_width": best.get("bbox_width"),
        "bbox_height": best.get("bbox_height"),
        "width_ratio": best.get("width_ratio"),
        "height_ratio": best.get("height_ratio"),
        "aspect": best.get("aspect"),
        "center_x": best.get("center_x"),
        "center_y": best.get("center_y"),
        "yellow_fill": best.get("yellow_fill"),
    }
def _hdist(a: int, b: int) -> int:
    return (a ^ b).bit_count()


def _sequence_windows(frames: list[dict], count: int = TITLECARD_SEQUENCE_FRAMES) -> list[dict]:
    out = []
    for i in range(max(0, len(frames) - count + 1)):
        seq = frames[i:i + count]
        if len(seq) != count:
            continue
        if any(
            int(y["time"]) - int(x["time"]) <= 0
            or int(y["time"]) - int(x["time"]) > TITLECARD_STATIC_MAX_FRAME_GAP
            for x, y in zip(seq, seq[1:])
        ):
            continue
        out.append({
            "time": int(seq[0]["time"]),
            "hashes": [int(x["hash"]) for x in seq],
        })
    return out


def _sequence_distance(a: list[int], b: list[int]) -> float:
    if len(a) != len(b) or not a:
        return 999.0
    return statistics.mean(_hdist(x, y) for x, y in zip(a, b))


def _learn_titlecard_reference(windows: list[list[dict]]) -> tuple[dict | None, dict]:
    usable = [w for w in windows if w]
    if len(usable) < 3:
        return None, {"reason": "too_few_windows", "usable_windows": len(usable)}

    first_start = min(int(x["time"]) for x in usable[0])
    anchor = [
        x for x in usable[0]
        if int(x["time"]) <= first_start + TITLECARD_REFERENCE_MAX_SECONDS
    ]
    anchor_sequences = _sequence_windows(anchor)
    if not anchor_sequences:
        return None, {"reason": "no_opening_sequence", "usable_windows": len(usable)}

    others = [_sequence_windows(w) for w in usable[1:]]
    best = None
    for ref in anchor_sequences:
        distances = []
        matches = 0
        for seqs in others:
            d = min(
                (_sequence_distance(ref["hashes"], x["hashes"]) for x in seqs),
                default=999.0,
            )
            distances.append(d)
            if d <= TITLECARD_SEQUENCE_MATCH_DISTANCE:
                matches += 1
        required = max(2, int(round((len(usable) - 1) * 0.45)))
        if matches < required:
            continue
        score = statistics.median(distances)
        candidate = (score, -matches, ref["time"], ref)
        if best is None or candidate[:3] < best[:3]:
            best = candidate

    if best is None:
        return None, {"reason": "no_recurring_opening_sequence", "usable_windows": len(usable)}
    return best[3], {
        "reason": "ok",
        "usable_windows": len(usable),
        "reference_time_seconds": int(best[3]["time"]) - first_start,
        "median_distance": round(float(best[0]), 3),
        "matching_windows": -best[1],
    }


def _best_titlecard_match(reference: dict, frames: list[dict]) -> tuple[int | None, float | None]:
    seqs = _sequence_windows(frames)
    if not seqs:
        return None, None
    scored = [
        (_sequence_distance(reference["hashes"], x["hashes"]), int(x["time"]))
        for x in seqs
    ]
    best_dist = min(x[0] for x in scored)
    if best_dist > TITLECARD_SEQUENCE_MATCH_DISTANCE:
        return None, best_dist
    near = [t for d, t in scored if d <= min(TITLECARD_SEQUENCE_MATCH_DISTANCE, best_dist + 3)]
    return min(near), best_dist


def _best_static_title_start(
    frames: list[dict],
    original: int,
    max_shift_seconds: int,
) -> tuple[int | None, dict]:
    if len(frames) < 3:
        return None, {"reason": "too_few_frames"}
    candidates = []
    for i in range(len(frames) - 2):
        cur, nxt, nxt2 = frames[i], frames[i + 1], frames[i + 2]
        gap1 = int(nxt["time"]) - int(cur["time"])
        gap2 = int(nxt2["time"]) - int(nxt["time"])
        if (
            gap1 <= 0 or gap1 > TITLECARD_STATIC_MAX_FRAME_GAP
            or gap2 <= 0 or gap2 > TITLECARD_STATIC_MAX_FRAME_GAP
        ):
            continue
        stable1 = _hdist(cur["hash"], nxt["hash"])
        stable2 = _hdist(nxt["hash"], nxt2["hash"])
        if stable1 > TITLECARD_STATIC_DISTANCE or stable2 > TITLECARD_STATIC_DISTANCE:
            continue

        prev_dist = 256
        if i > 0:
            prev = frames[i - 1]
            if int(cur["time"]) - int(prev["time"]) <= TITLECARD_STATIC_MAX_FRAME_GAP:
                prev_dist = _hdist(prev["hash"], cur["hash"])
        if i > 0 and prev_dist < TITLECARD_STATIC_TRANSITION_DISTANCE:
            continue

        shift = abs(int(cur["time"]) - int(original))
        if shift > max_shift_seconds:
            continue

        # Prefer the nearest high-contrast transition into a card that stays
        # visually stable for at least two sampling intervals.
        stability = stable1 + stable2
        candidates.append(
            ((shift, stability, -int(cur.get("contrast") or 0), int(cur["time"])),
             int(cur["time"]), stable1, stable2, prev_dist)
        )

    if not candidates:
        return None, {"reason": "no_guarded_static_card_transition"}
    candidates.sort(key=lambda x: x[0])
    _, start, stable1, stable2, transition = candidates[0]
    return start, {
        "reason": "ok",
        "stable_distance_1": stable1,
        "stable_distance_2": stable2,
        "transition_distance": transition,
        "distance_from_guess": abs(start - int(original)),
    }


def _apply_refined_chapter_starts(chapters: list[dict], starts: dict[int, int], duration: int) -> list[dict]:
    if not starts:
        return chapters
    out = [dict(x) for x in chapters]

    # VOD start remains zero; every later chapter can move to its detected title card.
    for index, item in enumerate(out):
        if index == 0:
            item["start_seconds"] = 0
            continue
        if index in starts:
            item["start_seconds"] = max(1, min(duration - 1, int(starts[index])))
            item["method"] = "titlecard-detected"
            item["confidence"] = "high"

    # A bad visual hit must never reverse chapter order or create tiny fragments.
    for i in range(1, len(out)):
        current = int(out[i]["start_seconds"])
        previous = int(out[i - 1]["start_seconds"])
        if current <= previous or current - previous < 120:
            return chapters

    vod_id = str(out[0].get("vod_id") or "") if out else ""
    for i, item in enumerate(out):
        start = int(item["start_seconds"])
        stop = duration if i == len(out) - 1 else int(out[i + 1]["start_seconds"])
        if stop <= start:
            return chapters
        item["stop_seconds"] = stop
        item["duration_seconds"] = stop - start
        item["replay_url"] = clip_url(vod_id, start, stop - start)
    return out


def _scan_title_logo_timeline(url: str, total_duration: int, chunk_seconds: int = 1800) -> list[dict]:
    """Scan the whole VOD for title-logo occurrences without trusting chapter starts."""
    width, height = 64, 36

    def scan_chunk(start: int) -> list[dict]:
        span = min(chunk_seconds, total_duration - start)
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-rw_timeout", "15000000", "-ss", str(start), "-i", url,
            "-t", str(span), "-an",
            "-vf", f"fps=1/{TITLE_LOGO_SAMPLE_SECONDS},scale={width}:{height}:flags=area,format=rgb24",
            "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1",
        ]
        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, check=False)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []
        if proc.returncode != 0:
            return []
        frame_size = width * height * 3
        rows = []
        for idx in range(len(proc.stdout) // frame_size):
            frame = proc.stdout[idx * frame_size:(idx + 1) * frame_size]
            logo = _normalise_yellow_logo(frame, width, height)
            if logo:
                rows.append({"time": start + idx * TITLE_LOGO_SAMPLE_SECONDS, **logo})
        return rows

    starts = list(range(0, total_duration, chunk_seconds))
    found = []
    # Four parallel HLS decoders cut wall time sharply while keeping memory modest.
    with ThreadPoolExecutor(max_workers=min(4, max(1, len(starts)))) as pool:
        futures = [pool.submit(scan_chunk, start) for start in starts]
        for future in as_completed(futures):
            try:
                found.extend(future.result())
            except Exception:
                continue
    found.sort(key=lambda x: int(x["time"]))
    return found


def _global_regular_logo_starts(frames: list[dict], count: int) -> list[int]:
    """Pick a chronological sequence of roughly hour-spaced recurring openings."""
    runs = _title_logo_runs(frames)
    candidates = [int(run[0]["time"]) for run in runs]
    if not candidates or count <= 0:
        return []
    # Dynamic programming: reward a full chronological sequence with regular
    # episode gaps, but do not require any pre-existing chapter boundary.
    states = {(i, 1): (0, [candidates[i]]) for i in range(len(candidates))}
    for length in range(2, count + 1):
        next_states = {}
        for j, t in enumerate(candidates):
            best = None
            for i in range(j):
                prev = states.get((i, length - 1))
                if not prev:
                    continue
                gap = t - candidates[i]
                if gap < 2400 or gap > 4800:
                    continue
                penalty = prev[0] + abs(gap - REFERENCE_EPISODE_SECONDS)
                if best is None or penalty < best[0]:
                    best = (penalty, prev[1] + [t])
            if best:
                next_states[(j, length)] = best
        states.update(next_states)
    finals = [v for (i, n), v in states.items() if n == count]
    if not finals:
        return []
    return min(finals, key=lambda x: x[0])[1]

def _sample_opening_hash_window(url: str, center: int, total_duration: int, before: int = 12, after: int = 22) -> list[dict]:
    """Sample grayscale hashes around an episode opening for sequence matching."""
    start = max(0, int(center) - int(before))
    stop = min(int(total_duration), int(center) + int(after) + 1)
    span = max(1, stop - start)
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-rw_timeout", "15000000",
        "-ss", str(start),
        "-i", url,
        "-t", str(span),
        "-an",
        "-vf", "fps=1,scale=17:16:flags=area,format=gray",
        "-pix_fmt", "gray",
        "-f", "rawvideo", "pipe:1",
    ]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=45, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    size = 17 * 16
    out = []
    raw = proc.stdout
    for idx in range(len(raw) // size):
        sig = _frame_signature(raw[idx * size:(idx + 1) * size])
        if not sig:
            continue
        bits, mean, contrast = sig
        out.append({"time": start + idx, "hash": bits, "mean": mean, "contrast": contrast})
    return out


def _probe_recurring_opening_sequence(url: str, chapters: list[dict], total_duration: int, reference_episode: int = 186, sequence_seconds: int = 10) -> dict:
    """Match a 10-second opening sequence, allowing a small timing shift per episode."""
    episodes = [x for x in chapters if x.get("kind") == "episode" and 177 <= int(x.get("episode") or 0) <= 196]
    ref_item = next((x for x in episodes if int(x.get("episode") or 0) == reference_episode), None)
    if not ref_item:
        return {"status": "skipped", "reason": "reference_episode_missing"}
    windows = {}
    for item in episodes:
        ep = int(item.get("episode") or 0)
        windows[ep] = _sample_opening_hash_window(url, int(item.get("start_seconds") or 0), total_duration)
    ref_center = int(ref_item.get("start_seconds") or 0)
    ref_map = {int(x["time"]): x for x in (windows.get(reference_episode) or [])}
    ref_seq = [ref_map.get(ref_center + i) for i in range(sequence_seconds)]
    if any(x is None for x in ref_seq):
        return {"status": "skipped", "reason": "reference_sequence_incomplete"}
    ref_seq = [x for x in ref_seq if x is not None]
    rows = []
    strong = 0
    for item in episodes:
        ep = int(item.get("episode") or 0)
        center = int(item.get("start_seconds") or 0)
        cmap = {int(x["time"]): x for x in (windows.get(ep) or [])}
        scored = []
        for shift in range(-12, 13):
            cand = [cmap.get(center + shift + i) for i in range(sequence_seconds)]
            if any(x is None for x in cand):
                continue
            cand = [x for x in cand if x is not None]
            hammings = [(int(r["hash"]) ^ int(c["hash"])).bit_count() for r, c in zip(ref_seq, cand)]
            mean_deltas = [abs(float(r["mean"]) - float(c["mean"])) for r, c in zip(ref_seq, cand)]
            transition_deltas = []
            for i in range(1, sequence_seconds):
                rt = (int(ref_seq[i-1]["hash"]) ^ int(ref_seq[i]["hash"])).bit_count()
                ct = (int(cand[i-1]["hash"]) ^ int(cand[i]["hash"])).bit_count()
                transition_deltas.append(abs(rt - ct))
            avg_hamming = sum(hammings) / len(hammings)
            avg_mean = sum(mean_deltas) / len(mean_deltas)
            avg_transition = sum(transition_deltas) / max(1, len(transition_deltas))
            score = avg_hamming + avg_mean / 3.0 + avg_transition / 2.0
            scored.append((score, shift, avg_hamming, avg_mean, avg_transition, max(hammings)))
        if not scored:
            rows.append({"episode": ep, "matched": False, "reason": "sequence_window_incomplete"})
            continue
        scored.sort(key=lambda x: x[0])
        score, shift, avg_hamming, avg_mean, avg_transition, max_hamming = scored[0]
        matched = avg_hamming <= 52 and avg_transition <= 22
        if matched:
            strong += 1
        rows.append({
            "episode": ep,
            "matched": matched,
            "center": center,
            "best_shift_seconds": int(shift),
            "candidate_start": center + int(shift),
            "avg_hamming": round(avg_hamming, 2),
            "max_hamming": int(max_hamming),
            "avg_mean_delta": round(avg_mean, 2),
            "avg_transition_delta": round(avg_transition, 2),
            "score": round(score, 2),
        })
    return {
        "status": "diagnostic",
        "method": "10s-opening-sequence",
        "reference_episode": reference_episode,
        "reference_start": ref_center,
        "sequence_seconds": sequence_seconds,
        "matched": strong,
        "episode_count": len(episodes),
        "coverage": round(strong / max(1, len(episodes)), 3),
        "rows": rows,
    }


def _sample_hash_range(url: str, start: int, span: int, total_duration: int = 0) -> list[dict]:
    """Sample 1 fps grayscale perceptual hashes from an exact interval."""
    start = max(0, int(start))
    span = max(1, int(span))
    if total_duration > 0:
        span = min(span, max(1, int(total_duration) - start))
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-rw_timeout", "15000000",
        "-ss", str(start),
        "-i", url,
        "-t", str(span),
        "-an",
        "-vf", "fps=1,scale=17:16:flags=area,format=gray",
        "-pix_fmt", "gray",
        "-f", "rawvideo", "pipe:1",
    ]
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=55, check=False)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    size = 17 * 16
    out = []
    raw = proc.stdout
    for idx in range(len(raw) // size):
        sig = _frame_signature(raw[idx * size:(idx + 1) * size])
        if not sig:
            continue
        bits, mean, contrast = sig
        out.append({"time": start + idx, "hash": bits, "mean": mean, "contrast": contrast})
    return out


def _probe_known_35s_op(url: str, chapters: list[dict], total_duration: int) -> dict:
    """Use the user-confirmed first 35 seconds of #227 as a full OP template."""
    template_frames = _sample_hash_range(KNOWN_OP_TEMPLATE_URL, 0, KNOWN_OP_TEMPLATE_SECONDS)
    if len(template_frames) < KNOWN_OP_TEMPLATE_SECONDS - 2:
        return {"status": "skipped", "reason": "template_incomplete", "frames": len(template_frames)}
    template_frames = template_frames[:KNOWN_OP_TEMPLATE_SECONDS]
    rows = []
    episodes = [x for x in chapters if x.get("kind") == "episode"][:3]
    for item in episodes:
        ep = int(item.get("episode") or 0)
        center = int(item.get("start_seconds") or 0)
        search_before = 20
        search_after = 20
        sample_start = max(0, center - search_before)
        sample_stop = min(int(total_duration), center + search_after + KNOWN_OP_TEMPLATE_SECONDS)
        frames = _sample_hash_range(url, sample_start, max(1, sample_stop - sample_start), total_duration)
        fmap = {int(x["time"]): x for x in frames}
        scored = []
        for shift in range(-search_before, search_after + 1):
            cand_start = center + shift
            if cand_start < 0:
                continue
            cand = [fmap.get(cand_start + i) for i in range(KNOWN_OP_TEMPLATE_SECONDS)]
            if any(x is None for x in cand):
                continue
            cand = [x for x in cand if x is not None]
            hammings = [(int(r["hash"]) ^ int(c["hash"])).bit_count() for r, c in zip(template_frames, cand)]
            means = [abs(float(r["mean"]) - float(c["mean"])) for r, c in zip(template_frames, cand)]
            # Ignore the worst ~30% of frames so episode-specific title overlays do not dominate.
            core_n = max(1, int(len(hammings) * 0.70))
            core_hamming = sum(sorted(hammings)[:core_n]) / core_n
            avg_hamming = sum(hammings) / len(hammings)
            avg_mean = sum(means) / len(means)
            score = core_hamming + avg_mean / 4.0
            scored.append((score, shift, core_hamming, avg_hamming, avg_mean, max(hammings)))
        if not scored:
            rows.append({"episode": ep, "matched": False, "reason": "search_window_incomplete"})
            continue
        scored.sort(key=lambda x: x[0])
        score, shift, core_hamming, avg_hamming, avg_mean, max_hamming = scored[0]
        rows.append({
            "episode": ep,
            "chapter_start": center,
            "best_op_start": center + int(shift),
            "shift_seconds": int(shift),
            "score": round(score, 2),
            "core_hamming": round(core_hamming, 2),
            "avg_hamming": round(avg_hamming, 2),
            "avg_mean_delta": round(avg_mean, 2),
            "max_hamming": int(max_hamming),
        })
    return {
        "status": "diagnostic",
        "method": "user-confirmed-35s-op-template",
        "template_seconds": KNOWN_OP_TEMPLATE_SECONDS,
        "template_url": KNOWN_OP_TEMPLATE_URL,
        "rows": rows,
    }


def _probe_global_op_logo_starts(url: str, total_duration: int, episode_count: int, chapters: list[dict] | None = None) -> dict:
    """Find OP logos in wide +/-10 minute windows around rough chapter estimates."""
    template_logo_frames = _scan_title_logo_timeline(KNOWN_OP_TEMPLATE_URL, KNOWN_OP_TEMPLATE_SECONDS, KNOWN_OP_TEMPLATE_SECONDS)
    reference, ref_meta = _pick_anchor_title_logo(template_logo_frames, 0)
    if reference is None:
        return {"status": "skipped", "reason": "template_logo_not_found", "reference": ref_meta}
    logo_offset = int(reference.get("run_start") or 0)
    ref_w = float(reference.get("width_ratio") or 0)
    ref_h = float(reference.get("height_ratio") or 0)
    ref_a = float(reference.get("aspect") or 0)
    ref_x = float(reference.get("center_x") or 0.5)
    ref_y = float(reference.get("center_y") or 0.5)
    ref_fill = float(reference.get("yellow_fill") or 0)
    test_count = min(3, int(episode_count))
    episodes = [x for x in (chapters or []) if x.get("kind") == "episode"][:test_count]
    if len(episodes) != test_count:
        return {"status": "skipped", "reason": "episode_estimates_missing", "template_logo_offset": logo_offset}

    def sample_wide(item: dict) -> dict:
        ep = int(item.get("episode") or 0)
        rough_center = int(item.get("start_seconds") or 0)
        center = rough_center + max(0, ep - 227) * 262
        radius = 240
        start = max(0, center - radius)
        stop = min(int(total_duration), center + radius)
        if center <= radius:
            start = 0
            stop = min(int(total_duration), 90)
        width, height = 64, 36
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error",
            "-rw_timeout", "15000000", "-ss", str(start), "-i", url,
            "-t", str(span), "-an",
            "-vf", f"fps=1/{TITLE_LOGO_SAMPLE_SECONDS},scale={width}:{height}:flags=area,format=rgb24",
            "-pix_fmt", "rgb24", "-f", "rawvideo", "pipe:1",
        ]
        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=220, check=False)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            return {"episode": ep, "chapter_start": rough_center, "search_center": center, "matched": False, "reason": str(exc)}
        if proc.returncode != 0:
            return {"episode": ep, "chapter_start": rough_center, "search_center": center, "matched": False, "reason": "ffmpeg_failed"}
        frame_size = width * height * 3
        frames = []
        for idx in range(len(proc.stdout) // frame_size):
            frame = proc.stdout[idx * frame_size:(idx + 1) * frame_size]
            logo = _normalise_yellow_logo(frame, width, height)
            if logo:
                frames.append({"time": start + idx * TITLE_LOGO_SAMPLE_SECONDS, **logo})
        candidates = []
        expected_logo = center + logo_offset
        for run in _title_logo_runs(frames):
            run_start = int(run[0]["time"])
            best = max(run, key=lambda x: (float(x.get("width_ratio") or 0), float(x.get("yellow_fill") or 0)))
            w = float(best.get("width_ratio") or 0)
            h = float(best.get("height_ratio") or 0)
            aa = float(best.get("aspect") or 0)
            cx = float(best.get("center_x") or 0.5)
            cy = float(best.get("center_y") or 0.5)
            fill = float(best.get("yellow_fill") or 0)
            fd = (
                abs(w - ref_w) / 0.30 + abs(h - ref_h) / 0.22 + abs(aa - ref_a) / 3.0
                + abs(cx - ref_x) / 0.22 + abs(cy - ref_y) / 0.20 + abs(fill - ref_fill) / 0.35
            ) / 6.0
            if fd > 0.40:
                continue
            candidates.append((round(fd, 4), abs(run_start - expected_logo), -len(run), run_start, len(run)))
        if not candidates:
            return {
                "episode": ep, "chapter_start": rough_center, "search_center": center, "matched": False,
                "reason": "no_logo_in_wide_window", "detected_logo_frames": len(frames),
                "window_start": start, "window_stop": stop,
            }
        candidates.sort()
        fd, distance, neg_len, logo_time, run_frames = candidates[0]
        op_start = max(0, int(logo_time) - logo_offset)
        return {
            "episode": ep, "chapter_start": rough_center, "search_center": center, "matched": True,
            "window_start": start, "window_stop": stop,
            "logo_time": int(logo_time), "op_start": op_start,
            "shift_seconds": op_start - rough_center,
            "feature_distance": fd, "run_frames": int(run_frames),
            "distance_from_estimated_logo": int(distance),
            "detected_logo_frames": len(frames),
        }

    rows = []
    with ThreadPoolExecutor(max_workers=min(4, len(episodes))) as pool:
        futures = [pool.submit(sample_wide, item) for item in episodes]
        for future in as_completed(futures):
            rows.append(future.result())
    rows.sort(key=lambda x: int(x.get("episode") or 0))
    matched_rows = [x for x in rows if x.get("matched")]
    return {
        "status": "diagnostic" if len(matched_rows) >= max(1, test_count - 1) else "partial",
        "method": "wide-local-op-logo-scan",
        "template_logo_offset": logo_offset,
        "matched": len(matched_rows),
        "episode_count": test_count,
        "rows": rows,
    }


def refine_with_titlecard(
    vod: dict,
    chapters: list[dict],
    previous_result: dict | None = None,
) -> tuple[list[dict], dict]:
    """Align regular episode clips to the recurring blue-room opening frame.

    VOD5 thumbnails are taken from the beginning of each clip, so a successful
    refinement must make regular episodes begin on the same blue-room cue,
    rather than merely finding the later yellow title logo.
    """
    duration = int(vod.get("duration_seconds") or 0)
    vod_id = str(vod.get("vod_id") or "")
    source_url = str(vod.get("source_url") or "")
    if not vod.get("playable") and vod_id:
        source_url = f"{REPLAY_BASE}{urllib.parse.quote(vod_id)}"
    items = list(chapters[:TITLECARD_MAX_ANALYZE_EPISODES])
    if duration <= 0 or not source_url or len(items) < 2:
        return chapters, {"status": "skipped", "reason": "insufficient_source_or_chapters"}

    if previous_result and int(previous_result.get("duration_seconds") or 0) == duration:
        prev = previous_result.get("titlecard_refinement") or {}
        cached = prev.get("chapter_starts") or {}
        if (
            prev.get("status") in {"applied", "partial"}
            and int(prev.get("boundary_version") or 0) == TITLECARD_BOUNDARY_VERSION
            and cached
        ):
            starts = {int(k): int(v) for k, v in cached.items()}
            rebuilt = _apply_refined_chapter_starts(
                [{**x, "vod_id": vod_id} for x in chapters], starts, duration
            )
            for x in rebuilt:
                x.pop("vod_id", None)
            meta = dict(prev)
            meta["cache_reused"] = True
            return rebuilt, meta

    if os.environ.get("GMCX_TITLECARD_REFINE", "1") == "0":
        return chapters, {"status": "skipped", "reason": "disabled"}

    analysis_url = _lowest_hls_variant(source_url)
    regular_indices = [
        i for i, item in enumerate(items)
        if item.get("kind") == "episode"
        and int(item.get("episode") or 0) not in EPISODE_DURATION_OVERRIDES
    ]
    if len(regular_indices) < 3:
        return chapters, {"status": "skipped", "reason": "too_few_regular_episodes"}

    # Detect the recurring large yellow GMCX title logo.  This is a much
    # stronger cue than merely looking for a blue-ish studio frame.  Once the
    # logo time is known, move the clip start back by the opening offset learned
    # from the first regular episode.
    logo_windows: dict[int, list[dict]] = {}
    for index in regular_indices:
        original = int(items[index].get("start_seconds") or 0)
        logo_windows[index] = _sample_title_logo_window(analysis_url, original, duration)

    # The first episode can have a shorter/different intro (e.g. #177 has the
    # large GMCX logo around 10s).  Try every regular episode and use the
    # strongest detected logo as the reference instead of requiring episode 1.
    anchor_candidates = []
    for candidate_index in regular_indices:
        candidate_original = int(items[candidate_index].get("start_seconds") or 0)
        candidate_ref, candidate_meta = _pick_anchor_title_logo(
            logo_windows.get(candidate_index, []), candidate_original
        )
        if candidate_ref is None:
            continue
        candidate_time = int(candidate_ref.get("run_start") or 0)
        candidate_offset = candidate_time - candidate_original
        # Prefer a stable, large logo and a plausible opening offset (5-60s).
        if not (5 <= candidate_offset <= 60):
            continue
        score = (
            -int(candidate_meta.get("run_frames") or 0),
            -float(candidate_meta.get("width_ratio") or 0),
            abs(candidate_offset - 20),
        )
        anchor_candidates.append(
            (score, candidate_index, candidate_ref, candidate_meta, candidate_offset)
        )
    if not anchor_candidates:
        return chapters, {
            "status": "no_consensus", "method": "recurring-title-logo",
            "boundary_version": TITLECARD_BOUNDARY_VERSION,
            "reference": {"reason": "no_title_logo_anchor_in_any_episode"},
            "matches": [],
        }
    anchor_candidates.sort(key=lambda x: x[0])
    _, anchor_index, reference, ref_meta, opening_offset = anchor_candidates[0]
    ref_meta = dict(ref_meta)
    ref_meta["anchor_episode"] = int(items[anchor_index].get("episode") or 0)
    ref_meta["opening_offset_seconds"] = opening_offset
    starts: dict[int, int] = {}
    match_rows = []
    matched_regular = 0
    for index, item in enumerate(items):
        original = int(item.get("start_seconds") or 0)
        if index not in regular_indices:
            starts[index] = original
            continue
        expected_logo = original + opening_offset
        hit, detail = _match_title_logo(reference, logo_windows.get(index, []), expected_logo)
        if hit is None:
            match_rows.append({
                "index": index, "title": item.get("title"), "matched": False,
                "original": original, "reason": detail.get("reason"), "detail": detail,
            })
            continue
        refined = int(hit) - opening_offset
        if abs(refined - original) > TITLECARD_REGULAR_MAX_SHIFT_SECONDS:
            match_rows.append({
                "index": index, "title": item.get("title"), "matched": False,
                "original": original, "candidate": refined, "reason": "shift_guard",
                "detail": detail,
            })
            continue
        starts[index] = refined
        matched_regular += 1
        match_rows.append({
            "index": index, "title": item.get("title"), "matched": True,
            "method": "recurring-title-logo", "original": original,
            "logo_time": int(hit), "refined": refined,
            "shift_seconds": refined - original, "detail": detail,
        })

    coverage = matched_regular / max(1, len(regular_indices))
    if coverage < 0.8:
        return chapters, {
            "status": "no_consensus", "method": "recurring-title-logo",
            "boundary_version": TITLECARD_BOUNDARY_VERSION,
            "reason": "title_logo_coverage_below_80_percent",
            "reference": ref_meta, "opening_offset_seconds": opening_offset,
            "detected_regular_boundaries": matched_regular,
            "expected_regular_boundaries": len(regular_indices),
            "coverage": round(coverage, 3), "matches": match_rows,
        }

    rebuilt = _apply_refined_chapter_starts(
        [{**x, "vod_id": vod_id} for x in chapters], starts, duration
    )
    for x in rebuilt:
        x.pop("vod_id", None)
    return rebuilt, {
        "status": "applied" if coverage >= 0.95 else "partial",
        "method": "recurring-title-logo",
        "boundary_version": TITLECARD_BOUNDARY_VERSION,
        "reference": ref_meta, "opening_offset_seconds": opening_offset,
        "detected_regular_boundaries": matched_regular,
        "expected_regular_boundaries": len(regular_indices),
        "coverage": round(coverage, 3),
        "chapter_starts": {str(k): v for k, v in starts.items()},
        "matches": match_rows, "cache_reused": False,
    }

def clip_url(vod_id: str, start: int, duration: int) -> str:
    return f"{REPLAY_BASE}{urllib.parse.quote(vod_id)}&start={start}&duration={duration}"


def make_uniform_chapters(vod: dict, start_ep: int, end_ep: int, titles: dict[str, str]) -> list[dict]:
    count = end_ep - start_ep + 1
    duration = int(vod.get("duration_seconds") or 0)
    if count <= 0 or duration <= 0:
        return []
    unit = duration / count
    expected_unit = RANGE_EPISODE_SECONDS.get((start_ep, end_ep), REFERENCE_EPISODE_SECONDS)
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
            "confidence": "high" if abs(unit - expected_unit) <= 120 else "medium",
        })
    return chapters


def make_exact_197_206_chapters(vod: dict, titles: dict[str, str]) -> list[dict]:
    duration = int(vod.get("duration_seconds") or 0)
    vod_id = str(vod.get("vod_id") or "")
    if duration < 48610 or not vod_id:
        return []

    # Source player file list from the actual archive:
    # 29 s pre-roll, then exact file runtimes in playback order.
    layout = [
        ("episode", 197, None, 3480, None),
        ("episode", 198, None, 3480, None),
        ("episode", 199, None, 3450, None),
        ("special", None, "2015-niconico-chokaigi", 2525, "GMCX in ニコニコ超会議2015"),
        ("episode", 200, None, 3450, None),
        ("episode", 201, None, 3480, None),
        ("episode", 202, None, 3450, None),
        ("episode", 203, None, 3480, None),
        ("special", None, "2015-vietnam", 7170, "GMCX in VIETNAM ～ベトナムのゲーム事情 徹底調査&カジノにもリベンジしちゃうよ!SP～"),
        ("episode", 204, None, 3450, None),
        ("episode", 205, None, 3480, None),
        ("special", None, "2015-mario-maker-course-build", 1771, "GMCX 「スーパーマリオメーカー」コース制作編"),
        ("special", None, "2015-mario-maker-character", 206, "GMCX 「スーパーマリオメーカー」キャラマリオ編"),
        ("special", None, "2015-mario-maker-play", 2229, "GMCX 「スーパーマリオメーカー」を遊ぶ編"),
        ("episode", 206, None, 3480, None),
    ]

    chapters = []
    cursor = 29
    for kind, ep, key, length, special_title in layout:
        stop = cursor + int(length)
        if stop > duration:
            return []
        if kind == "episode":
            title = titles.get(str(ep), f"第{ep}回")
            chapters.append({
                "kind": "episode",
                "episode": ep,
                "title": title,
                "start_seconds": cursor,
                "stop_seconds": stop,
                "duration_seconds": int(length),
                "replay_url": clip_url(vod_id, cursor, int(length)),
                "method": "source-filelist-exact",
                "confidence": "high",
            })
        else:
            chapters.append({
                "kind": "special",
                "special_key": key,
                "title": special_title,
                "start_seconds": cursor,
                "stop_seconds": stop,
                "duration_seconds": int(length),
                "expected_broadcast_seconds": int(length),
                "replay_url": clip_url(vod_id, cursor, int(length)),
                "method": "source-filelist-exact",
                "confidence": "high",
            })
        cursor = stop

    if cursor != duration:
        return []
    return chapters


def make_mixed_chapters(vod: dict, start_ep: int, end_ep: int, titles: dict[str, str]) -> list[dict]:
    count = end_ep - start_ep + 1
    duration = int(vod.get("duration_seconds") or 0)
    if (start_ep, end_ep) == (197, 206):
        return make_exact_197_206_chapters(vod, titles)
    episode_seconds = RANGE_EPISODE_SECONDS.get((start_ep, end_ep), REFERENCE_EPISODE_SECONDS)
    specs = [dict(x) for x in KNOWN_SPECIALS.get((start_ep, end_ep), [])]

    regular_duration_map: dict[int, int] = {}
    if (start_ep, end_ep) == (217, 226):
        # 2016 chronology: five Pokemon specials have known year-end replay
        # blocks of 33/37/37/35/43 minutes. #226 is a 120-minute special.
        # Distribute the exact remaining archive time across #217-225.
        fixed_special_total = sum(int(x.get("duration_seconds") or 0) for x in specs)
        override_total = sum(
            int(EPISODE_DURATION_OVERRIDES.get(ep) or 0)
            for ep in range(start_ep, end_ep + 1)
            if ep in EPISODE_DURATION_OVERRIDES
        )
        regular_eps = [
            ep for ep in range(start_ep, end_ep + 1)
            if ep not in EPISODE_DURATION_OVERRIDES
        ]
        pool = duration - fixed_special_total - override_total
        if pool <= 0 or not regular_eps:
            return []
        base, remainder = divmod(pool, len(regular_eps))
        if base <= 0:
            return []
        regular_duration_map = {
            ep: base + (1 if idx < remainder else 0)
            for idx, ep in enumerate(regular_eps)
        }
        regular_total = override_total + sum(regular_duration_map.values())
    else:
        regular_total = sum(
            EPISODE_DURATION_OVERRIDES.get(ep, episode_seconds)
            for ep in range(start_ep, end_ep + 1)
        )

    if duration < regular_total:
        return []

    extra_total = duration - regular_total
    fixed_extra = sum(int(x.get("duration_seconds") or 0) for x in specs)
    flexible = [
        x for x in specs
        if x.get("duration_seconds") is None and not x.get("duration_group")
    ]
    grouped: dict[str, list[dict]] = {}
    for spec in specs:
        group = spec.get("duration_group")
        if group:
            grouped.setdefault(str(group), []).append(spec)

    if fixed_extra > extra_total:
        return []
    remaining = extra_total - fixed_extra

    # A single explicitly flexible mini-special may consume the small remainder.
    if len(flexible) > 1:
        return []
    if flexible:
        flexible[0]["duration_seconds"] = remaining
        remaining = 0

    # Same-format short specials (e.g. Pokémon #1-#5) share the remaining
    # footage evenly. This is safer than inventing different runtimes.
    if grouped:
        if len(grouped) > 1 or flexible:
            return []
        members = next(iter(grouped.values()))
        if not members:
            return []
        base, remainder = divmod(remaining, len(members))
        if base <= 0:
            return []
        for idx, spec in enumerate(members):
            spec["duration_seconds"] = base + (1 if idx < remainder else 0)
        remaining = 0

    if remaining != 0:
        return []

    vod_id = str(vod.get("vod_id"))
    by_before: dict[int, list[dict]] = {}
    by_after: dict[int, list[dict]] = {}
    for spec in specs:
        if spec.get("before_episode") is not None:
            before_ep = int(spec["before_episode"])
            by_before.setdefault(before_ep, []).append(spec)
        else:
            after_ep = int(spec.get("after_episode") or end_ep)
            by_after.setdefault(after_ep, []).append(spec)

    chapters = []
    cursor = 0

    def append_special(spec: dict) -> None:
        nonlocal cursor
        requested = int(spec.get("duration_seconds") or 0)
        if requested <= 0 or cursor >= duration:
            return
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

    for ep in range(start_ep, end_ep + 1):
        for spec in by_before.get(ep, []):
            append_special(spec)

        this_episode_seconds = EPISODE_DURATION_OVERRIDES.get(
            ep,
            regular_duration_map.get(ep, episode_seconds),
        )
        stop = min(duration, cursor + this_episode_seconds)
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
            append_special(spec)

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


def _mark_provisional_titles(
    chapters: list[dict],
    start_ep: int,
    end_ep: int,
) -> list[dict]:
    confirmed = (start_ep, end_ep) in FILELIST_CONFIRMED_RANGES
    out = []
    for chapter in chapters:
        row = dict(chapter)
        if confirmed:
            row["title_status"] = "confirmed-filelist"
            row["title_source"] = "source-player-filelist"
        else:
            title = str(row.get("title") or "")
            if title and not title.endswith("（仮）"):
                row["title"] = f"{title}（仮）"
            row["title_status"] = "provisional"
            row["title_source"] = "pending-user-check"
        out.append(row)
    return out


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
        elif not vod.get("vod_id"):
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
        previous_result = previous_results.get(str(vod.get("vod_id")))
        if status == "ready" and chapters and start_ep < 177:
            if (
                previous_result
                and previous_result.get("status") == "ready"
                and previous_result.get("chapters")
            ):
                chapters = previous_result["chapters"]
                titlecard_refinement = previous_result.get("titlecard_refinement") or {
                    "status": "reused"
                }
            else:
                titlecard_refinement = {
                    "status": "legacy-structured",
                    "reason": "image-refinement-limited-to-177-plus",
                }
        elif status == "ready" and chapters and vod.get("playable"):
            chapters, titlecard_refinement = refine_with_titlecard(
                vod,
                chapters,
                previous_result,
            )
        elif status == "ready" and chapters:
            titlecard_refinement = {
                "status": "skipped",
                "reason": "direct-source-unavailable-kept-structured-split",
            }

        known_op_probe = None
        global_op_probe = None
        hls_join_markers = None
        opening_sequence_probe = None
        packet_join_probe = None
        if status == "ready" and chapters:
            if start_ep == 227 and vod.get("source_url"):
                known_op_probe = _probe_known_35s_op(str(vod.get("source_url")), chapters, duration)
                global_op_probe = _probe_global_op_logo_starts(str(vod.get("source_url")), duration, count, chapters)
            if start_ep == 177 and vod.get("source_url"):
                hls_join_markers = _fetch_hls_join_markers(str(vod.get("source_url")))
                packet_join_probe = _probe_selected_episode_joins(str(vod.get("source_url")), chapters)
                opening_sequence_probe = _probe_recurring_opening_sequence(str(vod.get("source_url")), chapters, duration)
            chapters = _annotate_hls_diagnostics(vod, chapters)
            chapters = _mark_provisional_titles(chapters, start_ep, end_ep)

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
            "hls_join_markers": hls_join_markers if start_ep == 177 else None,
            "packet_join_probe": packet_join_probe if start_ep == 177 else None,
            "opening_sequence_probe": opening_sequence_probe if start_ep == 177 else None,
            "known_op_probe": known_op_probe if start_ep == 227 else None,
            "global_op_probe": global_op_probe if start_ep == 227 else None,
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
        if (x.get("titlecard_refinement") or {}).get("status") in {"applied", "partial"}
    )
    print(
        f"GMCX chapters: ready_vods={ready} chapters={len(all_chapters)} "
        f"ai_required={ai} waiting={waiting} source_unavailable={unavailable} "
        f"titlecard_refined={refined}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
