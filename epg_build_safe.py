from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

import epg_build

# Public-sports EPG is generated locally in this repository and merged later by
# public_sports_epg_merge.py. Never fetch the retired external public-sports repo
# from the base EPG builder.
epg_build.SOURCES = [(name, url) for name, url in epg_build.SOURCES if name != "public_sports"]
epg_build.SOURCE_PRIORITY = {name: i for i, (name, _) in enumerate(epg_build.SOURCES)}

# Rakuten R Channel IDs must never be matched by a similar display name. In
# particular rch_42 had been incorrectly borrowing karenda/rch_122. Use only the
# exact Rakuten source ID; when it is missing, the normal fallback is safer.
RAKUTEN_CHANNELS = {
    "rch_30": "鉄道・旅",
    "rch_98": "セクシーエンタメチャンネル",
    "rch_59": "おとなの歓楽街 by MEN'S NECO",
    "rch_41": "アイドル・グラビア",
    "rch_40": "刺激ストロング",
    "rch_42": "映画",
}
epg_build.SOURCE_PIN.update({channel_id: ("karenda", channel_id) for channel_id in RAKUTEN_CHANNELS})

epg_build.main()

out = Path("guides.xml")
if not out.is_file() or out.stat().st_size < 100_000:
    raise SystemExit(f"guides.xml suspiciously small: {out.stat().st_size if out.exists() else 0} bytes")

# 愛南ライブカメラ has no programme grid. Keep a 24-hour guide visible so the
# FreeWiFi EPG row never appears blank. Rebuild four JST days on every EPG run.
AINAN_ID = "ecatv.ainan_livecam"
AINAN_NAME = "愛南ライブカメラ"
JST = timezone(timedelta(hours=9))

root = ET.parse(out).getroot()

# Replace only our synthetic Ainan entries; leave every other channel untouched.
for p in list(root.findall("programme")):
    if p.get("channel") == AINAN_ID:
        root.remove(p)

ch = root.find(f"channel[@id='{AINAN_ID}']")
if ch is None:
    ch = ET.SubElement(root, "channel", {"id": AINAN_ID})
    ET.SubElement(ch, "display-name").text = AINAN_NAME

start_day = datetime.now(JST).replace(hour=0, minute=0, second=0, microsecond=0)
for offset in range(4):
    start = start_day + timedelta(days=offset)
    stop = start + timedelta(days=1)
    programme = ET.SubElement(
        root,
        "programme",
        {
            "start": start.strftime("%Y%m%d%H%M%S +0900"),
            "stop": stop.strftime("%Y%m%d%H%M%S +0900"),
            "channel": AINAN_ID,
        },
    )
    ET.SubElement(programme, "title", {"lang": "ja"}).text = "📹 愛南ライブカメラ｜24時間LIVE"
    ET.SubElement(programme, "desc", {"lang": "ja"}).text = (
        "愛媛CATV 愛南ライブカメラ。愛南地域のライブ映像を24時間配信しています。"
    )
    ET.SubElement(programme, "category", {"lang": "ja"}).text = "ライブカメラ"


def parse_xmltv_time(value: str | None) -> datetime | None:
    """Parse the common XMLTV YYYYmmddHHMMSS +/-ZZZZ form."""
    if not value:
        return None
    m = re.match(r"^(\d{14})(?:\s*([+-]\d{4}))?", value.strip())
    if not m:
        return None
    stamp, offset = m.groups()
    try:
        if offset:
            return datetime.strptime(f"{stamp} {offset}", "%Y%m%d%H%M%S %z")
        return datetime.strptime(stamp, "%Y%m%d%H%M%S").replace(tzinfo=JST)
    except ValueError:
        return None


# A source can contain historical programmes and still look "non-empty" to the
# base matcher. That made Rakuten rows appear OK in the report while VLC/IPTV
# clients had no programme covering the current time. Require at least one
# programme overlapping now through the next three days. Otherwise replace it
# with a visible fallback guide instead of leaving a blank row.
now = datetime.now(JST)
window_start = now - timedelta(hours=1)
window_end = now + timedelta(days=3)
forced_rakuten_fallback: list[tuple[str, str]] = []

for channel_id, channel_name in RAKUTEN_CHANNELS.items():
    programmes = [p for p in root.findall("programme") if p.get("channel") == channel_id]
    has_current = False
    for p in programmes:
        start = parse_xmltv_time(p.get("start"))
        stop = parse_xmltv_time(p.get("stop"))
        if start is None:
            continue
        if stop is None or stop <= start:
            stop = start + timedelta(hours=6)
        if stop >= window_start and start <= window_end:
            has_current = True
            break

    if has_current:
        continue

    # Remove stale/wrong source material and any duplicate channel declaration.
    for p in programmes:
        root.remove(p)
    for old_ch in list(root.findall("channel")):
        if old_ch.get("id") == channel_id:
            root.remove(old_ch)

    epg_build.add_fallback(root, channel_id, channel_name, "楽天")
    forced_rakuten_fallback.append((channel_id, channel_name))

ET.ElementTree(root).write(out, encoding="utf-8", xml_declaration=True)

# Keep the coverage report truthful when the post-build Rakuten guard had to
# replace a stale source with fallback EPG.
report_path = Path("epg_coverage.txt")
if forced_rakuten_fallback and report_path.is_file():
    lines = report_path.read_text(encoding="utf-8", errors="replace").splitlines()
    replaced = 0
    forced_ids = {channel_id: channel_name for channel_id, channel_name in forced_rakuten_fallback}
    for i, line in enumerate(lines):
        if not line.startswith("OK\t"):
            continue
        parts = line.split("\t")
        if len(parts) >= 2 and parts[1] in forced_ids:
            channel_id = parts[1]
            lines[i] = (
                f"FALLBACK\t{channel_id}\t{forced_ids[channel_id]}\t楽天\t"
                "12 programmes (no current Rakuten EPG)"
            )
            replaced += 1

    if replaced:
        def adjust(prefix: str, delta: int) -> None:
            for idx, line in enumerate(lines):
                if line.startswith(prefix):
                    value = int(line.split("=", 1)[1])
                    lines[idx] = f"{prefix}{value + delta}"
                    return

        adjust("matched_real=", -replaced)
        adjust("fallback=", replaced)
        adjust("unmatched_real=", replaced)

    report_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

root = ET.parse(out).getroot()
channels = len(root.findall("channel"))
programmes = len(root.findall("programme"))
if channels < 50 or programmes < 100:
    raise SystemExit(f"guides.xml suspiciously sparse: channels={channels} programmes={programmes}")

ainan_programmes = sum(1 for p in root.findall("programme") if p.get("channel") == AINAN_ID)
if ainan_programmes != 4:
    raise SystemExit(f"Ainan live-camera EPG missing: programmes={ainan_programmes}")

rakuten_counts = {
    channel_id: sum(1 for p in root.findall("programme") if p.get("channel") == channel_id)
    for channel_id in RAKUTEN_CHANNELS
}
if any(count == 0 for count in rakuten_counts.values()):
    raise SystemExit(f"Rakuten EPG blank after guard: {rakuten_counts}")

print(
    f"SAFE EPG OK: bytes={out.stat().st_size} channels={channels} programmes={programmes} "
    f"ainan_programmes={ainan_programmes} rakuten={rakuten_counts}"
)
