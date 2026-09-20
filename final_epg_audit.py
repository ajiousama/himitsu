from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

PLAYLISTS = [Path("freewifi"), Path("other_live.m3u")]
EPG = Path("guides.xml")
REPORT = Path("epg_final_audit.txt")
COVERAGE = Path("epg_coverage.txt")
JST = timezone(timedelta(hours=9))
PUBLIC_SPORT_PREFIXES = ("boat.", "keirin.", "auto.", "chihou.", "jra.")

SYNTHETIC_MARKERS = (
    "番組詳細EPG未取得",
    "実EPG未対応",
    "番組表未対応",
    "案内を常時表示",
    "空白時間を補完する案内表示",
    "実レースEPG取得失敗時の案内",
    "現在KICK配信 受信中",
    "YouTubeよりライブカメラ中継中",
)
SYNTHETIC_CATEGORIES = {"その他", "24H", "ライブカメラ", "KICK配信", "放送案内"}


def parse_xmltv_time(value: str | None) -> datetime | None:
    if not value:
        return None
    m = re.match(r"^(\d{14})(?:\s*([+-]\d{4}))?", value.strip())
    if not m:
        return None
    stamp, offset = m.groups()
    try:
        if offset:
            return datetime.strptime(f"{stamp} {offset}", "%Y%m%d%H%M%S %z").astimezone(JST)
        return datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(tzinfo=JST)
    except ValueError:
        return None


def parse_playlists():
    entries = []
    missing_tvg_id = []
    for path in PLAYLISTS:
        if not path.exists():
            continue
        for lineno, line in enumerate(path.read_text(encoding="utf-8-sig", errors="replace").splitlines(), 1):
            if not line.startswith("#EXTINF:"):
                continue
            name = line.rsplit(",", 1)[-1].strip() if "," in line else "(unknown)"
            group_m = re.search(r'group-title="([^"]*)"', line)
            group = group_m.group(1).strip() if group_m else ""
            id_m = re.search(r'tvg-id="([^"]*)"', line)
            tvg_id = id_m.group(1).strip() if id_m else ""
            if not tvg_id:
                missing_tvg_id.append((path.name, lineno, group, name))
                continue
            entries.append((path.name, lineno, tvg_id, group, name))
    return entries, missing_tvg_id


def is_synthetic(programme: ET.Element) -> bool:
    title = programme.findtext("title") or ""
    desc = programme.findtext("desc") or ""
    category = programme.findtext("category") or ""
    text = f"{title}\n{desc}"
    return category in SYNTHETIC_CATEGORIES or any(marker in text for marker in SYNTHETIC_MARKERS)


def is_public_sport(cid: str, group: str) -> bool:
    # "今日の開催場" is a presentation group, not a sport classifier.
    # Kana Tube can intentionally appear there, so strict race-EPG auditing
    # must be based on the stable public-sports tvg-id prefixes only.
    return cid.startswith(PUBLIC_SPORT_PREFIXES)


