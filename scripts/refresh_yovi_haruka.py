#!/usr/bin/env python3
"""HARUKA yovi-only trial: API host chasing with advancing-HLS + TS validation.

Never edits FreeWiFi, TV, Rakuten, or any non-managed yovi channel.
A missing HARUKA_AU may bootstrap the previously tested IP once; subsequent
automatic host chasing needs the HARUKA_AU GitHub Actions secret.
HTTP 200 + TS alone can be a frozen 28-second clip. Check HLS progression.\nProgression still does not prove the programme matches today's broadcast.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

PLAYLIST = Path("yovi")
API = "http://app.harukashop.site:3008/api/news/get-link"
BOOTSTRAP_BASE = "http://14.241.72.93:9394"  # initial manual test only
BEGIN = "# === YOVI_HARUKA_TRIAL_BEGIN ==="
END = "# === YOVI_HARUKA_TRIAL_END ==="
PAYLOAD = {"os": 1, "appId": 7, "deviceId": 602539, "newsId": 12}
# Confirmed HLS progression and TS fetch: 17 trial channels on 2026-11-23/26
# plus BS日テレ and WOWOWライブ・シネマ on 2026-11-26.
CHANNELS = (
    (4, "日本テレビ", "日本テレビ_jp", "地上波"),
    (5, "TBS", "TBS_jp", "地上波"),
    (7, "テレビ朝日", "テレビ朝日_jp", "地上波"),
    (8, "テレビ東京", "テレ東_jp", "地上波"),
    (12, "フジテレビ", "フジテレビ_jp", "地上波"),
    (17, "TOKYO MX1", "TOKYO・MX_jp", "地上波"),
    (18, "MBS毎日放送", "毎日テレビ_jp", "地上波"),
    (20, "関西テレビ", "関西テレビ_jp", "地上波"),
    (21, "読売テレビ", "読売テレビ_jp", "地上波"),
    (22, "テレビ大阪", "テレビ大阪_jp", "地上波"),
    (28, "ABCテレビ", "ABCテレビ_jp", "地上波"),
    (116, "KBS京都", "KBS京都_jp", "地上波"),
    (44, "BS日テレ", "BS日テレ_jp", "BS"),
    (35, "BS朝日", "BS朝日_jp", "BS"),
    (36, "BS-TBS", "BS-TBS_jp", "BS"),
    (37, "BSテレ東", "BSテレ東_jp", "BS"),
    (38, "BSフジ", "BSフジ_jp", "BS"),
    (39, "WOWOWプライム", "WOWOWプライム_jp", "BS"),
    (40, "WOWOWライブ", "WOWOWライブ_jp", "BS"),
    (41, "WOWOWシネマ", "WOWOWシネマ_jp", "BS"),
)
OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
HEADERS = {"User-Agent": "VLC/3.0.24", "Accept": "application/vnd.apple.mpegurl,*/*"}
STREAM = re.compile(r"^http://[A-Za-z0-9.:-]+:9394/stream/(\d+)\.m3u8$")
ALL_IDS = {entry[0] for entry in CHANNELS}


def fetch_current_base() -> str:
    auth = os.environ.get("HARUKA_AU", "")
    if not auth:
        raise RuntimeError("HARUKA_AU secret is not configured")
    request = urllib.request.Request(
        API, data=json.dumps(PAYLOAD).encode("utf-8"),
        headers={"au": auth, "content-type": "application/json; charset=UTF-8",
                 "User-Agent": "Dart/3.12 (dart:io)"},
        method="POST",
    )
    with OPENER.open(request, timeout=12) as response:
        body = json.load(response)
    if body.get("status") != 200:
        raise ValueError("HARUKA API did not return success status")
    link = body.get("data", {}).get("link")
    if not isinstance(link, str):
        raise ValueError("HARUKA API did not include data.link")
    p = urllib.parse.urlsplit(link)
    if p.scheme != "http" or not p.hostname or p.port != 9394 or p.username or p.password or p.path not in ("", "/") or p.query or p.fragment:
        raise ValueError("Unexpected HARUKA API link format")
    return "http://" + p.netloc


def stream_url(base: str, channel_id: int) -> str:
    return base + "/stream/" + str(channel_id) + ".m3u8"


def manifest_snapshot(channel_id: int, base: str) -> tuple[int, str] | None:
    """Fetch a snapshot; static 28-second HLS clips must NOT count as live."""
    url = stream_url(base, channel_id)
    try:
        headers = {**HEADERS, "Cache-Control": "no-cache", "Pragma": "no-cache"}
        with OPENER.open(urllib.request.Request(url, headers=headers), timeout=6) as response:
            if response.status != 200:
                return None
            body = response.read(16000).decode("utf-8", errors="replace")
        if not body.startswith("#EXTM3U") or "#EXT-X-ENDLIST" in body:
            return None
        sequence = re.search(r"(?m)^#EXT-X-MEDIA-SEQUENCE:(\d+)\s*$", body)
        if not sequence or "#EXT-X-TARGETDURATION:" not in body:
            return None
        segments = [line.strip() for line in body.splitlines()
                    if line.strip() and not line.strip().startswith("#")]
        if not segments:
            return None
        last = urllib.parse.urljoin(url, segments[-1])
        parts = urllib.parse.urlsplit(last)
        if parts.scheme != "http" or parts.netloc != urllib.parse.urlsplit(url).netloc:
            return None
        return int(sequence.group(1)), last
    except (ValueError, OSError, urllib.error.URLError):
        return None


def has_advanced(previous: tuple[int, str] | None,
                 current: tuple[int, str] | None) -> bool:
    """Require increasing HLS media sequence AND a new segment URI."""
    return bool(previous and current and current[0] > previous[0]
                and current[1] != previous[1])


def probe_latest_segment(snapshot: tuple[int, str] | None) -> bool:
    if snapshot is None:
        return False
    try:
        request = urllib.request.Request(
            snapshot[1], headers={**HEADERS, "Range": "bytes=0-4095"}
        )
        with OPENER.open(request, timeout=7) as response:
            if response.status not in (200, 206):
                return False
            data = response.read(4096)
        return len(data) >= 377 and data[0] == 0x47 and data[188] == 0x47
    except (ValueError, OSError, urllib.error.URLError):
        return False

def existing_entries(text: str) -> dict[int, str]:
    if BEGIN not in text and END not in text:
        return {}
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        raise ValueError("Invalid yovi HARUKA trial block markers")
    body = text.split(BEGIN, 1)[1].split(END, 1)[0]
    lines = body.splitlines()
    result: dict[int, str] = {}
    for i, line in enumerate(lines):
        if not line.startswith("#EXTINF:"):
            continue
        if i + 1 >= len(lines):
            raise ValueError("Truncated HARUKA entry")
        url = lines[i + 1].strip()
        m = STREAM.fullmatch(url)
        if not m or int(m.group(1)) not in ALL_IDS:
            raise ValueError("Unexpected HARUKA trial URL")
        channel_id = int(m.group(1))
        if channel_id in result:
            raise ValueError("Duplicate HARUKA trial channel")
        result[channel_id] = url
    return result


def logos_from_existing(text: str) -> dict[str, str]:
    logos: dict[str, str] = {}
    for line in text.splitlines():
        if not line.startswith("#EXTINF:") or "HARUKA試験" in line:
            continue
        id_match = re.search(r'tvg-id="([^"]+)"', line)
        logo_match = re.search(r'tvg-logo="([^"]+)"', line)
        if id_match and logo_match and id_match.group(1) not in logos:
            logos[id_match.group(1)] = logo_match.group(1)
    return logos


def update_yovi(original: str, base: str, good_ids: set[int]) -> tuple[str, int]:
    if not original.startswith("#EXTM3U"):
        raise ValueError("yovi is not M3U")
    old_entries = existing_entries(original)
    logos = logos_from_existing(original)
    rows = [
        BEGIN,
        "# HARUKA automatic host follow (yovi trial only). LIVE freshness is NOT verified.",
        "# This block is owned by scripts/refresh_yovi_haruka.py; do not edit manually.",
    ]
    kept = 0
    for channel_id, name, tvg_id, group in CHANNELS:
        if channel_id in good_ids:
            url = stream_url(base, channel_id)
        elif channel_id in old_entries:
            url = old_entries[channel_id]  # preserve last passing base
            kept += 1
        else:
            continue  # do not publish a newly failing stream
        logo = logos.get(tvg_id)
        attrs = ' tvg-id="' + tvg_id + '"'
        if logo:
            attrs += ' tvg-logo="' + logo + '"'
        attrs += ' group-title="HARUKA試験 ' + group + '"'
        rows += ["#EXTINF:-1" + attrs + ",[HARUKA試験・LIVE未判定] " + name, url, ""]
    rows.append(END)
    block = "\n".join(rows) + "\n"
    if BEGIN in original:
        pattern = re.compile(r"^" + re.escape(BEGIN) + r"\r?\n.*?^" + re.escape(END) + r"(?:\r?\n)?", re.M | re.S)
        updated, count = pattern.subn(lambda _: block, original)
        if count != 1:
            raise ValueError("Failed to replace managed HARUKA block")
    else:
        updated = original.rstrip("\n") + "\n\n" + block
    return updated, kept


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    original = PLAYLIST.read_text(encoding="utf-8-sig")
    old = existing_entries(original)
    try:
        base = fetch_current_base()
        source = "HARUKA API"
    except (ValueError, OSError, RuntimeError, urllib.error.URLError) as exc:
        if old:
            print("HARUKA lookup failed; preserving yovi trial block: " + type(exc).__name__)
            return
        if "HARUKA_AU" in os.environ and os.environ["HARUKA_AU"]:
            print("HARUKA API failed; refusing initial bootstrap")
            return
        base = BOOTSTRAP_BASE
        source = "previously tested bootstrap IP; API chase requires HARUKA_AU secret"
    # A frozen stream can return HTTP 200 and valid 28-second MPEG-TS forever.
    # Compare two manifest snapshots before publishing new host URLs.
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        first = list(pool.map(lambda c: manifest_snapshot(c[0], base), CHANNELS))
    time.sleep(20)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        second = list(pool.map(lambda c: manifest_snapshot(c[0], base), CHANNELS))
        advancing = [(ch[0], snap) for ch, old, snap in
                     zip(CHANNELS, first, second) if has_advanced(old, snap)]
        checks = list(pool.map(lambda item: probe_latest_segment(item[1]), advancing))
    good = {channel_id for (channel_id, _), ok in zip(advancing, checks) if ok}
    print("HARUKA source: " + source + "; host=" + base
          + "; HLS-advancing=" + str(len(advancing)) + "/" + str(len(CHANNELS))
          + "; fresh-TS-passing=" + str(len(good)))
    if not good:
        print("All sources frozen/unavailable: preserve existing yovi URLs (not LIVE)")
        return
    updated, kept = update_yovi(original, base, good)
    print("HARUKA entries kept on previous URL=" + str(kept))
    if updated != original:
        if args.dry_run:
            print("Dry run: yovi would be updated")
        else:
            PLAYLIST.write_text(updated, encoding="utf-8", newline="\n")
            print("Updated yovi HARUKA trial only")
    else:
        print("yovi HARUKA trial already current")


if __name__ == "__main__":
    main()
