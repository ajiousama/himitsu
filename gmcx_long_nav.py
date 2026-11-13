#!/usr/bin/env python3
"""Conservative time-navigation chapters for unresolved long GCCX KICK archives.

This is NOT episode detection. Never give a time slice an episode number or
overwrite confirmed cuts. Keep original full/remainder entries in VOD5.
Existing GCCX video/BGM chapter maps remain the source of truth.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import quote

CHUNK_SECONDS = 58 * 60
MIN_RANGE_SECONDS = 2 * 60 * 60
MIN_LAST_SECONDS = 5 * 60
MAX_CHUNKS_PER_VOD = 72
RESOLVER = "https://kick-resolver-production.up.railway.app/kick?vod="
LOGO = "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/contrast/kick.gccx.logo_4fa63dbb.png"


def time_slices(start: int, end: int) -> list[tuple[int, int]]:
    """Cover a known time range without gaps; merge a tiny final remainder."""
    if start < 0 or end <= start or end - start < MIN_RANGE_SECONDS:
        return []
    spans = []
    point = start
    while end - point > CHUNK_SECONDS:
        spans.append((point, point + CHUNK_SECONDS))
        point += CHUNK_SECONDS
        if len(spans) > MAX_CHUNKS_PER_VOD:
            return []
    if spans and end - point < MIN_LAST_SECONDS:
        spans[-1] = (spans[-1][0], end)
    else:
        spans.append((point, end))
    return spans if len(spans) <= MAX_CHUNKS_PER_VOD else []


def hms(seconds: int) -> str:
    hours, remainder = divmod(int(seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def _range_for_vod(vod: dict, result: dict) -> tuple[int, int, str] | None:
    duration = int(vod.get("duration_seconds") or 0)
    if duration < MIN_RANGE_SECONDS:
        return None
    if result.get("status") == "range_unknown":
        # The source title does not identify the episode(s). Time navigation
        # is useful, but MUST NOT be presented as confirmed episode cuts.
        return 0, duration, "録画"
    if result.get("status") == "ready" and result.get("partial") is True:
        chapters = result.get("chapters") or []
        if not chapters:
            return None
        tail = chapters[-1]
        if (
            tail.get("kind") == "special"
            and tail.get("confidence") == "unconfirmed"
            and "未分割" in str(tail.get("title") or "")
        ):
            start = int(tail.get("start_seconds") or 0)
            end = int(tail.get("stop_seconds") or 0)
            if 0 <= start < end <= duration + 10:
                return start, min(end, duration), "後半未分類"
    return None


def build_time_navigation_entries(
    replay_path: Path, chapter_path: Path
) -> list[tuple[str, str]]:
    """Generate M3U entries only for available GCCX VODs with unresolved spans.

    Source clips are short seekable ranges, without fetching media. The
    unverified slots do not replace the original full VOD or special tail.
    """
    if not replay_path.exists() or not chapter_path.exists():
        return []
    try:
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
        chapters = json.loads(chapter_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []

    results = {
        str(item.get("vod_id")): item
        for item in chapters.get("results", [])
        if isinstance(item, dict) and item.get("vod_id")
    }
    entries = []
    for vod in replay.get("vods", []):
        if not isinstance(vod, dict):
            continue
        vod_id = str(vod.get("vod_id") or "")
        if (
            not str(vod.get("tvg_id") or "").startswith("kick.gccx")
            or vod.get("ready_for_publish") is not True
            or vod.get("playable") is not True
            or not re.fullmatch(r"[A-Za-z0-9_-]{8,120}", vod_id)
        ):
            continue
        result = results.get(vod_id)
        if not result:
            continue
        unresolved = _range_for_vod(vod, result)
        if not unresolved:
            continue
        start, end, kind = unresolved
        spans = time_slices(start, end)
        if not spans:
            continue
        created = str(vod.get("created_at") or "")
        date_label = created[5:10].replace("-", "/") if re.match(r"\d{4}-\d{2}-\d{2}", created) else "日時未詳"
        for index, (begin, stop) in enumerate(spans, 1):
            part_id = f"kick.gmcx.nav.{vod_id[:12]}.{begin}"
            label = (
                f"📼 GCCX {date_label} {kind}・仮チャプター "
                f"{index}/{len(spans)}（{hms(begin)}〜{hms(stop)}／話数未確認）"
            )
            extinf = (
                '#EXTINF:-1 group-title="KICK系VOD" '
                f'tvg-id="{part_id}" tvg-logo="{LOGO}",{label}'
            )
            url = f"{RESOLVER}{quote(vod_id, safe='')}&start={begin}&duration={stop - begin}"
            entries.append((extinf, url))
    return entries
