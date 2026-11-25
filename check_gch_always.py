#!/usr/bin/env python3
"""Reject FreeWiFi updates that drop an always-on Green Channel route."""
from pathlib import Path
import re
import json
from freewifi_today_jra import GCH_SINORI_LOGO, GCH_COFFEE_NAME, GCH_COFFEE_ID, gch_coffee_url

PLAYLIST = Path("freewifi")
GROUP = "今日の開催場"
LOCAL_RAW = "https://raw.githubusercontent.com/ajiousama/himitsu/main"
REGIONAL = {
    "JRA EAST WEB3 HQ": ("jra.east.hq", "jra.east", "gch_east_master.m3u8"),
    "JRA EAST WEB3 LQ": ("jra.east.lq", "jra.east", "gch_east_LQ.m3u8"),
    "JRA WEST WEB4 HQ": ("jra.west.hq", "jra.west", "gch_west_master.m3u8"),
    "JRA WEST WEB4 LQ": ("jra.west.lq", "jra.west", "gch_west_LQ.m3u8"),
    "JRA LOCAL WEB5 HQ": ("jra.local.hq", "jra.hokkaido", "gch_hokkaido_master.m3u8"),
    "JRA LOCAL WEB5 LQ": ("jra.local.lq", "jra.hokkaido", "gch_hokkaido_LQ.m3u8"),
}
REQUIRED = {
    "グリーンチャンネル MAIN HQ": (
        "jra.gch.hq",
        "https://raw.githubusercontent.com/ajiousama/himitsu/main/gchmain_master.m3u8",
    ),
    "グリーンチャンネル MAIN LQ": (
        "jra.gch.lq",
        "https://raw.githubusercontent.com/ajiousama/himitsu/main/gchmain_LQ.m3u8",
    ),
    "グリーンチャンネル (5002直)": (
        "jra.gch.hq",
        "http://67.215.237.218:5002/bs14.m3u8?gid=bs14&token=guoziyun&channel=zhongying&uin=159413&ts=0&sign=&playseek=0",
    ),
}


