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

from gmcx_continuity import grouped_label, grouped_slices
from gmcx_exact_nav import snap_verified_starts, validated_starts
from gmcx_auto_opening import snap_audio_starts

CHUNK_SECONDS = 58 * 60
MIN_RANGE_SECONDS = 2 * 60 * 60
MIN_LAST_SECONDS = 5 * 60
MAX_CHUNKS_PER_VOD = 72
RESOLVER = "https://kick-resolver-production.up.railway.app/kick?vod="
LOGO = "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/contrast/kick.gccx.logo_4fa63dbb.png"

OCR_REPORT = Path("gmcx_unknown_title_review.json")
EPISODE_TITLES = Path("gmcx_episode_titles.json")
FRAME_REVIEW = Path("gmcx_frame_identified_titles.json")
SEQUENCE_ESTIMATES = Path("gmcx_chronological_title_estimates.json")


def ocr_title_candidates(replay: dict) -> dict[tuple[str, int], tuple[int, str]]:
    """Use OCR-confirmed title-text matches, but never invent a verified boundary."""
    if not OCR_REPORT.is_file() or not EPISODE_TITLES.is_file():
        return {}
    try:
        report = json.loads(OCR_REPORT.read_text(encoding="utf-8"))
        titles = json.loads(EPISODE_TITLES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    sources = {
        str(v.get("vod_id")): str(v.get("source_url") or "")
        for v in replay.get("vods", [])
        if isinstance(v, dict) and v.get("vod_id")
    }
    out: dict[tuple[str, int], tuple[int, str]] = {}
    for vod_id, entry in (report.get("vods") or {}).items():
        if not isinstance(entry, dict) or not sources.get(vod_id):
            continue
        if entry.get("source_url") != sources[vod_id]:
            continue
        for start_key, row in (entry.get("rows") or {}).items():
            if not isinstance(row, dict) or row.get("status") not in {
                "ocr_match", "ocr_match_from_workflow_log",
            }:
                continue
            # Historical OCR results may predate the episode-guide guard.
            # Do not publish a title read from a multi-episode listing.
            samples = row.get("samples") or []
            excerpts = "\\n".join(str(x.get("ocr_excerpt") or "")
                                 for x in samples if isinstance(x, dict))
            if len(set(re.findall(r"#\\s*\\d{2,4}", excerpts))) >= 2:
                continue
            candidate = row.get("candidate") or {}
            try:
                ep = int(candidate.get("episode"))
                start = int(start_key)
                score = float(candidate.get("score") or 0)
            except (TypeError, ValueError):
                continue
            title = str(candidate.get("title") or "")
            if title != titles.get(str(ep)):
                continue
            if row.get("status") == "ocr_match_from_workflow_log":
                evidence = row.get("evidence") or {}
                if not evidence.get("workflow_run_id") or not evidence.get("job_id"):
                    continue
            elif score < 0.84:
                continue
            if row.get("source_url") != sources[vod_id]:
                continue
            # OCR text alone cannot establish the current programme.
            # Historical unreviewed matches must also remain unpublished.
            if row.get("status") == "ocr_match":
                continue
            # Reject legacy OCR candidates where the only apparent game
            # name is a numbered sequel of a shorter title.
            # Check only unnumbered titles; numbered titles match exactly.
            import unicodedata
            base = re.sub(r"[^a-z0-9ぁ-んァ-ヶ一-龯]", "",
                          unicodedata.normalize("NFKC", title).lower())
            if base and not base[-1].isdigit():
                def normalize_excerpt(value: str) -> str:
                    return re.sub(r"[^a-z0-9ぁ-んァ-ヶ一-龯]", "",
                                  unicodedata.normalize("NFKC", value).lower())
                excerpts_normal = [
                    normalize_excerpt(x.get("ocr_excerpt") or "")
                    for x in samples if isinstance(x, dict)
                ]
                if (any(re.search(re.escape(base) + r"[0-9]", x)
                        for x in excerpts_normal)
                    and not any(base in x and not re.search(
                        re.escape(base) + r"[0-9]", x)
                        for x in excerpts_normal)):
                    continue
            out[(vod_id, start)] = (ep, title)
    return out


def frame_title_candidates(replay: dict) -> dict[tuple[str, int], tuple[str, int | None]]:
    """Apply manually inspected video-frame evidence to the exact source only."""
    if not FRAME_REVIEW.is_file():
        return {}
    try:
        data = json.loads(FRAME_REVIEW.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    sources = {
        str(v.get("vod_id")): str(v.get("source_url") or "")
        for v in replay.get("vods", [])
        if isinstance(v, dict) and v.get("vod_id")
    }
    accepted = {
        "actual_gameplay_visible_episode_and_end_not_verified",
        "actual_gameplay_visible_episode_candidate_not_verified",
        # Human-reviewed subject/mixed-corner frames: preserve the named content,
        # never promote it into a verified whole episode or exact boundary.
        "actual_video_shows_subject_but_exact_episode_unverified",
        "ai_visual_consensus_boundary_unverified",
    }
    result = {}
    for row in data.get("entries", []):
        if not isinstance(row, dict) or row.get("confidence") not in accepted:
            continue
        vod_id = str(row.get("source_vod_id") or "")
        if not sources.get(vod_id) or row.get("source_url") != sources[vod_id]:
            continue
        title = str(row.get("title") or "").strip()
        if not title or len(title) > 100:
            continue
        try:
            at = int(row.get("start_seconds"))
            ep = int(row["episode_candidate"]) if row.get("episode_candidate") else None
        except (TypeError, ValueError):
            continue
        kind = row.get("confidence")
        if kind == "ai_visual_consensus_boundary_unverified":
            if (vod_id, at) in result:
                continue
            ep = None
        result[(vod_id, at)] = (title, ep, "ai" if kind == "ai_visual_consensus_boundary_unverified" else kind == "actual_video_shows_subject_but_exact_episode_unverified")
    return result


def chronological_title_hints(replay: dict) -> dict[tuple[str, int], tuple[int | None, str]]:
    """Tentative names by episode order; NEVER treated as verified cuts."""
    if not SEQUENCE_ESTIMATES.is_file() or not EPISODE_TITLES.is_file():
        return {}
    try:
        data = json.loads(SEQUENCE_ESTIMATES.read_text(encoding="utf-8"))
        title_map = json.loads(EPISODE_TITLES.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    by_id = {
        str(v.get("vod_id")): v
        for v in replay.get("vods", [])
        if isinstance(v, dict) and v.get("vod_id")
    }
    results: dict[tuple[str, int], tuple[int | None, str]] = {}
    for rule in data.get("rules", []):
        if not isinstance(rule, dict):
            continue
        vod_id = str(rule.get("source_vod_id") or "")
        vod = by_id.get(vod_id)
        if (not vod or not rule.get("source_url")
            or rule.get("source_url") != vod.get("source_url")
            or rule.get("confidence") != "provisional_chronological_inference"):
            continue
        try:
            duration = int(vod.get("duration_seconds") or 0)
            begin = int(rule.get("nav_start_seconds"))
            first_slot = int(rule.get("first_slot_index"))
            first_episode = int(rule.get("first_episode"))
            last_episode = int(rule.get("last_episode"))
        except (TypeError, ValueError):
            continue
        if (duration <= 0 or begin < 0 or first_slot < 0
            or first_episode <= 0 or last_episode < first_episode):
            continue
        try:
            stop_guessing_at = int(
                rule.get("disable_episode_sequence_at_or_after_seconds") or 0
            )
        except (TypeError, ValueError):
            stop_guessing_at = 0
        suspended_label = str(rule.get("post_special_label") or "").strip()
        for index in range(MAX_CHUNKS_PER_VOD):
            start = begin + index * CHUNK_SECONDS
            if start >= duration:
                break
            # A long live special can cover many 58-minute clips. Without a
            # newly observed post-special episode opening, advancing an
            # episode each clip makes every later title drift.
            if stop_guessing_at and start >= stop_guessing_at:
                if suspended_label:
                    results[(vod_id, start)] = (None, suspended_label)
                continue
            if index < first_slot:
                title = str(rule.get("early_special_title") or "").strip()
                if title:
                    results[(vod_id, start)] = (None, title)
                continue
            # Some 58-minute windows cross the same broadcast episode;
            # verified repeated-episode slots shift every later estimate.
            repeats = rule.get("episode_repeat_slots") or []
            if not isinstance(repeats, list):
                repeats = []
            repeats = [int(value) for value in repeats if isinstance(value, int)
                       and first_slot < value <= index]
            ep = first_episode + (index - first_slot) - len(set(repeats))
            if ep > last_episode:
                break
            title = title_map.get(str(ep))
            if title:
                results[(vod_id, start)] = (ep, title)
    return results


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
                # The older provisional chapter detector can truncate the
                # final HLS seconds (e.g. 172795 vs source 172798). Preserve
                # a <=10s measured source tail instead of silently dropping it.
                if 0 <= duration - end <= 10:
                    end = duration
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
    ocr_candidates = ocr_title_candidates(replay)
    observed_games = frame_title_candidates(replay)
    chronological = chronological_title_hints(replay)
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
        nominal_spans = spans[:]
        # Observed image boundaries always override audio estimates.
        verified_starts = validated_starts(vod, start, end)
        spans = snap_verified_starts(spans, verified_starts)
        # Automated recurring intro-sound matches can shift only safe,
        # provisional edges. Confirmed starts and series/marathons are locked.
        spans, audio_starts = snap_audio_starts(
            spans, vod, start, end, verified_starts
        )
        continuity = grouped_slices(vod, spans, {k: v for k, v in observed_games.items() if v[2] != "ai"})
        created = str(vod.get("created_at") or "")
        date_label = created[5:10].replace("-", "/") if re.match(r"\d{4}-\d{2}-\d{2}", created) else "日時未詳"
        for index, (begin, stop) in enumerate(spans, 1):
            # Title evidence was gathered at the original provisional clip
            # start; audio alignment may move it by a few seconds.
            nominal = nominal_spans[index - 1][0]
            part_id = f"kick.gmcx.nav.{vod_id[:12]}.{begin}"
            gameplay = (observed_games.get((vod_id, begin))
                        or observed_games.get((vod_id, nominal)))
            if gameplay is None:
                # Snapped boundary can precede a verified game frame by a
                # few seconds (e.g. SP intro at 59152; game frame at 59173).
                gameplay = next(
                    (observed_games[(vod_id, t)] for t in range(begin+1, min(stop, begin+45))
                     if (vod_id, t) in observed_games),
                    None,
                )
            matched_title = (ocr_candidates.get((vod_id, begin))
                             or ocr_candidates.get((vod_id, nominal)))
            if (group := continuity.get(begin)):
                label = grouped_label(
                    group, gameplay[0] if gameplay else None,
                    date_label, hms(begin), hms(stop),
                    verified_start=begin in verified_starts,
                )
            elif gameplay:
                game, possible_episode, is_content_only = gameplay
                hint = f"（#{possible_episode}候補）" if possible_episode else ""
                evidence_label = "AI映像判定" if is_content_only == "ai" else ("実映像で内容確認" if is_content_only else "実映像でゲーム名確認")
                label = (
                    f"📼 GCCX {game}{hint}（{evidence_label}・境界仮／"
                    f"{date_label} {hms(begin)}〜{hms(stop)}）"
                )
            elif matched_title:
                ep, title = matched_title
                label = (
                    f"📼 GCCX #{ep} {title}（映像OCR候補・境界仮／"
                    f"{date_label} {hms(begin)}〜{hms(stop)}）"
                )
            elif (hint := (chronological.get((vod_id, begin))
                            or chronological.get((vod_id, nominal)))):
                ep, title = hint
                prefix = f"#{ep} " if ep is not None else ""
                suspended = (
                    ep is None and
                    ("通常回再開位置を確認中" in title)
                )
                label = (
                    f"📼 GCCX {prefix}{title}（"
                    f"{'特番をまたぐ話数推定を停止' if suspended else '放送順・位置から仮推定'}／"
                    f"{date_label} {hms(begin)}〜{hms(stop)}）"
                )
            else:
                label = (
                    f"📼 GCCX {date_label} {kind}・仮チャプター "
                    f"{index}/{len(spans)}（{hms(begin)}〜{hms(stop)}／話数未確認）"
                )
            if begin in audio_starts:
                # A song fingerprint is not proof of programme/episode ID.
                # Never call such an aligned edge "exact" or "confirmed".
                label = label.replace(
                    "実映像でゲーム名確認・境界仮",
                    "実映像でゲーム名確認・音声境界仮"
                ).replace(
                    "実映像で内容確認・境界仮",
                    "実映像で内容確認・音声境界仮"
                ).replace(
                    "映像OCR候補・境界仮", "映像OCR候補・音声境界仮"
                )
                if "音声境界仮" not in label:
                    label += "［音声による開始位置推定・要映像確認］"
            extinf = (
                '#EXTINF:-1 group-title="KICK系VOD" '
                f'tvg-id="{part_id}" tvg-logo="{LOGO}",{label}'
            )
            url = f"{RESOLVER}{quote(vod_id, safe='')}&start={begin}&duration={stop - begin}"
            entries.append((extinf, url))
    return entries


def build_video_observed_opening_entries(
    replay_path: Path, chapter_path: Path,
    evidence_path: Path = Path("gmcx_video_verified_openings.json"),
) -> list[tuple[str, str]]:
    """Add navigable *short previews* for genuine video-observed SP intros.

    This is not exact full-episode splitting: the end of the programme and its
    episode number are still unknown. Fail closed on every source mismatch.
    """
    if not replay_path.exists() or not chapter_path.exists() or not evidence_path.exists():
        return []
    try:
        replay = json.loads(replay_path.read_text(encoding="utf-8"))
        chapter_results = json.loads(chapter_path.read_text(encoding="utf-8"))
        evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    vod_id = str(evidence.get("source_vod_id") or "")
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,120}", vod_id):
        return []
    matching_vods = [x for x in replay.get("vods", [])
                     if isinstance(x, dict) and str(x.get("vod_id")) == vod_id]
    matching_results = [x for x in chapter_results.get("results", [])
                        if isinstance(x, dict) and str(x.get("vod_id")) == vod_id]
    if len(matching_vods) != 1 or len(matching_results) != 1:
        return []
    vod, result = matching_vods[0], matching_results[0]
    if (not str(vod.get("tvg_id") or "").startswith("kick.gccx")
        or vod.get("playable") is not True
        or vod.get("ready_for_publish") is not True):
        return []
    duration = int(vod.get("duration_seconds") or 0)
    if abs(duration - int(evidence.get("source_duration_seconds") or 0)) > 10:
        return []
    unresolved = _range_for_vod(vod, result)
    if not unresolved:
        return []
    tail_begin, tail_end, _ = unresolved
    entries = []
    seen = set()
    for opening in evidence.get("openings", []):
        if not isinstance(opening, dict):
            continue
        if (opening.get("confidence") != "video_intro_observed_episode_end_unverified"
            or opening.get("episode_number") is not None
            or opening.get("end_seconds") is not None):
            continue
        start = int(opening.get("start_seconds") or 0)
        length = int(opening.get("clip_preview_seconds") or 0)
        if (start in seen or start < tail_begin or start >= tail_end
            or not 60 <= length <= 3600 or start + length > min(tail_end, duration)):
            continue
        title = str(opening.get("title") or "").replace("\n", " ").replace('"', "'").strip()
        if not title or len(title) > 120:
            continue
        seen.add(start)
        extinf = (
            '#EXTINF:-1 group-title="KICK系VOD" '
            f'tvg-id="kick.gmcx.video-intro.{vod_id[:12]}.{start}" '
            f'tvg-logo="{LOGO}",'
            f'🎬 {title}（映像で冒頭確認・約58分試聴・終点未確定）'
        )
        url = f"{RESOLVER}{quote(vod_id, safe='')}&start={start}&duration={length}"
        entries.append((extinf, url))
    return entries
