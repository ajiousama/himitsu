#!/usr/bin/env python3
"""HARUKA yovi-only trial: API host chasing with HLS+TS validation.

Never edits FreeWiFi, TV, Rakuten, or any non-managed yovi channel.
A missing HARUKA_AU may bootstrap the previously tested IP once; subsequent
automatic host chasing needs the HARUKA_AU GitHub Actions secret.
An HTTP 200 only shows data availability, NOT live broadcast freshness.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import json
import os
import re
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
# Only channels for which both HLS and a MPEG-TS segment were fetched on 2026-11-23.
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
    (35, "BS朝日", "BS朝日_jp", "BS"),
    (36, "BS-TBS", "BS-TBS_jp", "BS"),
    (37, "BSテレ東", "BSテレ東_jp", "BS"),
    (38, "BSフジ", "BSフジ_jp", "BS"),
    (39, "WOWOWプライム", "WOWOWプライム_jp", "BS"),
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


def probe(channel_id: int, base: str) -> bool:
    url = stream_url(base, channel_id)
    try:
        with OPENER.open(urllib.request.Request(url, headers=HEADERS), timeout=6) as response:
            if response.status != 200:
                return False
            body = response.read(16000).decode("utf-8", errors="replace")
        if not body.startswith("#EXTM3U"):
            return False
        first = next((s.strip() for s in body.splitlines() if s.strip() and not s.startswith("#")), None)
        if not first:
            return False
        segment = urllib.parse.urljoin(url, first)
        parsed = urllib.parse.urlsplit(segment)
        if parsed.scheme != "http" or parsed.netloc != urllib.parse.urlsplit(url).netloc:
            return False
        request = urllib.request.Request(segment, headers={**HEADERS, "Range": "bytes=0-4095"})
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
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        checks = list(pool.map(lambda c: (c[0], probe(c[0], base)), CHANNELS))
    good = {n for n, ok in checks if ok}
    print("HARUKA source: " + source + "; host=" + base
          + "; TS-passing=" + str(len(good)) + "/" + str(len(CHANNELS)))
    if not good:
        print("No TS-passing channels; keeping all existing content")
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
