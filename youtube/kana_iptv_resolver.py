#!/usr/bin/env python3
"""Independent Kana IPTV HLS resolver; does not modify browser Kana output."""
import datetime as dt
import json
import re
import subprocess
import urllib.request
from pathlib import Path

VIDEO = "DVL04eDdDIE"
OUT = Path("youtube/output/kana_iptv.m3u")
STATE = Path("youtube/state/kana_iptv_probe.json")
WATCH = "https://www.youtube.com/watch?v=" + VIDEO
CLIENTS = ("default", "web", "android", "web_safari")
def run(args, timeout=38):
    return subprocess.run(args, capture_output=True, text=True, timeout=timeout)
def candidate_urls(client):
    cmd = ["yt-dlp", "--no-playlist", "--no-warnings", "--socket-timeout", "8",
           "--retries", "0", "--extractor-args",
           "youtube:player_client=" + client, "-f",
           "best[protocol^=m3u8]/best[protocol*=m3u8]", "-g", WATCH]
    p = run(cmd)
    print("KANA_IPTV", client, "exit", p.returncode,
          "stderr", re.sub(r"https?://\\S+", "[URL]", p.stderr[-450:]))
    return [u for u in p.stdout.splitlines() if u.startswith("https://") and
            ("manifest.googlevideo.com/" in u or ".m3u8" in u)]
def valid(url):
    match = re.search(r"/expire/(\\d+)", url)
    if match and int(match.group(1)) < dt.datetime.now(dt.timezone.utc).timestamp() + 180:
        return False, "expiring"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            body = resp.read(8192).decode("utf-8", "replace")
            return resp.status == 200 and "#EXTM3U" in body, "http=" + str(resp.status)
    except Exception as exc:
        return False, type(exc).__name__ + ": " + str(exc)[:150]
def main():
    attempts = []
    chosen = None
    for client in CLIENTS:
        try:
            urls = candidate_urls(client)
            for url in urls:
                ok, reason = valid(url)
                attempts.append({"client": client, "valid": ok, "reason": reason})
                if ok:
                    chosen = url
                    break
        except (subprocess.TimeoutExpired, OSError) as exc:
            attempts.append({"client": client, "reason": type(exc).__name__})
        if chosen:
            break
    # Never retain an expired or unverified URL.
    OUT.parent.mkdir(parents=True, exist_ok=True)
    if chosen:
        OUT.write_text('#EXTM3U\n#EXTINF:-1 tvg-id="youtube.kana_tube_iptv" tvg-name="かなチューブ IPTV" group-title="今日の開催場",かなチューブ IPTV【LIVE】\n' + chosen + '\n')
    else:
        OUT.write_text("#EXTM3U\n")
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps({"video_id": VIDEO, "success": bool(chosen),
        "checked_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "attempts": attempts}, ensure_ascii=False, indent=2) + "\n")
    print("KANA_IPTV RESULT", "VERIFIED_MANIFEST" if chosen else "NO_VERIFIED_HLS")
if __name__ == "__main__":
    main()
