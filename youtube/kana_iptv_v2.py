#!/usr/bin/env python3
# trigger: v2-first-live
import json, os, re, subprocess, sys, time, urllib.request
from pathlib import Path

VIDEO_ID = os.environ.get("KANA_VIDEO_ID", "DVL04eDdDIE").strip()
WATCH = f"https://www.youtube.com/watch?v={VIDEO_ID}"
OUT = Path("youtube/output/kana_iptv.m3u")
STATE = Path("youtube/state/kana_iptv_v2.json")

def run(args, timeout=75):
    p = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    return p.returncode, p.stdout, p.stderr

def add_candidate(out, url, source):
    if not isinstance(url, str):
        return
    url = url.strip()
    if not url.startswith("http"):
        return
    if ("manifest.googlevideo.com/" in url or ".m3u8" in url) and url not in {x[0] for x in out}:
        out.append((url, source))

def candidates_from_json(data, source):
    out = []
    for key in ("hls_manifest_url", "hlsManifestUrl", "url"):
        add_candidate(out, data.get(key), f"{source}:{key}")
    for f in data.get("formats") or []:
        proto = str(f.get("protocol") or "").lower()
        url = f.get("url")
        if "m3u8" in proto or (isinstance(url, str) and ("manifest.googlevideo.com/" in url or ".m3u8" in url)):
            add_candidate(out, url, f"{source}:format:{f.get('format_id')}")
    return out

def probe(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/vnd.apple.mpegurl,application/x-mpegURL,text/plain,*/*",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = r.read(65536)
            text = body.decode("utf-8", "replace")
            ok = r.status == 200 and "#EXTM3U" in text[:4096]
            return ok, r.status, text[:500]
    except Exception as e:
        return False, None, repr(e)

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)
    STATE.parent.mkdir(parents=True, exist_ok=True)

    client_sets = [
        "web_creator,web_safari,web",
        "android_vr,web_safari,web",
        "mweb,web_safari,web",
    ]
    found = []
    errors = []

    for clients in client_sets:
        cmd = [
            "yt-dlp", "--no-playlist", "--dump-single-json",
            "--ignore-no-formats-error",
            "--extractor-args", f"youtube:player_client={clients}",
            WATCH,
        ]
        rc, stdout, stderr = run(cmd)
        errors.append({"clients": clients, "rc": rc, "stderr_tail": stderr[-1200:]})
        if stdout.strip():
            try:
                data = json.loads(stdout)
                found.extend(candidates_from_json(data, clients))
            except Exception as e:
                errors.append({"clients": clients, "json_error": repr(e)})

    # Independent direct URL mode. No live-status filter: the whole point of
    # this v2 resolver is to work even when YouTube metadata still says upcoming.
    selectors = [
        "best[protocol^=m3u8]/best[protocol*=m3u8]/best",
        "bestvideo[protocol*=m3u8]+bestaudio[protocol*=m3u8]/best[protocol*=m3u8]/best",
    ]
    for clients in client_sets:
        for sel in selectors:
            rc, stdout, stderr = run([
                "yt-dlp", "--no-playlist",
                "--extractor-args", f"youtube:player_client={clients}",
                "-f", sel, "-g", WATCH,
            ])
            errors.append({"clients": clients, "selector": sel, "rc": rc, "stderr_tail": stderr[-900:]})
            for line in stdout.splitlines():
                add_candidate(found, line, f"-g:{clients}:{sel}")

    # Prefer media playlists over master/variant when both exist.
    found = list(dict.fromkeys(found))
    found.sort(key=lambda x: (0 if "/hls_playlist/" in x[0] else 1, 0 if "manifest.googlevideo.com/" in x[0] else 1))

    winner = None
    probes = []
    for url, source in found:
        ok, status, detail = probe(url)
        probes.append({"source": source, "status": status, "ok": ok, "url_prefix": url[:180], "detail": detail[:300]})
        if ok:
            winner = (url, source)
            break

    state = {
        "version": 2,
        "video_id": VIDEO_ID,
        "watch_url": WATCH,
        "checked_epoch": int(time.time()),
        "candidate_count": len(found),
        "ok": bool(winner),
        "winner_source": winner[1] if winner else None,
        "probes": probes,
        "errors": errors,
    }

    if winner:
        url = winner[0]
        OUT.write_text(
            '#EXTM3U\n'
            '#EXTINF:-1 tvg-id="youtube.kana_tube_iptv" tvg-name="かなチューブ IPTV" '
            'group-title="今日の開催場",かなチューブ IPTV【LIVE】\n'
            + url + '\n',
            encoding="utf-8",
        )
        state["play_url"] = url
        m = re.search(r"/expire/(\d+)", url)
        state["expire_epoch"] = int(m.group(1)) if m else None
        print("KANA_IPTV_V2_OK", source if (source := winner[1]) else "")
    else:
        # Do not overwrite a previously working playlist with a watch URL.
        state["play_url"] = None
        print("KANA_IPTV_V2_NO_VALID_HLS", file=sys.stderr)

    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0 if winner else 2

if __name__ == "__main__":
    raise SystemExit(main())
