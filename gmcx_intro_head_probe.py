#!/usr/bin/env python3
"""Capture small opening contact sheets to look for an actual GCCX title sequence.

This is a read-only diagnostic. Frames sampled every four seconds are suitable
for visual review, not sufficient for automatically certifying an episode start.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from kick_gmcx_chapters import _lowest_hls_variant

PREFIXES = ("df1386fd", "5847ae05", "f622346e", "de35f5fe")
OUT_DIR = Path("gmcx_intro_head_frames")


def capture(source: dict, output: Path) -> tuple[bool, str]:
    url = _lowest_hls_variant(str(source["source_url"]))
    # 32 frames covering 0–124 sec of this independent KICK recording,
    # sequentially displayed left-to-right, top-to-bottom (8x4).
    vf = "fps=1/4,scale=240:135:flags=area,tile=8x4:padding=3:margin=3"
    args = [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
        "-rw_timeout", "15000000",
        "-ss", "0", "-i", url, "-t", "128", "-an",
        "-vf", vf, "-frames:v", "1", "-q:v", "5", "-y", str(output),
    ]
    try:
        result = subprocess.run(
            args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=100, check=False
        )
        if result.returncode != 0 or not output.is_file():
            return False, result.stderr.decode("utf-8", "replace")[-220:]
        return True, f"bytes={output.stat().st_size}"
    except (OSError, subprocess.TimeoutExpired) as exc:
        return False, str(exc)[:220]


def main() -> int:
    OUT_DIR.mkdir(exist_ok=True)
    replay = json.loads(Path("kick_replay.json").read_text(encoding="utf-8"))
    rows = []
    for prefix in PREFIXES:
        matches = [
            item for item in replay.get("vods", [])
            if str(item.get("vod_id") or "").startswith(prefix)
            and str(item.get("tvg_id") or "").startswith("kick.gccx")
        ]
        item = matches[0] if matches else {}
        row = {"prefix": prefix, "vod_id": item.get("vod_id")}
        if not item.get("playable") or not item.get("source_url"):
            row["status"] = "not_available"
        else:
            output = OUT_DIR / f"head_{prefix}.jpg"
            ok, detail = capture(item, output)
            row.update({"status": "captured" if ok else "capture_failed",
                        "detail": detail, "file": str(output)})
        rows.append(row)
        print("GCCX_HEAD_REVIEW "+json.dumps(row, ensure_ascii=False), flush=True)
    (OUT_DIR / "index.json").write_text(
        json.dumps({"note": "visual sample only; no verified episode anchors",
                    "rows": rows}, ensure_ascii=False, indent=2)+"\n",
        encoding="utf-8"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
