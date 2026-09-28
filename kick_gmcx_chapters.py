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

# Range-specific cadence measured from clean same-season KICK bundles.
# Season 18's clean #177-196 archive is 77,992 sec / 20 ~= 3,900 sec.
RANGE_EPISODE_SECONDS: dict[tuple[int, int], int] = {
    (177, 196): 3900,
    (197, 206): 3871,
    (207, 216): 3900,
    (217, 226): 3900,
}

# Numbered episodes that are actually long-form specials.
EPISODE_DURATION_OVERRIDES: dict[int, int] = {
    226: 7200,  # in 四国 / 奇々怪界: official 2-hour special
}

# Real-video boundary refinement. GMCX repeats a characteristic title/opening
# frame at the beginning of regular episodes. We learn that recurring visual
# signature inside each VOD and place every split on the same visual cue.
TITLECARD_WINDOW_SECONDS = 240
TITLECARD_SAMPLE_SECONDS = 2
TITLECARD_BOUNDARY_VERSION = 14
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
TITLECARD_REGULAR_MAX_SHIFT_SECONDS = 240
BLUE_ROOM_MIN_BLUE = 70
BLUE_ROOM_BLUE_RED_GAP = 24
BLUE_ROOM_BLUE_GREEN_GAP = 10
BLUE_ROOM_HASH_DISTANCE = 46
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
TITLE_LOGO_MAX_EXPECTED_DISTANCE_SECONDS = 150
TITLE_LOGO_COMPONENT_MIN_WIDTH_RATIO = 0.50
TITLE_LOGO_COMPONENT_MIN_HEIGHT_RATIO = 0.18
TITLE_LOGO_COMPONENT_MIN_ASPECT = 2.6
TITLE_LOGO_COMPONENT_MAX_ASPECT = 6.2
TITLE_LOGO_COMPONENT_CENTER_TOLERANCE = 0.22
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
            "key": "2015-mario-maker-play",
            "title": "GMCX 「スーパーマリオメーカー」を遊ぶ編",
            "before_episode": 207,
            "duration_seconds": 2700,
            "expected_broadcast_seconds": 2700,
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
            "duration_seconds": None,
            "expected_broadcast_seconds": 600,
        },
    ],
    (217, 226): [
        {
            "key": "2016-pokemon-1",
            "title": "GMCX 特別篇 ポケットモンスター赤・緑 #1",
            "after_episode": 219,
            "duration_group": "pokemon-2016",
        },
        {
            "key": "2016-pokemon-2",
            "title": "GMCX 特別篇 ポケットモンスター赤・緑 #2",
            "after_episode": 222,
            "duration_group": "pokemon-2016",
        },
        {
            "key": "2016-pokemon-3",
            "title": "GMCX 特別篇 ポケットモンスター赤・緑 #3",
            "after_episode": 224,
            "duration_group": "pokemon-2016",
        },
        {
            "key": "2016-pokemon-4",
            "title": "GMCX 特別篇 ポケットモンスター赤・緑 #4",
            "after_episode": 225,
            "duration_group": "pokemon-2016",
        },
        {
            "key": "2016-pokemon-5",
            "title": "GMCX 特別篇 ポケットモンスター赤・緑 #5",
            "after_episode": 226,
            "duration_group": "pokemon-2016",
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

    anchor = usable[0]
    best = None
    for frame in anchor:
        matches = 0
        distances = []
        for w in usable[1:]:
            d = min((_hdist(frame["hash"], x["hash"]) for x in w), default=999)
            distances.append(d)
            if d <= BLUE_ROOM_HASH_DISTANCE:
                matches += 1
        required = max(2, int(round((len(usable) - 1) * 0.45)))
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


def _pick_anchor_title_logo(frames: list[dict], chapter_start: int) -> tuple[dict | None, dict]:
    candidates = []
    for run in _title_logo_runs(frames):
        start = int(run[0]["time"])
        offset = start - int(chapter_start)
        if offset < 0 or offset > TITLE_LOGO_REFERENCE_SEARCH_SECONDS:
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
        )
        candidates.append((score, start, best, run))
    if not candidates:
        return None, {"reason": "no_title_logo_near_reference_start"}
    candidates.sort(key=lambda x: x[0])
    _, start, best, run = candidates[0]
    ref = dict(best)
    ref["run_start"] = start
    return ref, {
        "reason": "ok",
        "title_time": start,
        "offset_seconds": start - int(chapter_start),
        "run_frames": len(run),
        "width_ratio": best.get("width_ratio"),
        "height_ratio": best.get("height_ratio"),
        "aspect": best.get("aspect"),
        "yellow_fill": best.get("yellow_fill"),
    }

def _match_title_logo(reference: dict, frames: list[dict], expected_time: int) -> tuple[int | None, dict]:
    candidates = []
    for run in _title_logo_runs(frames):
        start = int(run[0]["time"])
        best = max(
            run,
            key=lambda x: (
                float(x.get("width_ratio") or 0),
                float(x.get("yellow_fill") or 0),
            ),
        )
        score = (
            abs(start - int(expected_time)),
            -len(run),
            -float(best.get("width_ratio") or 0),
            -float(best.get("yellow_fill") or 0),
        )
        candidates.append((score, start, best, len(run)))

    if not candidates:
        return None, {"reason": "no_matching_title_logo"}
    candidates.sort(key=lambda x: x[0])
    _, start, best, run_frames = candidates[0]
    if abs(start - int(expected_time)) > TITLE_LOGO_MAX_EXPECTED_DISTANCE_SECONDS:
        return None, {
            "reason": "nearest_title_logo_too_far",
            "distance_from_expected": start - int(expected_time),
        }
    return start, {
        "reason": "ok",
        "run_frames": run_frames,
        "expected_title_time": int(expected_time),
        "distance_from_expected": start - int(expected_time),
        "bbox_width": best.get("bbox_width"),
        "bbox_height": best.get("bbox_height"),
        "width_ratio": best.get("width_ratio"),
        "height_ratio": best.get("height_ratio"),
        "aspect": best.get("aspect"),
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

def refine_with_titlecard(
    vod: dict,
    chapters: list[dict],
    previous_result: dict | None = None,
) -> tuple[list[dict], dict]:
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
    logo_windows = []
    for item in items:
        center = int(item.get("start_seconds") or 0)
        logo_windows.append(_sample_title_logo_window(analysis_url, center, duration))

    # Learn the user-confirmed yellow title logo from the first regular episode.
    regular_indices = [
        i for i, item in enumerate(items)
        if item.get("kind") == "episode"
        and int(item.get("episode") or 0) not in EPISODE_DURATION_OVERRIDES
    ]
    if not regular_indices:
        return chapters, {"status": "skipped", "reason": "no_regular_episode_reference"}

    anchor_index = regular_indices[0]
    anchor_start = int(items[anchor_index].get("start_seconds") or 0)
    reference, anchor_meta = _pick_anchor_title_logo(
        logo_windows[anchor_index],
        anchor_start,
    )
    if reference is None:
        return chapters, {
            "status": "no_consensus",
            "method": "yellow-gmcx-title-logo",
            "boundary_version": TITLECARD_BOUNDARY_VERSION,
            "reference": anchor_meta,
            "matches": [],
        }

    title_offset = int(anchor_meta["offset_seconds"])
    starts: dict[int, int] = {}
    match_rows = []

    for index, (item, frames) in enumerate(zip(items, logo_windows)):
        original = int(item.get("start_seconds") or 0)
        if index == 0:
            starts[index] = 0
            match_rows.append({
                "index": index,
                "title": item.get("title"),
                "matched": True,
                "method": "vod-start",
                "original": original,
                "refined": 0,
            })
            continue

        is_long_numbered_special = (
            item.get("kind") == "episode"
            and int(item.get("episode") or 0) in EPISODE_DURATION_OVERRIDES
        )
        is_special = item.get("kind") == "special" or is_long_numbered_special

        # Specials use their known chronological/official boundary. They may
        # have a different opening design, so do not force a regular title match.
        if is_special:
            starts[index] = original
            match_rows.append({
                "index": index,
                "title": item.get("title"),
                "matched": True,
                "method": "structured-special-boundary",
                "original": original,
                "refined": original,
                "shift_seconds": 0,
            })
            continue

        expected_title = original + title_offset
        title_time, meta = _match_title_logo(reference, frames, expected_title)
        if title_time is None:
            match_rows.append({
                "index": index,
                "title": item.get("title"),
                "matched": False,
                "original": original,
                "expected_title": expected_title,
                "logo": meta,
            })
            continue

        refined = max(0, int(title_time) - title_offset)
        if abs(refined - original) > TITLECARD_REGULAR_MAX_SHIFT_SECONDS:
            match_rows.append({
                "index": index,
                "title": item.get("title"),
                "matched": False,
                "original": original,
                "candidate": refined,
                "reason": "shift_guard",
                "logo": meta,
            })
            continue

        starts[index] = refined
        match_rows.append({
            "index": index,
            "title": item.get("title"),
            "matched": True,
            "method": "yellow-gmcx-title-logo",
            "original": original,
            "title_time": int(title_time),
            "title_offset": title_offset,
            "refined": refined,
            "shift_seconds": refined - original,
            "logo": meta,
        })

    regular_nonfirst = [i for i in regular_indices if i != 0]
    matched_regular = sum(
        1 for row in match_rows
        if row.get("method") == "yellow-gmcx-title-logo"
    )

    rebuilt = _apply_refined_chapter_starts(
        [{**x, "vod_id": vod_id} for x in chapters],
        starts,
        duration,
    )
    unchanged = rebuilt == [{**x, "vod_id": vod_id} for x in chapters]
    if unchanged and matched_regular:
        return chapters, {
            "status": "guarded",
            "method": "yellow-gmcx-title-logo",
            "boundary_version": TITLECARD_BOUNDARY_VERSION,
            "reason": "order_or_minimum-gap-guard",
            "reference": anchor_meta,
            "matches": match_rows,
        }

    for x in rebuilt:
        x.pop("vod_id", None)

    expected_regular = max(1, len(regular_indices) - 1)
    coverage = matched_regular / expected_regular
    status = "applied" if coverage >= 0.8 else ("partial" if matched_regular else "no_consensus")
    return rebuilt, {
        "status": status,
        "method": "yellow-gmcx-title-logo",
        "boundary_version": TITLECARD_BOUNDARY_VERSION,
        "window_seconds": TITLECARD_WINDOW_SECONDS,
        "sample_seconds": TITLE_LOGO_SAMPLE_SECONDS,
        "reference": anchor_meta,
        "title_offset_seconds": title_offset,
        "detected_regular_boundaries": matched_regular,
        "expected_regular_boundaries": expected_regular,
        "coverage": round(coverage, 3),
        "chapter_starts": {str(k): v for k, v in starts.items()},
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


def make_mixed_chapters(vod: dict, start_ep: int, end_ep: int, titles: dict[str, str]) -> list[dict]:
    count = end_ep - start_ep + 1
    duration = int(vod.get("duration_seconds") or 0)
    episode_seconds = RANGE_EPISODE_SECONDS.get((start_ep, end_ep), REFERENCE_EPISODE_SECONDS)
    regular_total = sum(
        EPISODE_DURATION_OVERRIDES.get(ep, episode_seconds)
        for ep in range(start_ep, end_ep + 1)
    )
    if duration < regular_total:
        return []

    specs = [dict(x) for x in KNOWN_SPECIALS.get((start_ep, end_ep), [])]
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

        this_episode_seconds = EPISODE_DURATION_OVERRIDES.get(ep, episode_seconds)
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
