#!/usr/bin/env python3
"""
Build a local-station M3U from a private CSV.

This script is intentionally metadata-first. The repository CSV keeps stream_url blank.
Users should copy the template locally, fill stream_url privately, and run this script.

It does not discover, fetch, scrape, or validate playback URLs.
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Dict, Iterable, List

REQUIRED_COLUMNS = [
    "channel_key",
    "display_name",
    "group_title",
    "tvg_id",
    "tvg_name",
    "stream_url",
]


def read_rows(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"CSV not found: {path}")

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise ValueError("CSV has no header row")

        missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise ValueError(f"CSV missing required columns: {', '.join(missing)}")

        return [{k: (v or "").strip() for k, v in row.items()} for row in reader]


def safe_attr(value: str) -> str:
    return value.replace('"', "'").strip()


def build_m3u(rows: Iterable[Dict[str, str]], *, include_missing: bool = False) -> str:
    lines: List[str] = ["#EXTM3U"]
    used = 0
    skipped = 0

    for row in rows:
        url = row.get("stream_url", "").strip()
        if not url:
            skipped += 1
            if include_missing:
                key = row.get("channel_key", "unknown")
                lines.append(f"#SKIP {key}: stream_url is blank")
            continue

        tvg_id = safe_attr(row.get("tvg_id", ""))
        tvg_name = safe_attr(row.get("tvg_name") or row.get("display_name", ""))
        group = safe_attr(row.get("group_title") or "Local Stations")
        logo = safe_attr(row.get("logo_hint", ""))
        name = row.get("display_name") or tvg_name or row.get("channel_key", "")

        attrs = [f'tvg-id="{tvg_id}"', f'tvg-name="{tvg_name}"', f'group-title="{group}"']
        if logo:
            attrs.insert(2, f'tvg-logo="{logo}"')

        lines.append(f"#EXTINF:-1 {' '.join(attrs)},{name}")
        lines.append(url)
        used += 1

    lines.append(f"# Generated entries: {used}")
    lines.append(f"# Skipped blank stream_url rows: {skipped}")
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a local-station M3U from a private CSV.")
    parser.add_argument("--csv", default="japan_iptv_local_station_m3u_private_template.csv", help="Input CSV with private stream_url values")
    parser.add_argument("--out", default="local_station_private.m3u", help="Output M3U path")
    parser.add_argument("--include-missing", action="store_true", help="Write #SKIP comments for blank URL rows")
    args = parser.parse_args()

    input_path = Path(args.csv)
    output_path = Path(args.out)

    rows = read_rows(input_path)
    m3u = build_m3u(rows, include_missing=args.include_missing)
    output_path.write_text(m3u, encoding="utf-8")

    print(f"Wrote: {output_path}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
