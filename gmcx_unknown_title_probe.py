#!/usr/bin/env python3
"""Bounded, resumable video OCR title detection for unknown GCCX KICK chapters.

Only video-observed OCR matches against a known title are published as tentative.
Never relabel manually verified cuts, guess episode order, or treat 58-minute
navigation positions as verified episode boundaries.
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import subprocess
import tempfile
import time
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from gmcx_long_nav import build_time_navigation_entries

REPLAY = Path("kick_replay.json")
CHAPTERS = Path("kick_gmcx_chapters.json")
TITLES = Path("gmcx_episode_titles.json")
REPORT = Path("gmcx_unknown_title_review.json")
SAMPLES = (65, 155, 280)
RETRY_SECONDS = 3 * 3600


def normalized(value: str) -> str:
    value = unicodedata.normalize("NFKC", str(value)).lower()
    return re.sub(r"[^a-z0-9ぁ-んァ-ヶ一-龯]", "", value)


def title_keys(title: str) -> set[str]:
    parts = [title]
    parts += re.split(r"[（(「『～〜/:：]", title)[:2]
    parts += [x for x in title.split() if len(normalized(x)) >= 4]
    keys = {normalized(x) for x in parts}
    return {x for x in keys if len(x) >= 4}


def identify_title(text: str, titles: dict) -> dict | None:
    lines = [normalized(line) for line in text.splitlines()]
    lines = [line for line in lines if len(line) >= 4]
    full = normalized(text)
    if not lines or not full:
        return None
    scores = []
    for number, title in titles.items():
        keys = title_keys(title)
        if not keys:
            continue
        best = 0.0
        for key in keys:
            if key in full:
                best = max(best, 1.0 if len(key) >= 6 else 0.92)
            elif len(key) >= 6:
                similarity = max(
                    (difflib.SequenceMatcher(None, key, line[:max(len(key) + 8, 24)]).ratio()
                     for line in lines), default=0.0
                )
                if similarity >= 0.90:
                    best = max(best, similarity * 0.94)
        if best >= 0.84:
            scores.append((best, int(number), title))
    if not scores:
        return None
    scores.sort(key=lambda row: (-row[0], row[1]))
    top = scores[0]
    other = scores[1][0] if len(scores) > 1 else 0.0
    if top[0] - other < 0.08:
        return None
    return {"episode": top[1], "title": top[2],
            "confidence": "ocr_title_candidate", "score": round(top[0], 3)}


def capture_text(url: str, second: int, tmp: Path, index: int) -> tuple[str, str]:
    image = tmp / ("sample_" + str(index) + ".png")
    command = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-rw_timeout", "9000000", "-ss", str(second),
        "-i", url, "-frames:v", "1", "-y", str(image),
    ]
    try:
        proc = subprocess.run(command, capture_output=True, timeout=20, check=False)
        if proc.returncode != 0 or not image.is_file():
            return "", "ffmpeg_failed"
        ocr = subprocess.run(
            ["tesseract", str(image), "stdout", "-l", "jpn+eng", "--psm", "11"],
            capture_output=True, timeout=20, check=False,
        )
        if ocr.returncode:
            return "", "ocr_failed"
        return ocr.stdout.decode("utf-8", "replace"), "ocr_completed"
    except FileNotFoundError as exc:
        return "", "missing_program:" + str(exc.filename)
    except subprocess.TimeoutExpired:
        return "", "timeout"


def eligible_chunks() -> list[tuple[str, int, int, str]]:
    replay = json.loads(REPLAY.read_text(encoding="utf-8"))
    by_id = {
        str(v.get("vod_id")): v for v in replay.get("vods", [])
        if isinstance(v, dict) and v.get("vod_id")
        and v.get("playable") is True
        and v.get("ready_for_publish") is True
        and str(v.get("tvg_id") or "").startswith("kick.gccx")
    }
    entries = build_time_navigation_entries(REPLAY, CHAPTERS)
    chunks = []
    for _label, url in entries:
        query = parse_qs(urlsplit(url).query)
        vod_id = query.get("vod", [""])[0]
        vod = by_id.get(vod_id)
        if not vod or not vod.get("source_url"):
            continue
        try:
            start = int(query.get("start", [""])[0])
            length = int(query.get("duration", [""])[0])
        except (TypeError, ValueError):
            continue
        if start < 0 or length < 300:
            continue
        chunks.append((vod_id, start, length, str(vod["source_url"])))
    # Alternate across recordings so a long 48-hour VOD cannot starve
    # every other unidentified archive inside the Actions time budget.
    order = {str(v.get("vod_id")): str(v.get("created_at") or "")
             for v in by_id.values()}
    grouped: dict[str, list[tuple[str, int, int, str]]] = {}
    for item in chunks:
        grouped.setdefault(item[0], []).append(item)
    vod_order = sorted(grouped, key=lambda key: order.get(key, ""), reverse=True)
    for group in grouped.values():
        group.sort(key=lambda item: item[1])
    balanced = []
    while any(grouped.values()):
        for vod_id in vod_order:
            if grouped[vod_id]:
                balanced.append(grouped[vod_id].pop(0))
    return balanced


def run_probe(max_new: int, budget_seconds: int) -> dict:
    report = {"schema_version": 1, "vods": {}}
    if REPORT.exists():
        try:
            report = json.loads(REPORT.read_text(encoding="utf-8"))
            if report.get("schema_version") != 1:
                raise ValueError("Unsupported prior OCR report")
        except (OSError, ValueError):
            report = {"schema_version": 1, "vods": {}}
    report.setdefault("vods", {})
    titles = json.loads(TITLES.read_text(encoding="utf-8"))
    now = int(time.time())
    deadline = time.monotonic() + max(30, budget_seconds)
    processed = 0
    matches = 0
    for vod_id, start, length, source in eligible_chunks():
        if processed >= max_new or time.monotonic() >= deadline - 25:
            break
        vod = report["vods"].setdefault(vod_id, {"source_url": source, "rows": {}})
        if vod.get("source_url") != source:
            vod["source_url"] = source
            vod["rows"] = {}
        rows = vod.setdefault("rows", {})
        prior = rows.get(str(start), {})
        if now - int(prior.get("attempted_at") or 0) < RETRY_SECONDS:
            continue
        texts = []
        samples = []
        with tempfile.TemporaryDirectory(prefix="gmcx_ocr_") as folder:
            for i, delta in enumerate(SAMPLES):
                if time.monotonic() >= deadline - 25:
                    break
                second = start + min(delta, length - 10)
                found, state = capture_text(source, second, Path(folder), i)
                if state in {"ffmpeg_failed", "timeout"}:
                    # The source's absolute seek can fail while the short
                    # resolver clip stays playable. Probe both paths.
                    resolver_url = (
                        "https://kick-resolver-production.up.railway.app/kick"
                        f"?vod={vod_id}&start={second}&duration=8"
                    )
                    recovered, recovered_state = capture_text(
                        resolver_url, 1, Path(folder), i + 10
                    )
                    if recovered_state == "ocr_completed":
                        found, state = recovered, "ocr_completed_via_resolver"
                    else:
                        state = state + ";resolver_" + recovered_state
                samples.append({"offset": second, "status": state,
                                "ocr_excerpt": found[:400]})
                if found.strip():
                    texts.append(found)
                elif "resolver_" in state:
                    # Skip futile extra attempts while this archive is blocked.
                    break
        best = identify_title("\n".join(texts), titles) if texts else None
        row = {"start_seconds": start, "attempted_at": now,
               "source_url": source, "status": "ocr_match" if best else "no_title_match",
               "samples": samples}
        if best:
            row["candidate"] = best
            matches += 1
        rows[str(start)] = row
        processed += 1
        print("OCR", vod_id[:8], start, row["status"],
              best["title"] if best else "", flush=True)
        # Write incrementally so interrupted jobs can still publish evidence.
        REPORT.write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    report["last_scan_utc"] = datetime.now(timezone.utc).isoformat()
    report["last_scan_count"] = processed
    report["last_scan_matches"] = matches
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                      encoding="utf-8")
    print("OCR scan complete:", processed, "chapters examined,", matches,
          "new title candidate(s)", flush=True)
    return report


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="scan all current unknown VODs")
    ap.add_argument("--max-new", type=int, default=12)
    ap.add_argument("--budget-seconds", type=int, default=300)
    args = ap.parse_args()
    if not args.all:
        ap.error("--all is required; video probe is deliberately bounded")
    run_probe(max(1, min(args.max_new, 40)), max(30, min(args.budget_seconds, 1200)))


if __name__ == "__main__":
    main()
