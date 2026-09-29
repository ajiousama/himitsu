#!/usr/bin/env python3
"""Check local-station tvg-id candidates against an XMLTV EPG file.

This script is metadata-only. It does not fetch or validate playback URLs.

Usage:
  python scripts/check_local_station_epg_ids.py \
    --epg epg.xml \
    --map japan_iptv_local_station_epg_map.csv \
    --out local_station_epg_check_result.csv
"""

from __future__ import annotations

import argparse
import csv
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, Iterable, List, Set


def read_epg_channel_ids(epg_path: Path) -> Set[str]:
    """Return every channel id found in an XMLTV file."""
    if not epg_path.exists():
        raise FileNotFoundError(f"EPG file not found: {epg_path}")

    ids: Set[str] = set()

    # iterparse keeps memory use reasonable for larger XMLTV files.
    for _event, elem in ET.iterparse(epg_path, events=("end",)):
        tag = elem.tag.split("}", 1)[-1]
        if tag == "channel":
            channel_id = (elem.attrib.get("id") or "").strip()
            if channel_id:
                ids.add(channel_id)
        elem.clear()

    return ids


def split_candidates(value: str) -> List[str]:
    """Split candidate id fields without being too clever."""
    if not value:
        return []
    parts: List[str] = []
    for chunk in value.replace("|", ";").replace("/", ";").split(";"):
        item = chunk.strip()
        if item:
            parts.append(item)
    return parts


def read_mapping_rows(map_path: Path) -> List[Dict[str, str]]:
    if not map_path.exists():
        raise FileNotFoundError(f"mapping CSV not found: {map_path}")

    with map_path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def find_first_match(candidates: Iterable[str], epg_ids: Set[str]) -> str:
    for candidate in candidates:
        if candidate in epg_ids:
            return candidate
    return ""


def build_result_rows(rows: List[Dict[str, str]], epg_ids: Set[str]) -> List[Dict[str, str]]:
    result: List[Dict[str, str]] = []

    for row in rows:
        channel_key = row.get("channel_key", "").strip()
        display_name = row.get("display_name", "").strip()
        preferred = row.get("tvg_id_preferred", "").strip()
        alternates = split_candidates(row.get("tvg_id_alternates", ""))
        slug_hints = split_candidates(row.get("slug_or_id_hint", ""))

        candidates: List[str] = []
        if preferred:
            candidates.append(preferred)
        candidates.extend(alternates)
        candidates.extend(slug_hints)

        # Keep first occurrence order while removing duplicates.
        seen: Set[str] = set()
        unique_candidates: List[str] = []
        for candidate in candidates:
            if candidate not in seen:
                unique_candidates.append(candidate)
                seen.add(candidate)

        matched = find_first_match(unique_candidates, epg_ids)
        status = "OK" if matched else "MISSING"

        result.append(
            {
                "channel_key": channel_key,
                "display_name": display_name,
                "status": status,
                "matched_epg_id": matched,
                "preferred_tvg_id": preferred,
                "checked_candidates": ";".join(unique_candidates),
                "note": "matched preferred/alternate id" if matched else "add or remap tvg-id",
            }
        )

    return result


def write_result(rows: List[Dict[str, str]], out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "channel_key",
        "display_name",
        "status",
        "matched_epg_id",
        "preferred_tvg_id",
        "checked_candidates",
        "note",
    ]
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Check URL-free local-station tvg-id candidates against an XMLTV EPG file."
    )
    parser.add_argument("--epg", required=True, help="Path to XMLTV EPG file, e.g. epg.xml")
    parser.add_argument(
        "--map",
        default="japan_iptv_local_station_epg_map.csv",
        help="Path to local station EPG map CSV",
    )
    parser.add_argument(
        "--out",
        default="local_station_epg_check_result.csv",
        help="Output CSV path",
    )
    args = parser.parse_args()

    epg_path = Path(args.epg)
    map_path = Path(args.map)
    out_path = Path(args.out)

    try:
        epg_ids = read_epg_channel_ids(epg_path)
        map_rows = read_mapping_rows(map_path)
        result_rows = build_result_rows(map_rows, epg_ids)
        write_result(result_rows, out_path)
    except Exception as exc:  # keep CLI-friendly error output
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    ok_count = sum(1 for row in result_rows if row["status"] == "OK")
    missing_count = sum(1 for row in result_rows if row["status"] == "MISSING")
    print(f"EPG channel IDs loaded: {len(epg_ids)}")
    print(f"Rows checked: {len(result_rows)}")
    print(f"OK: {ok_count}")
    print(f"MISSING: {missing_count}")
    print(f"Wrote: {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
