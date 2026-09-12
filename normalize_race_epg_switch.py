from __future__ import annotations

"""Normalize race-by-race XMLTV blocks to the common FreeWiFi race rule.

Rule for every real race programme:
- the first race of a meeting starts 45 minutes before its advertised start;
- race N remains selected until its advertised start time + 3 minutes;
- race N+1 starts exactly at race N start time + 3 minutes;
- after the final race, an existing finished notice starts at final start + 3 minutes.

This is intentionally a final-output normalizer. Individual acquisition/repair
scripts may use their own temporary lead-in windows, but FreeWiFi's published EPG
must always follow the same race boundary rule.
"""

import argparse
from datetime import datetime, timedelta
from pathlib import Path
import xml.etree.ElementTree as ET

from sports_race_time import JST, race_time

FIRST_RACE_LEAD = timedelta(minutes=45)
SWITCH = timedelta(minutes=3)
TARGET_PREFIXES = (
    "keirin.",
    "chihou.",
    "auto.",
    "boat.",
)
TARGET_IDS = {"jra.east", "jra.west", "jra.hokkaido"}


def parse_xmltv(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    raw = text[:14]
    if len(raw) != 14 or not raw.isdigit():
        return None
    try:
        return datetime.strptime(raw, "%Y%m%d%H%M%S").replace(tzinfo=JST)
    except ValueError:
        return None


def fmt(value: datetime) -> str:
    return value.astimezone(JST).strftime("%Y%m%d%H%M%S +0900")


def is_target(channel: str) -> bool:
    return channel in TARGET_IDS or channel.startswith(TARGET_PREFIXES)


def title(programme: ET.Element) -> str:
    return (programme.findtext("title") or "").strip()


def race_groups(root: ET.Element):
    groups: dict[tuple[str, object], list[tuple[datetime, int, ET.Element]]] = {}
    for programme in root.findall("programme"):
        channel = programme.get("channel") or ""
        if not is_target(channel):
            continue
        info = race_time(programme)
        if not info:
            continue
        groups.setdefault((channel, info["day"]), []).append(
            (info["dt"], int(info["race"]), programme)
        )
    for rows in groups.values():
        rows.sort(key=lambda row: (row[0], row[1], row[2].get("start", "")))
    return groups


def find_finish_notice(root: ET.Element, channel: str, final_dt: datetime) -> ET.Element | None:
    candidates = []
    latest = final_dt + timedelta(hours=6)
    for programme in root.findall("programme"):
        if programme.get("channel") != channel:
            continue
        if race_time(programme):
            continue
        if "終了" not in title(programme):
            continue
        start = parse_xmltv(programme.get("start"))
        if start and final_dt <= start <= latest:
            candidates.append((start, programme))
    return min(candidates, key=lambda item: item[0])[1] if candidates else None


def trim_overlapping_leadin(root: ET.Element, channel: str, first_start: datetime) -> int:
    """End a non-race lead-in/waiting block exactly where 1R begins."""
    changed = 0
    for programme in root.findall("programme"):
        if programme.get("channel") != channel or race_time(programme):
            continue
        start = parse_xmltv(programme.get("start"))
        stop = parse_xmltv(programme.get("stop"))
        if not start or not stop:
            continue
        if start < first_start < stop and "終了" not in title(programme):
            programme.set("stop", fmt(first_start))
            changed += 1
    return changed


def normalize_root(root: ET.Element) -> tuple[int, int]:
    changed = 0
    races_seen = 0
    for (channel, _meeting_day), rows in race_groups(root).items():
        if not rows:
            continue
        races_seen += len(rows)

        first_dt, _first_number, first_programme = rows[0]
        wanted_first_start = first_dt - FIRST_RACE_LEAD
        if first_programme.get("start") != fmt(wanted_first_start):
            first_programme.set("start", fmt(wanted_first_start))
            changed += 1
        changed += trim_overlapping_leadin(root, channel, wanted_first_start)

        for index, (race_dt, _number, programme) in enumerate(rows):
            wanted_stop = race_dt + SWITCH
            if programme.get("stop") != fmt(wanted_stop):
                programme.set("stop", fmt(wanted_stop))
                changed += 1

            if index > 0:
                wanted_start = rows[index - 1][0] + SWITCH
                if programme.get("start") != fmt(wanted_start):
                    programme.set("start", fmt(wanted_start))
                    changed += 1

        final_dt = rows[-1][0]
        finish = find_finish_notice(root, channel, final_dt)
        if finish is not None:
            wanted = final_dt + SWITCH
            if finish.get("start") != fmt(wanted):
                finish.set("start", fmt(wanted))
                changed += 1

    return changed, races_seen


def validate_root(root: ET.Element, label: str) -> int:
    checked = 0
    errors = []
    for (channel, meeting_day), rows in race_groups(root).items():
        if not rows:
            continue

        first_dt, first_number, first_programme = rows[0]
        first_start = parse_xmltv(first_programme.get("start"))
        wanted_first_start = first_dt - FIRST_RACE_LEAD
        if first_start != wanted_first_start:
            errors.append(
                f"{channel} {meeting_day} {first_number}R first_start={first_start} expected={wanted_first_start}"
            )

        for index, (race_dt, number, programme) in enumerate(rows):
            checked += 1
            stop = parse_xmltv(programme.get("stop"))
            wanted_stop = race_dt + SWITCH
            if stop != wanted_stop:
                errors.append(
                    f"{channel} {meeting_day} {number}R stop={stop} expected={wanted_stop}"
                )
            if index > 0:
                start = parse_xmltv(programme.get("start"))
                wanted_start = rows[index - 1][0] + SWITCH
                if start != wanted_start:
                    errors.append(
                        f"{channel} {meeting_day} {number}R start={start} expected={wanted_start}"
                    )

        for programme in root.findall("programme"):
            if programme.get("channel") != channel or race_time(programme):
                continue
            start = parse_xmltv(programme.get("start"))
            stop = parse_xmltv(programme.get("stop"))
            if start and stop and start < wanted_first_start < stop and "終了" not in title(programme):
                errors.append(
                    f"{channel} {meeting_day} lead-in overlaps 1R start: {start}-{stop}"
                )

        finish = find_finish_notice(root, channel, rows[-1][0])
        if finish is not None:
            start = parse_xmltv(finish.get("start"))
            wanted = rows[-1][0] + SWITCH
            if start != wanted:
                errors.append(
                    f"{channel} {meeting_day} finish start={start} expected={wanted}"
                )
    if errors:
        raise RuntimeError(label + " race-boundary validation failed:\n" + "\n".join(errors[:30]))
    return checked


def process(path: Path, check_only: bool) -> None:
    if not path.exists() or not path.stat().st_size:
        raise RuntimeError(f"missing/empty XML: {path}")
    tree = ET.parse(path)
    root = tree.getroot()
    if check_only:
        checked = validate_root(root, str(path))
        print(f"{path}: 45m/+3 check OK races={checked}")
        return

    changed, races_seen = normalize_root(root)
    validate_root(root, str(path))
    if changed:
        channels = [item for item in list(root) if item.tag == "channel"]
        programmes = [item for item in list(root) if item.tag == "programme"]
        other = [item for item in list(root) if item.tag not in {"channel", "programme"}]
        programmes.sort(key=lambda item: (item.get("start", ""), item.get("channel", "")))
        root[:] = channels + other + programmes
        ET.indent(tree, space="  ")
        tree.write(path, encoding="utf-8", xml_declaration=True)
    print(f"{path}: normalized races={races_seen} changed_fields={changed}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for path in args.paths:
        process(path, args.check)


if __name__ == "__main__":
    main()
