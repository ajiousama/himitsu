from __future__ import annotations

"""Normalize race-by-race XMLTV blocks to the common FreeWiFi race rule.

Rule for every real race programme:
- a verified 1R starts 30 minutes before its advertised start, not before midnight;
- a date-specific "本日開催 / 1R / 開催区分" guide covers midnight to 1R;
- race N remains selected until its advertised start time + 3 minutes;
- race N+1 starts exactly at race N start time + 3 minutes;
- after the final race, an existing finished notice starts at final start + 3 minutes.

This is intentionally a final-output normalizer. Individual acquisition/repair
scripts may use their own temporary lead-in windows, but FreeWiFi's published EPG
must always follow the same race boundary rule.
"""

import argparse
from datetime import datetime, timedelta, time
from pathlib import Path
import xml.etree.ElementTree as ET

from sports_race_time import JST, race_time, FIRST_RACE_LEAD_MINUTES

FIRST_RACE_LEAD = timedelta(minutes=FIRST_RACE_LEAD_MINUTES)
SWITCH = timedelta(minutes=3)
TARGET_PREFIXES = (
    "keirin.",
    "chihou.",
    "auto.",
    "boat.",
)
JRA_BASES = {"jra.east", "jra.west", "jra.hokkaido", "jra.local"}
TARGET_IDS = JRA_BASES | {base + suffix for base in JRA_BASES for suffix in (".hq", ".lq")}


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


def is_prestart_guidance(programme: ET.Element) -> bool:
    text = title(programme)
    return text.startswith("本日") and "開催" in text and "1R" in text and "発走" in text


def prestart_guidance(root: ET.Element, channel: str, meeting_day) -> ET.Element | None:
    rows = [
        p for p in root.findall("programme")
        if p.get("channel") == channel and not race_time(p) and is_prestart_guidance(p)
        and (start := parse_xmltv(p.get("start"))) is not None
        and start.date() == meeting_day
    ]
    return min(rows, key=lambda p: p.get("start", "")) if rows else None


def normalize_prestart_guidance(
    root: ET.Element,
    channel: str,
    meeting_day,
    first_start: datetime,
    first_dt: datetime,
    first_programme: ET.Element,
) -> int:
    """Create/repair only this meeting day's confirmed 1R waiting block."""
    midnight = datetime.combine(meeting_day, time(0, 0), tzinfo=JST)
    guide = prestart_guidance(root, channel, meeting_day)
    changed = 0
    if first_start > midnight and guide is None:
        name = next((c.findtext("display-name") for c in root.findall("channel")
                     if c.get("id") == channel), None) or channel
        info = race_time(first_programme)
        clock = info["start"] if info else first_dt.strftime("%H:%M")
        detail = first_programme.findtext("desc") or ""
        mode = next((m for m in ("オーバーミッドナイト", "ミッドナイト", "モーニング",
                                "ナイター", "薄暮", "デイ") if m in detail), "")
        guide = ET.SubElement(root, "programme", {"channel": channel})
        ET.SubElement(guide, "title", {"lang": "ja"}).text = (
            f"本日{name}開催　1R{clock}発走" + (f"　{mode}" if mode else "")
        )
        ET.SubElement(guide, "desc", {"lang": "ja"}).text = f"{name}は本日開催です。1R発走予定: {clock}"
        changed += 1

    if guide is not None:
        if first_start <= midnight:
            root.remove(guide)
            guide = None
            changed += 1
        else:
            for attr, wanted in (("start", midnight), ("stop", first_start)):
                if guide.get(attr) != fmt(wanted):
                    guide.set(attr, fmt(wanted))
                    changed += 1

    for p in list(root.findall("programme")):
        if p is guide or p.get("channel") != channel or race_time(p):
            continue
        start, stop = parse_xmltv(p.get("start")), parse_xmltv(p.get("stop"))
        if not start or not stop or stop <= midnight or start >= first_start:
            continue
        if start < midnight:
            # Preserve the preceding day's programme, not its spill into this day.
            p.set("stop", fmt(midnight))
            changed += 1
        elif start.date() == meeting_day:
            # A confirmed first race supersedes generic same-day waiting placeholders.
            if "中止" in title(p) or "開催予定に変更" in title(p):
                continue
            root.remove(p)
            changed += 1
    return changed


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

        first_dt, first_number, first_programme = rows[0]
        midnight = datetime.combine(_meeting_day, time(0, 0), tzinfo=JST)
        wanted_first_start = max(midnight, first_dt - FIRST_RACE_LEAD)
        if first_programme.get("start") != fmt(wanted_first_start):
            first_programme.set("start", fmt(wanted_first_start))
            changed += 1
        if first_number == 1:
            changed += normalize_prestart_guidance(
                root, channel, _meeting_day, wanted_first_start, first_dt, first_programme
            )
        else:
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
        midnight = datetime.combine(meeting_day, time(0, 0), tzinfo=JST)
        wanted_first_start = max(midnight, first_dt - FIRST_RACE_LEAD)
        if first_number == 1 and wanted_first_start > midnight:
            guide = prestart_guidance(root, channel, meeting_day)
            if guide is None or guide.get("start") != fmt(midnight) or guide.get("stop") != fmt(wanted_first_start):
                errors.append(f"{channel} {meeting_day} missing/incomplete midnight-to-1R guide")
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
        print(f"{path}: prestart/+3 check OK races={checked}")
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
