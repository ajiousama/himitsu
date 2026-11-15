#!/usr/bin/env python3
"""Video-anchored continuous programme groups for short GCCX navigation slices.

The groups never change stream start/end, never create multi-hour playback
entries and never claim that an unseen interval was video verified.
"""
from __future__ import annotations

import json
from pathlib import Path

GROUPS_FILE = Path("gmcx_continuity_groups.json")
CHUNK_SECONDS = 3480


def grouped_slices(
    vod: dict,
    spans: list[tuple[int, int]],
    observed: dict[tuple[str, int], tuple[str, int | None]],
    groups_path: Path = GROUPS_FILE,
) -> dict[int, dict]:
    """Return grouped short-clip metadata keyed by original clip start.

    Fail closed per group if VOD source changed, saved span boundaries no
    longer match, image evidence is absent or group ranges overlap.
    """
    if not groups_path.is_file():
        return {}
    try:
        config = json.loads(groups_path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}
    if config.get("schema_version") != 1 or not isinstance(config.get("groups"), list):
        return {}
    vod_id = str(vod.get("vod_id") or "")
    source_url = str(vod.get("source_url") or "")
    if not vod_id or not source_url:
        return {}
    result: dict[int, dict] = {}
    for group in config["groups"]:
        if not isinstance(group, dict) or group.get("source_vod_id") != vod_id:
            continue
        if (group.get("source_url") != source_url
            or group.get("confidence") != "video_anchored_continuity_estimate"):
            continue
        try:
            start = int(group["start_seconds"])
            end = int(group["end_seconds"])
            anchors = [int(x) for x in group.get("evidence_anchor_starts", [])]
        except (KeyError, TypeError, ValueError):
            continue
        title = str(group.get("title") or "").replace("\n", " ").replace('"', "'").strip()
        slug = str(group.get("group_id") or "").strip()
        if (not title or len(title) > 90 or not slug or start < 0 or end <= start
            or len(anchors) < 2 or len(set(anchors)) != len(anchors)
            or not all(start <= x < end and (vod_id, x) in observed for x in anchors)):
            continue
        inside = [(a, b) for a, b in spans if start <= a and b <= end]
        if (len(inside) < 2 or inside[0][0] != start or inside[-1][1] != end
            or any(left[1] != right[0] for left, right in zip(inside, inside[1:]))
            or any(a in result for a, _ in inside)):
            continue
        for i, (a, b) in enumerate(inside, 1):
            if not 60 <= b-a <= 3605:
                break
        else:
            for i, (a, b) in enumerate(inside, 1):
                result[a] = {
                    "group_id": slug,
                    "title": title,
                    "part": i,
                    "total": len(inside),
                    "anchor": any(a <= t < b for t in anchors),
                    "part_label_style": (
                        "fullwidth_letter"
                        if group.get("part_label_style") == "fullwidth_letter"
                        else "numeric"
                    ),
                }
    return result


def grouped_label(group: dict, observed_title: str | None, date: str,
                  start_text: str, end_text: str) -> str:
    """Explicitly distinguish observed footage from inferred continuity."""
    sequence = f"{group['part']:02d}/{group['total']:02d}"
    if group.get("part_label_style") == "fullwidth_letter":
        # User-facing A, B, C ... naming, independent of inferred broadcast cuts.
        # Supports A-Z, then AA, AB, etc. without silently truncating at 26.
        i = int(group["part"])
        letters = ""
        while i > 0:
            i, remainder = divmod(i - 1, 26)
            letters = chr(0xFF21 + remainder) + letters
        heading = f"{group['title']}{letters}"
    else:
        heading = group["title"]
    if observed_title:
        # One 58-minute slice can show several games, so show what was
        # actually seen even if the wider programme was different.
        inside = f"［映像：{observed_title}］"
        status = "映像あり・区間境界は仮"
    else:
        inside = ""
        status = "前後の映像から継続推定"
    return (
        f"📼 GCCX {heading}｜連続{sequence}{inside}"
        f"（{status}／{date} {start_text}〜{end_text}）"
    )