def main() -> None:
    text = PLAYLIST.read_text(encoding="utf-8-sig")
    start = text.find("# === TODAY_JRA_START ===")
    end = text.find("# === TODAY_JRA_END ===", start)
    if start < 0 or end < start:
        raise SystemExit("GCH always-on guard: TODAY_JRA block is missing")
    block = text[start:end]
    if ('earphone' + '1981') in block:
        raise SystemExit('GCH/JRA guard: retired external source returned')
    lines = text.splitlines()
    found = {}
    names = set(REQUIRED) | set(REGIONAL) | {GCH_COFFEE_NAME, "グリーンチャンネル（sinori）"}
    coffee_entries = []
    for index, line in enumerate(lines):
        if not line.startswith("#EXTINF:"):
            continue
        name = line.rsplit(",", 1)[-1].strip()
        candidate_url = lines[index + 1].strip() if index + 1 < len(lines) else ""
        if "coffee.linxei.biz.id/" in candidate_url:
            coffee_entries.append(name)
        if name not in names:
            continue
        dedicated = {"グリーンチャンネル MAIN HQ":"https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/public_sports/jra_quality/main_hq.webp","グリーンチャンネル MAIN LQ":"https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/public_sports/jra_quality/main_lq.webp","JRA EAST WEB3 HQ":"https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/public_sports/jra_quality/east_hq.webp","JRA EAST WEB3 LQ":"https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/public_sports/jra_quality/east_lq.webp","JRA WEST WEB4 HQ":"https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/public_sports/jra_quality/west_hq.webp","JRA WEST WEB4 LQ":"https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/public_sports/jra_quality/west_lq.webp","JRA LOCAL WEB5 HQ":"https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/public_sports/jra_quality/local_hq.webp","JRA LOCAL WEB5 LQ":"https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/public_sports/jra_quality/local_lq.webp"}
        dedicated.update({"グリーンチャンネル（sinori）":"https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/public_sports/jra_quality/sinori.webp","グリーンチャンネル (5002直)":"https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/public_sports/jra_quality/direct.webp","グリーンチャンネル（coffee）":"https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/public_sports/jra_quality/coffee.webp","グリーンチャンネル MAIN HQ":"https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/public_sports/jra_quality/main_hq.webp","グリーンチャンネル MAIN LQ":"https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/public_sports/jra_quality/main_lq.webp"})
        expected_logo = dedicated.get(name, GCH_SINORI_LOGO)
        if f'tvg-logo="{expected_logo}"' not in line:
            raise SystemExit(f"GCH logo guard: noncanonical logo: {name}")
        if name in found:
            raise SystemExit(f"GCH always-on guard: duplicate entry: {name}")
        tvg_id = re.search(r'tvg-id="([^"]+)"', line)
        group = re.search(r'group-title="([^"]+)"', line)
        url = lines[index + 1].strip() if index + 1 < len(lines) else ""
        found[name] = (tvg_id.group(1) if tvg_id else "", url, group.group(1) if group else "")
        if not (start < text.find(line) < end):
            raise SystemExit(f"GCH always-on guard: source escaped TODAY_JRA block: {name}")

    if coffee_entries != [GCH_COFFEE_NAME]:
        raise SystemExit("GCH guard: only the Coffee Green Channel may appear in FreeWiFi")
    required = dict(REQUIRED)
    required[GCH_COFFEE_NAME] = (GCH_COFFEE_ID, gch_coffee_url())
    required["グリーンチャンネル（sinori）"] = ("グリーンチャンネル_jp", "https://ri.shinori.my.id/pxx.php?shk_cid=bs14")
    for name, (expected_id, expected_url) in required.items():
        expected = (expected_id, expected_url, GROUP)
        actual = found.get(name)
        if actual != expected:
            raise SystemExit(f"GCH always-on guard: {name} missing or changed: {actual!r}")
    expected_order = ["グリーンチャンネル（sinori）","グリーンチャンネル (5002直)","グリーンチャンネル（coffee）","グリーンチャンネル MAIN HQ","グリーンチャンネル MAIN LQ","JRA EAST WEB3 HQ","JRA EAST WEB3 LQ","JRA WEST WEB4 HQ","JRA WEST WEB4 LQ","JRA LOCAL WEB5 HQ","JRA LOCAL WEB5 LQ"]
    if list(found) != [name for name in expected_order if name in found]:
        raise SystemExit("GCH/JRA guard: incorrect channel order")
    status_path = Path("today_jra_status.json")
    if status_path.is_file():
        status = json.loads(status_path.read_text(encoding="utf-8-sig"))
        active = set(status.get("active_ids") or [])
        race_active = set(status.get("race_active_ids") or [])
        regional = {"jra.east", "jra.west", "jra.hokkaido"}
        race_day = bool(race_active & regional)
        if (active & regional) != (regional if race_day else set()):
            raise SystemExit("JRA guard: all regional visibility must match any JRA race date")
        for name, (cid, family, filename) in REGIONAL.items():
            actual = found.get(name)
            # All regional routes are present on any JRA race date.
            required = race_day
            if required and actual != (cid, f"{LOCAL_RAW}/{filename}", GROUP):
                raise SystemExit(f"JRA race-date guard: {name} missing or changed: {actual!r}")
            if not required and actual is not None:
                raise SystemExit(f"JRA race-date guard: inactive source unexpectedly present: {name}")
            if not Path(filename).is_file():
                raise SystemExit(f"JRA race-date guard: local source missing: {filename}")
    for filename in ("gchmain_master.m3u8", "gchmain_LQ.m3u8"):
        if not Path(filename).is_file():
            raise SystemExit(f"GCH guard: local source missing: {filename}")
    if "haruka" in text.lower():
        raise SystemExit("GCH guard: retired HARUKA route returned")
    print("GCH/JRA local-source guard OK: MAIN HQ/LQ, 5002 and race-date regional routes")


if __name__ == "__main__":
    main()
