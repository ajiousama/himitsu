#!/usr/bin/env python3
"""Read-only diagnostic of GCH LOCAL WEB5 media and audio tracks.

Does not change playlists, guess manifest numbers or publish new stream URLs.
"""
import json
import os
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

FILES = {
    "LOCAL HQ": Path("gch_hokkaido_master.m3u8"),
    "LOCAL LQ": Path("gch_hokkaido_LQ.m3u8"),
}
ALLOWED_HOST = "variants.streaks.jp"
REPORT = []


def report(line):
    print(line, flush=True)
    REPORT.append(line)


def parse(path):
    lines = path.read_text(encoding="utf-8-sig").splitlines()
    audio = None
    video = None
    declared = None
    for index, line in enumerate(lines):
        if line.startswith("#EXT-X-MEDIA:") and "TYPE=AUDIO" in line:
            match = re.search(r'URI="([^"]+)"', line)
            if match:
                audio = match.group(1)
        if line.startswith("#EXT-X-STREAM-INF:"):
            match = re.search(r"\bBANDWIDTH=(\d+)", line)
            declared = int(match.group(1)) if match else None
            for candidate in lines[index + 1:]:
                if candidate.strip() and not candidate.startswith("#"):
                    video = candidate.strip()
                    break
    if not audio or not video:
        raise ValueError("master playlist is missing audio or video reference")
    for url in (audio, video):
        parsed = urlparse(url)
        if parsed.scheme != "https" or parsed.hostname != ALLOWED_HOST:
            raise ValueError("unexpected origin in media URL")
    return {"audio": audio, "video": video, "declared": declared}


def probe(url, expected_type):
    args = [
        "ffprobe", "-v", "error",
        "-rw_timeout", "12000000",
        "-analyzeduration", "3000000",
        "-probesize", "1000000",
        "-show_entries",
        "stream=codec_type,codec_name,width,height,avg_frame_rate,bit_rate",
        "-of", "json", url,
    ]
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=25)
        if result.returncode != 0:
            return {"status": "unverified (upstream inaccessible or media probe failed)"}
        streams = json.loads(result.stdout).get("streams") or []
    except (OSError, subprocess.TimeoutExpired, ValueError, json.JSONDecodeError):
        return {"status": "unverified (probe failed)"}
    matches = [s for s in streams if s.get("codec_type") == expected_type]
    if not matches:
        return {"status": "mismatch (expected track not detected)",
                "seen": sorted({s.get("codec_type", "?") for s in streams})}
    item = matches[0]
    desc = {"status": "detected", "codec": item.get("codec_name", "?")}
    if expected_type == "video":
        desc["resolution"] = "%sx%s" % (item.get("width", "?"), item.get("height", "?"))
        desc["fps"] = item.get("avg_frame_rate", "?")
        desc["bit_rate"] = item.get("bit_rate", "unknown")
    return desc


def check_audio_level(url, duration=12):
    """Sample actual audio; presence alone does not prove audible sound."""
    args = [
        "ffmpeg", "-hide_banner", "-nostdin", "-v", "info",
        "-rw_timeout", "12000000", "-i", url,
        "-map", "0:a:0", "-vn", "-t", str(duration),
        "-af", "volumedetect", "-f", "null", "-",
    ]
    try:
        res = subprocess.run(args, capture_output=True, text=True, timeout=35)
    except (OSError, subprocess.TimeoutExpired):
        return {"status": "unverified (ffmpeg failed or timed out)"}
    if res.returncode != 0:
        return {"status": "unverified (audio payload decode failed)"}
    mean = re.search(r"mean_volume:\s*([-\w.]+)\s*dB", res.stderr)
    maximum = re.search(r"max_volume:\s*([-\w.]+)\s*dB", res.stderr)
    if not mean or not maximum:
        return {"status": "unverified (no volume stats)"}
    maximum_value = maximum.group(1)
    if maximum_value == "-inf":
        status = "decoded DIGITAL SILENCE during sample"
    elif float(maximum_value) > -60:
        status = "decoded NON-SILENT audio during sample"
    else:
        status = "very quiet audio; audibility uncertain"
    return {"status": status, "mean_dB": mean.group(1),
            "max_dB": maximum_value, "sample_seconds": duration}


def main():
    report("GCH LOCAL WEB5 / read-only HLS audit")
    data = {}
    for name, path in FILES.items():
        data[name] = parse(path)
        report("%s: declared BANDWIDTH=%s" % (name, data[name]["declared"]))
    if data["LOCAL HQ"]["video"] == data["LOCAL LQ"]["video"]:
        report("WARNING: HQ and LQ use the SAME VIDEO URL; no distinct quality is selected.")
    if data["LOCAL HQ"]["audio"] == data["LOCAL LQ"]["audio"]:
        report("NOTE: HQ and LQ share the same audio URL.")
    unique = {}
    for name, spec in data.items():
        for kind in ("video", "audio"):
            key = (spec[kind], kind)
            if key not in unique:
                unique[key] = probe(spec[kind], kind)
            report("%s %s: %s" % (name, kind, json.dumps(unique[key], ensure_ascii=False)))
    if os.environ.get("GCH_LOCAL_AUDIO_LEVEL") == "1":
        result = check_audio_level(data["LOCAL HQ"]["audio"])
        report("LOCAL HQ sampled audio: " + json.dumps(result, ensure_ascii=False))
    if os.environ.get("GCH_LOCAL_AUDIO_ALTERNATES") == "1":
        report("Read-only audio candidate check; no playlist switching.")
        seed = data["LOCAL HQ"]["audio"]
        for variant in ("3", "4", "5", "6", "7", "8", "7_0", "8_0"):
            if not re.search(r"/manifest_\d+(?:_\d+)?\.m3u8\?", seed):
                report("Audio candidate check skipped: source format unknown.")
                break
            candidate = re.sub(
                r"/manifest_\d+(?:_\d+)?\.m3u8(?=\?)",
                "/manifest_%s.m3u8" % variant,
                seed, count=1
            )
            desc = probe(candidate, "audio")
            if desc.get("status") == "detected":
                desc["volume"] = check_audio_level(candidate, duration=8)
            report("LOCAL candidate manifest_%s AUDIO: %s" % (
                variant, json.dumps(desc, ensure_ascii=False)))
    if os.environ.get("GCH_LOCAL_PROBE_ALTERNATES") == "1":
        report("Read-only check of known STREAKS variant slots (3-8); NO automatic switching.")
        seed = data["LOCAL HQ"]["video"]
        if not re.search(r"/manifest_\d+\.m3u8\?", seed):
            report("Variant check skipped: video path format is not recognised.")
        else:
            for number in range(3, 9):
                candidate = re.sub(
                    r"/manifest_\d+\.m3u8(?=\?)",
                    "/manifest_%s.m3u8" % number,
                    seed, count=1
                )
                result = probe(candidate, "video")
                report("LOCAL candidate manifest_%s VIDEO: %s" % (
                    number, json.dumps(result, ensure_ascii=False)))
    report("No URLs, credentials or media content are printed. No playlist changes made.")
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write("### GCH LOCAL WEB5 diagnostic (read-only)\n\n")
            f.write("".join("- " + line + "\n" for line in REPORT))


if __name__ == "__main__":
    main()
