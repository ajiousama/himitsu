#!/usr/bin/env python3
"""Review-only OCR of unknown GCCX VODs. Never modifies published playlists."""
import argparse
import json
import subprocess
from pathlib import Path

def run(cmd, timeout):
    return subprocess.run(cmd, capture_output=True, timeout=timeout, check=False)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vod", required=True)
    ap.add_argument("--max-chapters", type=int, default=4)
    ap.add_argument("--output", default="gmcx_unknown_title_review")
    args = ap.parse_args()
    catalog = json.loads(Path("kick_replay.json").read_text(encoding="utf-8"))
    vod = next((v for v in catalog["vods"] if v.get("vod_id") == args.vod and
                str(v.get("tvg_id", "")).startswith("kick.gccx")), None)
    if not vod or not vod.get("source_url") or not int(vod.get("duration_seconds") or 0):
        ap.error("No matching playable GCCX recording")
    out = Path(args.output) / args.vod
    out.mkdir(parents=True, exist_ok=True)
    duration = int(vod["duration_seconds"])
    rows = []
    for start in list(range(0, duration, 3480))[:max(0, args.max_chapters)]:
        samples = []
        for delta in (0, 10, 20):
            second = start + delta
            image = out / f"{second:07d}.png"
            try:
                ff = run(["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                          "-rw_timeout", "12000000", "-ss", str(second), "-i",
                          vod["source_url"], "-frames:v", "1", "-y", str(image)], 40)
                if ff.returncode or not image.exists():
                    samples.append({"second": second, "status": "frame_unavailable"})
                    continue
                ocr = run(["tesseract", str(image), "stdout", "-l", "jpn+eng"], 30)
                samples.append({"second": second, "status": "ocr_candidate",
                                "text": ocr.stdout.decode("utf-8", "replace")[:800],
                                "image": str(image)})
            except (OSError, subprocess.TimeoutExpired):
                samples.append({"second": second, "status": "probe_failed"})
        rows.append({"approximate_start": start, "samples": samples})
    report = {"vod_id": args.vod, "status": "review_only",
              "note": "58-minute markers are not verified episode boundaries; OCR is not proof of episode title.",
              "rows": rows}
    (out / "review.json").write_text(json.dumps(report, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print("Review saved:", out / "review.json")

if __name__ == "__main__":
    main()
