#!/usr/bin/env python3
"""Read-only HLS playlist sampler for HARUKA ABC/TVO; never modifies playback."""
import argparse
import datetime as dt
import hashlib
import collections
import json
import re
import time
import urllib.request
from urllib.parse import urljoin, urlparse

CHANNELS = {"ABC": "28", "TVO": "22"}
BASE = "http://118.69.27.222:9394"
HEADERS = {"User-Agent": "Mozilla/5.0 HarukaPlaylistDiagnostic/1.0"}
def fetch(url):
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=8) as response:
        return response.read(256000).decode("utf-8", "replace")

def analyze(name, raw, url):
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    urls = [line for line in lines if not line.startswith("#")]
    tags = [line.split(":", 1)[0] for line in lines if line.startswith("#EXT")]
    markers = [line[:140] for line in lines if re.search(r"(DATERANGE|DISCONTINUITY|CUE-OUT|CUE-IN|SCTE|AD-)", line, re.I)]
    hosts = sorted({urlparse(urljoin(url, item)).hostname for item in urls if urlparse(urljoin(url,item)).hostname})
    durations = [float(m.group(1)) for line in lines if (m := re.match(r"#EXTINF:([0-9.]+)", line))]
    segment_suffixes = collections.Counter(urlparse(item).path.rsplit(".", 1)[-1] for item in urls)
    sequence = next((line.partition(":")[2] for line in lines if line.startswith("#EXT-X-MEDIA-SEQUENCE:")), None)
    discontinuity_sequence = next((line.partition(":")[2] for line in lines if line.startswith("#EXT-X-DISCONTINUITY-SEQUENCE:")), None)
    # Segment fingerprints only: no media bytes or full stream URLs are logged.
    segment_ids = [hashlib.sha256(urljoin(url, item).encode()).hexdigest()[:12] for item in urls]
    return {"channel": name, "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "playlist_hash": hashlib.sha256(raw.encode()).hexdigest()[:16],
            "segment_count": len(urls), "tag_counts": {t: tags.count(t) for t in sorted(set(tags))},
            "markers": markers[:20], "hosts": hosts, "durations": durations,
            "segment_types": dict(segment_suffixes), "media_sequence": sequence,
            "discontinuity_sequence": discontinuity_sequence, "segment_ids": segment_ids}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--iterations", type=int, default=18)
    ap.add_argument("--interval", type=int, default=20)
    args = ap.parse_args()
    if not 1 <= args.iterations <= 90 or not 5 <= args.interval <= 120:
        ap.error("invalid sampler settings")
    previous = {}
    for index in range(args.iterations):
        for name, channel in CHANNELS.items():
            url = f"{BASE}/stream/{channel}.m3u8"
            try:
                manifest = fetch(url)
                info = analyze(name, manifest, url)
                # Follow only same host variant playlists, without fetching video segments.
                variants = [urljoin(url, line.strip()) for line in manifest.splitlines()
                            if line.strip() and not line.startswith("#") and ".m3u8" in line]
                if variants and urlparse(variants[0]).hostname == urlparse(url).hostname:
                    info["media_playlist"] = analyze(name, fetch(variants[0]), variants[0])
                current = json.dumps(info, ensure_ascii=False, sort_keys=True)
                if current != previous.get(name):
                    print(current, flush=True)
                    previous[name] = current
            except Exception as exc:
                print(json.dumps({"channel": name, "timestamp_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "error": str(exc)[:180]}), flush=True)
        if index < args.iterations - 1:
            time.sleep(args.interval)
if __name__ == "__main__":
    main()
