#!/usr/bin/env python3
"""Conservative application of recurring opening-sound candidates to GCCX navigation.

Audio candidates are never 'confirmed programme starts'. A strong independently
calibrated acoustic match may move a provisional navigation edge, but the
caption must say 'audio provisional' until the video opening is inspected.
Do not change visually confirmed programme boundaries or series continuity
windows (such as the Lemmings A-W marathon).
"""
from __future__ import annotations
import json
from pathlib import Path

REPORT = Path("gmcx_auto_opening_review.json")
GROUPS = Path("gmcx_continuity_groups.json")
MAX_SHIFT = 36
MAX_SECONDS_PER_CLIP = 3605
MIN_SECONDS_PER_CLIP = 180
MIN_STRONG = 2
MIN_SIMILARITY = 0.68


def locked_continuity_ranges(vod: dict, groups_path: Path = GROUPS) -> list[tuple[int,int]]:
    try:
        cfg=json.loads(groups_path.read_text(encoding="utf-8"))
    except (ValueError,OSError):
        return []
    if cfg.get("schema_version")!=1:
        return []
    locked=[]
    for g in cfg.get("groups",[]):
        if (isinstance(g,dict)
            and g.get("source_vod_id")==vod.get("vod_id")
            and g.get("source_url")==vod.get("source_url")):
            try:
                a,b=int(g["start_seconds"]),int(g["end_seconds"])
                if a<b:
                    locked.append((a,b))
            except (ValueError,TypeError,KeyError):
                pass
    return locked


def candidates_for_vod(vod: dict, start: int, end: int,
                       report_path: Path = REPORT) -> list[tuple[int,int]]:
    try:
        cfg=json.loads(report_path.read_text(encoding="utf-8"))
    except (ValueError,OSError):
        return []
    if cfg.get("schema_version")!=1:
        return []
    entry=(cfg.get("vods") or {}).get(str(vod.get("vod_id")))
    if not isinstance(entry,dict):
        return []
    if (entry.get("source_url")!=vod.get("source_url")
        or entry.get("duration_seconds")!=vod.get("duration_seconds")):
        return []
    accepted=[]
    for nominal,row in (entry.get("rows") or {}).items():
        if not isinstance(row,dict) or row.get("status")!="candidate":
            continue
        if row.get("verification")!="audio_only_needs_video":
            continue
        try:
            orig=int(nominal)
            actual=round(float(row["candidate_seconds"]))
            strong=int(row["strong_matches"])
            score=float(row["mean_similarity"])
        except (KeyError,ValueError,TypeError):
            continue
        if (not start<orig<end or not start<actual<end
            or abs(actual-orig)>MAX_SHIFT or strong<MIN_STRONG
            or not MIN_SIMILARITY<=score<=1.0):
            continue
        accepted.append((orig,actual))
    return sorted(set(accepted))


def snap_audio_starts(
    spans: list[tuple[int,int]], vod: dict, original_start: int,
    original_end: int, verified_starts: list[int],
    report_path: Path = REPORT, groups_path: Path = GROUPS,
) -> tuple[list[tuple[int,int]],set[int]]:
    """Use only exact matching published nominal edges; never create gaps."""
    if len(spans)<2:
        return spans[:],set()
    lock=locked_continuity_ranges(vod,groups_path)
    protected=set(verified_starts)
    original=spans[:]
    aligned=[list(s) for s in original]
    snapped=set()
    for nominal,proposed in candidates_for_vod(vod,original_start,
                                                  original_end,report_path):
        if proposed==nominal or nominal in protected:
            continue
        # Never perturb group starts/ends or any edge inside an annotated
        # continuous programme, including estimated 24-hour specials.
        if any(a<=nominal<=b or a<=proposed<=b for a,b in lock):
            continue
        choices=[i for i in range(len(aligned)-1)
                 if original[i][1]==nominal
                 and original[i+1][0]==nominal]
        if len(choices)!=1:
            continue
        i=choices[0]
        if not (MIN_SECONDS_PER_CLIP<=proposed-aligned[i][0]<=MAX_SECONDS_PER_CLIP
                and MIN_SECONDS_PER_CLIP<=aligned[i+1][1]-proposed<=MAX_SECONDS_PER_CLIP):
            continue
        aligned[i][1]=proposed
        aligned[i+1][0]=proposed
        snapped.add(proposed)
    result=[tuple(s) for s in aligned]
    if (result[0][0]!=original[0][0]
        or result[-1][1]!=original[-1][1]
        or any(a>=b or b-a>MAX_SECONDS_PER_CLIP for a,b in result)
        or any(result[i][1]!=result[i+1][0]
               for i in range(len(result)-1))):
        raise ValueError("GCCX audio snap would change source coverage")
    return result,snapped
