#!/usr/bin/env python3
"""Mirror verified BOAT Auto v4 outputs from ajiousama/himitsu.

Source of truth for BOAT streams/EPG is ajiousama/himitsu. This repository
keeps its own 3-day EPG pipeline for the other sports.
"""
from __future__ import annotations

import argparse
import json
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = "https://raw.githubusercontent.com/ajiousama/himitsu/main/"
UA = "public-sports-iptv BOAT-v4 mirror/1.1"


def get(name: str) -> bytes:
    req = urllib.request.Request(BASE + name, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def sync_streams() -> None:
    # Use the verified per-venue state directly.  Parsing freewifi made the
    # mirror depend on playlist layout and could associate a venue with the
    # wrong neighbouring URL.
    state_raw = get("boat_auto_state.json")
    state = json.loads(state_raw)
    status_raw = get("today_boat_status.json")
    status = json.loads(status_raw)

    for name, obj in (("boat_auto_state.json", state), ("today_boat_status.json", status)):
        if obj.get("architecture_version") != 4 or not obj.get("last_update_ok"):
            raise SystemExit(f"BOAT Auto v4 source is not healthy in {name}; refusing to replace local BOAT data")

    if state.get("date") != status.get("date"):
        raise SystemExit(f"BOAT v4 source date mismatch: state={state.get('date')} status={status.get('date')}")

    streams = state.get("streams") or {}
    expected = int(status.get("visible_count", 0) or state.get("visible_count", 0))
    if not isinstance(streams, dict) or not streams:
        raise SystemExit("BOAT v4 verified streams are missing; refusing to replace local BOAT data")

    venue_names = {}
    for key in streams:
        if key.startswith("boat."):
            venue_names[key] = key.split(".", 1)[1]

    # Prefer names already published by freewifi only as display metadata;
    # URLs always come from the verified state above.
    try:
        playlist = get("freewifi").decode("utf-8")
        for line in playlist.splitlines():
            if not (line.startswith("#EXTINF:") and 'tvg-id="boat.' in line):
                continue
            import re
            mid = re.search(r'tvg-id="(boat\.[^"]+)"', line)
            mname = re.search(r'tvg-name="([^"]+)"', line)
            if mid and mname:
                venue_names[mid.group(1)] = mname.group(1).removeprefix("BOATRACE")
    except Exception as e:
        print(f"BOAT display-name lookup skipped: {e}")

    out = ["#EXTM3U", f"# BOAT-DATE:{str(status.get('date','')).replace('-', '')}", "# BOAT-SOURCE:ajiousama/himitsu BOAT Auto v4 verified state"]
    seen_urls = {}
    count = 0
    for tvg_id, info in streams.items():
        if not tvg_id.startswith("boat.") or not isinstance(info, dict):
            continue
        url = str(info.get("url") or "").strip()
        if not url.startswith(("http://", "https://")):
            continue
        if not info.get("playback_verified"):
            raise SystemExit(f"BOAT v4 stream is not playback-verified: {tvg_id}")

        # The manifest path (before ?token=) is the venue/content identity.
        # Tokens can legitimately be shared, so never compare token alone.
        manifest = url.split("?", 1)[0]
        other = seen_urls.get(manifest)
        if other and other != tvg_id:
            raise SystemExit(f"BOAT v4 duplicate manifest: {other} and {tvg_id}: {manifest}")
        seen_urls[manifest] = tvg_id

        slug = tvg_id.split(".", 1)[1]
        name = venue_names.get(tvg_id, slug)
        logo = f"https://images.weserv.nl/?url=raw.githubusercontent.com/ajiousama/himitsu/main/logos/public_sports/venues/boat_{slug}.png&output=png"
        ext = f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="BOATRACE{name}" tvg-logo="{logo}" group-title="今日の開催場",BOATRACE{name}'
        out += ["", ext, url]
        count += 1

    if count < 1 or (expected and count != expected):
        raise SystemExit(f"BOAT v4 playlist mismatch: verified={count} expected={expected}")

    Path("boatrace_today.m3u").write_text("\n".join(out) + "\n", encoding="utf-8")
    Path("boat_v4_status.json").write_bytes(status_raw)
    print(f"BOAT v4 verified streams synced: {count} venues; date={status.get('date')}")


def merge_epg() -> None:
    source = ET.fromstring(get("guides.xml"))
    target_path = Path("epg.xml")
    target = ET.parse(target_path).getroot()

    source_channels = {e.get("id"): e for e in source.findall("channel") if (e.get("id") or "").startswith("boat.")}
    source_programmes = [e for e in source.findall("programme") if (e.get("channel") or "").startswith("boat.")]
    if not source_channels or not source_programmes:
        raise SystemExit("BOAT v4 EPG missing in source guides.xml; refusing empty replacement")

    for e in list(target):
        if e.tag == "channel" and (e.get("id") or "").startswith("boat."):
            target.remove(e)
        elif e.tag == "programme" and (e.get("channel") or "").startswith("boat."):
            target.remove(e)

    first_programme = next((i for i, e in enumerate(list(target)) if e.tag == "programme"), len(target))
    for cid in sorted(source_channels):
        target.insert(first_programme, source_channels[cid])
        first_programme += 1
    for e in source_programmes:
        target.append(e)

    ET.ElementTree(target).write(target_path, encoding="utf-8", xml_declaration=True)
    ET.parse(target_path)
    print(f"BOAT v4 EPG merged: channels={len(source_channels)} programmes={len(source_programmes)}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=["streams", "epg", "all"])
    args = ap.parse_args()
    if args.phase in ("streams", "all"):
        sync_streams()
    if args.phase in ("epg", "all"):
        merge_epg()


if __name__ == "__main__":
    main()