def main() -> int:
    if not EPG.exists() or not EPG.stat().st_size:
        raise RuntimeError("guides.xml is missing or empty")

    entries, missing_tvg_id = parse_playlists()
    root = ET.parse(EPG).getroot()
    channel_ids = {ch.get("id") for ch in root.findall("channel") if ch.get("id")}
    programmes = defaultdict(list)
    for p in root.findall("programme"):
        cid = p.get("channel") or ""
        if cid:
            programmes[cid].append(p)

    now = datetime.now(JST)
    window_start = now - timedelta(hours=2)
    window_end = now + timedelta(days=3)

    playlist_ids = {}
    for source, lineno, cid, group, name in entries:
        playlist_ids.setdefault(cid, (source, lineno, group, name))

    xml_channel_missing = []
    zero_programmes = []
    stale_only = []
    fallback_only = []
    healthy = []
    public_sports_invalid = []

    for cid, meta in sorted(playlist_ids.items()):
        source, lineno, group, name = meta
        if cid not in channel_ids:
            xml_channel_missing.append((cid, source, lineno, group, name))
            if is_public_sport(cid, group):
                public_sports_invalid.append((cid, "XML_CHANNEL_MISSING", group, name))
            continue
        rows = programmes.get(cid, [])
        if not rows:
            zero_programmes.append((cid, source, lineno, group, name))
            if is_public_sport(cid, group):
                public_sports_invalid.append((cid, "ZERO_PROGRAMMES", group, name))
            continue

        current_rows = []
        for p in rows:
            start = parse_xmltv_time(p.get("start"))
            stop = parse_xmltv_time(p.get("stop"))
            if start is None:
                continue
            if stop is None or stop <= start:
                stop = start + timedelta(hours=1)
            if stop >= window_start and start <= window_end:
                current_rows.append(p)

        if not current_rows:
            stale_only.append((cid, len(rows), source, lineno, group, name))
            if is_public_sport(cid, group):
                public_sports_invalid.append((cid, "STALE_ONLY", group, name))
            continue

        if all(is_synthetic(p) for p in current_rows):
            fallback_only.append((cid, len(current_rows), source, lineno, group, name))
            if is_public_sport(cid, group):
                public_sports_invalid.append((cid, "FALLBACK_ONLY_CURRENT", group, name))
        else:
            healthy.append((cid, len(current_rows), source, lineno, group, name))

    orphan_xml_channels = sorted(cid for cid in channel_ids if cid not in playlist_ids)

    lines = [
        "FINAL EPG AUDIT",
        f"generated={now.isoformat()}",
        f"playlist_entries_with_tvg_id={len(entries)}",
        f"playlist_unique_tvg_ids={len(playlist_ids)}",
        f"xml_channels={len(channel_ids)}",
        f"xml_programmes={sum(len(v) for v in programmes.values())}",
        f"healthy_current_real={len(healthy)}",
        f"fallback_only_current={len(fallback_only)}",
        f"missing_tvg_id_entries={len(missing_tvg_id)}",
        f"xml_channel_missing={len(xml_channel_missing)}",
        f"zero_programmes={len(zero_programmes)}",
        f"stale_only={len(stale_only)}",
        f"public_sports_invalid={len(public_sports_invalid)}",
        f"orphan_xml_channels={len(orphan_xml_channels)}",
        "",
    ]

    def section(title, rows, fmt):
        lines.append(f"[{title}]")
        if not rows:
            lines.append("none")
        else:
            lines.extend(fmt(row) for row in rows)
        lines.append("")

    section(
        "MISSING_TVG_ID",
        missing_tvg_id,
        lambda r: f"{r[0]}:{r[1]}\tgroup={r[2]}\tname={r[3]}",
    )
    section(
        "XML_CHANNEL_MISSING",
        xml_channel_missing,
        lambda r: f"{r[0]}\t{r[1]}:{r[2]}\tgroup={r[3]}\tname={r[4]}",
    )
    section(
        "ZERO_PROGRAMMES",
        zero_programmes,
        lambda r: f"{r[0]}\t{r[1]}:{r[2]}\tgroup={r[3]}\tname={r[4]}",
    )
    section(
        "STALE_ONLY",
        stale_only,
        lambda r: f"{r[0]}\tprogrammes={r[1]}\t{r[2]}:{r[3]}\tgroup={r[4]}\tname={r[5]}",
    )
    section(
        "FALLBACK_ONLY_CURRENT",
        fallback_only,
        lambda r: f"{r[0]}\tcurrent={r[1]}\t{r[2]}:{r[3]}\tgroup={r[4]}\tname={r[5]}",
    )
    section(
        "PUBLIC_SPORTS_INVALID",
        public_sports_invalid,
        lambda r: f"{r[0]}\tstatus={r[1]}\tgroup={r[2]}\tname={r[3]}",
    )
    section(
        "HEALTHY_CURRENT_REAL",
        healthy,
        lambda r: f"{r[0]}\tcurrent={r[1]}\t{r[2]}:{r[3]}\tgroup={r[4]}\tname={r[5]}",
    )
    section("ORPHAN_XML_CHANNELS", orphan_xml_channels, lambda r: r)

    REPORT.write_text("\n".join(lines), encoding="utf-8")

    # epg_coverage.txt is already published by the main workflow. Append the
    # final merged result there so the repository's visible coverage report is
    # based on the finished guides.xml rather than the pre-merge base build.
    if COVERAGE.exists():
        base = COVERAGE.read_text(encoding="utf-8", errors="replace")
        marker = "\n[FINAL MERGED EPG AUDIT]\n"
        if marker in base:
            base = base.split(marker, 1)[0].rstrip() + "\n"
        concise = [
            marker.strip("\n"),
            f"generated={now.isoformat()}",
            f"healthy_current_real={len(healthy)}",
            f"fallback_only_current={len(fallback_only)}",
            f"missing_tvg_id_entries={len(missing_tvg_id)}",
            f"xml_channel_missing={len(xml_channel_missing)}",
            f"zero_programmes={len(zero_programmes)}",
            f"stale_only={len(stale_only)}",
            f"public_sports_invalid={len(public_sports_invalid)}",
            "",
            "[FINAL MISSING_TVG_ID]",
        ]
        concise.extend(
            f"{r[0]}:{r[1]}\tgroup={r[2]}\tname={r[3]}" for r in missing_tvg_id
        )
        if not missing_tvg_id:
            concise.append("none")
        concise.extend(["", "[FINAL XML_CHANNEL_MISSING]"])
        concise.extend(
            f"{r[0]}\tgroup={r[3]}\tname={r[4]}" for r in xml_channel_missing
        )
        if not xml_channel_missing:
            concise.append("none")
        concise.extend(["", "[FINAL ZERO_PROGRAMMES]"])
        concise.extend(
            f"{r[0]}\tgroup={r[3]}\tname={r[4]}" for r in zero_programmes
        )
        if not zero_programmes:
            concise.append("none")
        concise.extend(["", "[FINAL STALE_ONLY]"])
        concise.extend(
            f"{r[0]}\tprogrammes={r[1]}\tgroup={r[4]}\tname={r[5]}" for r in stale_only
        )
        if not stale_only:
            concise.append("none")
        concise.extend(["", "[FINAL FALLBACK_ONLY_CURRENT]"])
        concise.extend(
            f"{r[0]}\tcurrent={r[1]}\tgroup={r[4]}\tname={r[5]}" for r in fallback_only
        )
        if not fallback_only:
            concise.append("none")
        concise.extend(["", "[FINAL PUBLIC_SPORTS_INVALID]"])
        concise.extend(
            f"{r[0]}\tstatus={r[1]}\tgroup={r[2]}\tname={r[3]}" for r in public_sports_invalid
        )
        if not public_sports_invalid:
            concise.append("none")
        COVERAGE.write_text(base.rstrip() + "\n\n" + "\n".join(concise) + "\n", encoding="utf-8")

    print(
        "FINAL EPG AUDIT: "
        f"real={len(healthy)} fallback={len(fallback_only)} missing_id={len(missing_tvg_id)} "
        f"xml_missing={len(xml_channel_missing)} zero={len(zero_programmes)} stale={len(stale_only)} "
        f"public_sports_invalid={len(public_sports_invalid)}"
    )

    # Public sports must never be published with only the generic 6-hour
    # fallback grid, with no programmes, or with only stale programmes.
    if public_sports_invalid:
        for cid, status, group, name in public_sports_invalid:
            print(f"PUBLIC SPORTS INVALID: {cid} status={status} group={group} name={name}")
        return 2

    strict = "--strict" in sys.argv
    if strict and (xml_channel_missing or zero_programmes or stale_only):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
