#!/usr/bin/env python3
"""Read-only GCCX opening-audio validation with independent negative controls.

The first two KICK recordings show a visible GCCX opening near their start.
The latter two start during a programme. Cross-source audio matches may
suggest a reusable intro template, but are NEVER enough to certify a
particular episode's exact start or identity.

No code path writes VOD5, FreeWiFi, or any published chapter file.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from gmcx_auto_cut_audio import read_audio, fingerprint
from gmcx_title_bgm_probe import match_pair
from kick_gmcx_chapters import _lowest_hls_variant

JST = timezone(timedelta(hours=9))
# Source classification is based on independently reviewed contact sheets.
SOURCES = {
    "positive_2004_intro": "df1386fd",
    "positive_2006_intro": "de35f5fe",
    "negative_2006_mid_show": "5847ae05",
    "negative_2026_mid_show": "f622346e",
}
AUDIO_SECONDS = 105


def judge(comparisons: dict, available: set[str]) -> dict:
    if set(SOURCES) - available:
        return {
            "status": "insufficient_sources",
            "missing": sorted(set(SOURCES) - available),
            "usable_for_publication": False,
        }
    positive = comparisons.get("positive_2004_intro|positive_2006_intro", {}).get("summary", {})
    negative_keys = [
        f"{positive_name}|{negative_name}"
        for positive_name in ("positive_2004_intro", "positive_2006_intro")
        for negative_name in ("negative_2006_mid_show", "negative_2026_mid_show")
    ]
    negative_summaries = [
        comparisons.get(key, {}).get("summary", {}) for key in negative_keys
    ]
    positive_agreement = positive.get("status") == "common_audio_detected"
    negative_agreement = any(
        row.get("status") == "common_audio_detected" for row in negative_summaries
    )
    all_negative_checked = all(
        row.get("status") not in (None, "source_unavailable") and bool(row.get("status"))
        for row in negative_summaries
    )
    if positive_agreement and all_negative_checked and not negative_agreement:
        status = "candidate_intro_fingerprint_needs_video_onset_verification"
    elif positive_agreement and negative_agreement:
        status = "matched_audio_is_not_specific_to_opening"
    else:
        status = "no_independently_verified_common_intro"
    return {
        "status": status,
        "positive_match": positive_agreement,
        "negative_control_matches": negative_agreement,
        "negative_controls_complete": all_negative_checked,
        "usable_for_publication": False,
    }


def main() -> int:
    playlist = json.loads(Path("kick_replay.json").read_text(encoding="utf-8"))
    vods = playlist.get("vods", [])
    report = {
        "generated_at": datetime.now(JST).isoformat(),
        "mode": "read_only_two_visual_positives_vs_two_mid_show_negative_controls",
        "source_status": [],
        "comparisons": {},
        "production_modified": False,
    }
    fp = {}
    for name, prefix in SOURCES.items():
        row = {"name": name, "vod_prefix": prefix}
        matches = [
            x for x in vods if str(x.get("vod_id") or "").startswith(prefix)
            and str(x.get("tvg_id") or "").startswith("kick.gccx")
        ]
        source = matches[0] if len(matches) == 1 else None
        if not source or source.get("playable") is not True or not source.get("source_url"):
            row["status"] = "source_unavailable"
        else:
            row["vod_id"] = source["vod_id"]
            try:
                url = _lowest_hls_variant(str(source["source_url"]))
                fp[name] = fingerprint(read_audio(url, 0, AUDIO_SECONDS))
                row["status"] = "decoded"
                row["spectral_frames"] = int(len(fp[name]))
            except Exception as exc:
                row["status"] = "audio_error"
                row["error"] = str(exc)[:250]
        report["source_status"].append(row)
        print("GCCX_INTRO_REFERENCE " + json.dumps(row, ensure_ascii=False), flush=True)

    pairs = [
        ("positive_2004_intro", "positive_2006_intro"),
        ("positive_2004_intro", "negative_2006_mid_show"),
        ("positive_2004_intro", "negative_2026_mid_show"),
        ("positive_2006_intro", "negative_2006_mid_show"),
        ("positive_2006_intro", "negative_2026_mid_show"),
    ]
    for left, right in pairs:
        key = f"{left}|{right}"
        if left not in fp or right not in fp:
            report["comparisons"][key] = {"summary": {"status": "source_unavailable"}}
        else:
            try:
                report["comparisons"][key] = match_pair(fp[left], fp[right])
            except Exception as exc:
                report["comparisons"][key] = {
                    "summary": {"status": "comparison_error", "error": str(exc)[:250]}
                }
        print("GCCX_INTRO_COMPARISON " + json.dumps({
            "pair": key, "summary": report["comparisons"][key]["summary"],
        }, ensure_ascii=False), flush=True)

    report["conclusion"] = judge(report["comparisons"], set(fp))
    Path("gmcx_intro_bgm_controls.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print("GCCX_INTRO_CONCLUSION " + json.dumps(
        report["conclusion"], ensure_ascii=False
    ), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
