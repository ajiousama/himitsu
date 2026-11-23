#!/usr/bin/env python3
"""Read-only test: can ffmpeg decode sound from three GCH LQ master playlists?"""
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

FILES = {
    "EAST HQ": "gch_east_master.m3u8",
    "EAST LQ": "gch_east_LQ.m3u8",
    "WEST HQ": "gch_west_master.m3u8",
    "WEST LQ": "gch_west_LQ.m3u8",
    "LOCAL HQ": "gch_hokkaido_master.m3u8",
    "LOCAL LQ": "gch_hokkaido_LQ.m3u8",
}
def check_file(name, filename):
    content = Path(filename).read_text("utf-8-sig")
    uri = re.search(r'^#EXT-X-MEDIA:TYPE=AUDIO[^\n]*\bURI="([^"]+)"', content, re.M)
    stream = re.search(r'(?m)^#EXT-X-STREAM-INF:[^\n]+\n(https://[^\s]+)', content)
    if not uri or not stream:
        print(name + ": invalid playlist: audio group or video missing", flush=True)
        return
    audio, video = uri.group(1), stream.group(1)
    if any(urlparse(v).hostname != "variants.streaks.jp" for v in (audio, video)):
        print(name + ": invalid host", flush=True)
        return
    print(name + ": AUDIO=%s VIDEO=%s" % (
        re.search(r"manifest_[0-9_]+",audio).group(0),
        re.search(r"manifest_[0-9_]+",video).group(0)), flush=True)
    remote = "https://raw.githubusercontent.com/ajiousama/himitsu/main/" + filename
    probe = ["ffprobe", "-v", "error", "-rw_timeout", "15000000",
             "-show_entries", "stream=index,codec_type,codec_name,width,height",
             "-of", "json", filename]
    try:
        r = subprocess.run(probe, capture_output=True, text=True, timeout=25)
        if r.returncode:
            print(name + ": master decode FAIL (probe) " + re.sub(r"https?://[^\s]+", "[URL]", r.stderr).strip()[:450], flush=True)
        else:
            streams = json.loads(r.stdout).get("streams", [])
            print(name + ": master streams: " +
                  json.dumps(streams, ensure_ascii=False), flush=True)
    except Exception as exc:
        print(name + ": master probe error: "+type(exc).__name__, flush=True)
    command = ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "info",
               "-rw_timeout", "15000000", "-i", remote,
               "-map", "0:a:0", "-t", "10", "-af", "volumedetect",
               "-f", "null", "-"]
    try:
        r = subprocess.run(command, capture_output=True, text=True, timeout=35)
        text = r.stderr
        mean = re.search(r"mean_volume:\s*(\S+)\s*dB", text)
        peak = re.search(r"max_volume:\s*(\S+)\s*dB", text)
        if not r.returncode and mean and peak:
            print(name + ": master sample mean=%s dB peak=%s dB" %
                  (mean.group(1), peak.group(1)), flush=True)
        else:
            print(name + ": master audio sample unavailable / decode failed: " + re.sub(r"https?://[^\s]+", "[URL]", r.stderr).strip()[-400:], flush=True)
    except Exception as exc:
        print(name + ": master audio probe error: "+type(exc).__name__, flush=True)

def main():
    for name, filename in FILES.items():
        check_file(name, filename)
    print("READ-ONLY. Existing HQ, LQ, FreeWiFi and EPG files left unchanged.", flush=True)

if __name__ == "__main__":
    main()
