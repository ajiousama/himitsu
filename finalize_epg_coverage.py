from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from pathlib import Path

PLAYLISTS = [Path("freewifi"), Path("other_live.m3u")]
GUIDES = Path("guides.xml")
REPORT = Path("epg_coverage.txt")
PUBLIC_SPORT_PREFIXES = ("boat.", "keirin.", "auto.", "chihou.", "jra.")


def parse_playlists():
    out = {}
    for path in PLAYLISTS:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
            if not line.startswith("#EXTINF:"):
                continue
            mid = re.search(r'tvg-id="([^"]+)"', line)
            if not mid:
                continue
            cid = mid.group(1).strip()
            name = line.rsplit(",", 1)[-1].strip() if "," in line else cid
            group_match = re.search(r'group-title="([^"]*)"', line)
            group = group_match.group(1).strip() if group_match else ""
            out.setdefault(cid, (name, group))
    return out


def parse_xmltv_time(value):
    value = (value or "").strip()
    if len(value) < 14:
        return None
    try:
        return datetime.strptime(value[:14], "%Y%m%d%H%M%S")
    except ValueError:
        return None


def is_synthetic_fallback_grid(programmes):
    """Detect the 3-day/6-hour grid emitted by epg_build.add_fallback()."""
    if len(programmes) != 12:
        return False
    starts = []
    for p in programmes:
        start = parse_xmltv_time(p.get("start"))
        stop = parse_xmltv_time(p.get("stop"))
        if not start or not stop:
            return False
        if (stop - start).total_seconds() != 6 * 60 * 60:
            return False
        if start.hour not in (0, 6, 12, 18) or start.minute or start.second:
            return False
        starts.append(start)
    return len({x.date() for x in starts}) == 3


def old_source_errors():
    if not REPORT.exists():
        return ["none"]
    lines = REPORT.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    try:
        start = lines.index("[source errors]") + 1
    except ValueError:
        return ["none"]
    out = []
    for line in lines[start:]:
        if line.startswith("["):
            break
        if line.strip():
            out.append(line)
    return out or ["none"]


def main():
    wanted = parse_playlists()
    if not GUIDES.exists():
        raise SystemExit("guides.xml is missing")

    root = ET.parse(GUIDES).getroot()
    programmes = defaultdict(list)
    for p in root.findall("programme"):
        cid = (p.get("channel") or "").strip()
        if cid:
            programmes[cid].append(p)

    real = []
    fallback = []
    blank = []
    public_sports_invalid = []

    for cid, (name, group) in wanted.items():
        ps = programmes.get(cid, [])
        if not ps:
            status = "BLANK"
            blank.append(cid)
        elif is_synthetic_fallback_grid(ps):
            status = "FALLBACK"
            fallback.append(cid)
        else:
            status = "OK-FINAL"
            real.append(cid)

        is_public_sport = cid.startswith(PUBLIC_SPORT_PREFIXES) or group == "今日の開催場"
        if is_public_sport and status != "OK-FINAL":
            public_sports_invalid.append(cid)

    errors = old_source_errors()
    coverage = []
    for cid, (name, group) in wanted.items():
        count = len(programmes.get(cid, []))
        if cid in blank:
            coverage.append(f"BLANK\t{cid}\t{name}\t{group}\t0 programmes")
        elif cid in fallback:
            coverage.append(f"FALLBACK\t{cid}\t{name}\t{group}\t{count} programmes (final synthetic grid)")
        else:
            coverage.append(f"OK-FINAL\t{cid}\t{name}\t{group}\t{count} programmes")

    report = [
        "FreeWiFi FINAL EPG coverage",
        f"wanted={len(wanted)}",
        f"matched_real={len(real)}",
        f"fallback={len(fallback)}",
        f"blank={len(blank)}",
        f"unmatched_real={len(fallback) + len(blank)}",
        f"covered_total={len(real) + len(fallback)}",
        f"public_sports_invalid={len(public_sports_invalid)}",
        f"output_bytes={GUIDES.stat().st_size}",
        "",
        "[source errors]",
        *errors,
        "",
        "[public sports invalid]",
        *(public_sports_invalid or ["none"]),
        "",
        "[coverage]",
        *coverage,
    ]
    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")

    print(
        f"FINAL real={len(real)}/{len(wanted)} fallback={len(fallback)} "
        f"blank={len(blank)} public_sports_invalid={len(public_sports_invalid)}"
    )
    if public_sports_invalid:
        print("Public-sports channels without final race/status EPG:", file=sys.stderr)
        for cid in public_sports_invalid:
            print(f"  - {cid}", file=sys.stderr)
        raise SystemExit(2)


if __name__ == "__main__":
    main()
