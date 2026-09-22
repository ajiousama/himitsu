"""Build a per-channel, official daily status snapshot for today's EPG.

The main generator already fetches race details.  This final verification pass is
deliberately smaller: it asks the official daily/monthly indexes only which
venues are running, so a detail-page failure cannot turn an active venue into a
false "non-event" (or a stale M3U into a false active venue).
"""

from __future__ import annotations

import datetime
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import main_epg_3days as epg


JST = datetime.timezone(datetime.timedelta(hours=9))
TODAY = datetime.datetime.now(JST).date()
DATE = TODAY.strftime("%Y%m%d")
OUT = Path("/tmp/verified_daily_status.json")


def category(ids, active=(), inactive=(), source="", verified=False, note=""):
    active = set(active)
    inactive = set(inactive)
    return {
        "source": source,
        "verified": bool(verified),
        "active": sorted(active),
        "inactive": sorted(inactive),
        "unknown": sorted(set(ids) - active - inactive),
        "note": note,
    }


def verify_keirin():
    ids = set(epg.KEIRIN_MAP.values())
    month = epg.fetch_keirin_future_month(TODAY.year, TODAY.month)
    if not month:
        return category(ids, source="KEIRIN.JP開催日程", note="月間表を取得できませんでした")
    active_names = set(month.get(DATE, {}))
    active = {epg.KEIRIN_MAP[name] for name in active_names if name in epg.KEIRIN_MAP}
    return category(
        ids,
        active=active,
        inactive=ids - active,
        source="KEIRIN.JP開催日程",
        verified=True,
    )


def verify_keiba():
    ids = set(epg.KEIBA_MAP.values())
    data = epg.fetch_nar_future_schedule(DATE)
    active_names = set(data.get("local", {}))
    active = {epg.KEIBA_MAP[name] for name in active_names if name in epg.KEIBA_MAP}
    if not active:
        # A second NAR request can be rejected even when the main generation
        # succeeded minutes earlier.  In that case certify only channels whose
        # already-generated programme contains real race data; leave every
        # other channel unknown instead of falsely declaring it inactive.
        try:
            root = ET.parse("epg.xml").getroot()
            for p in root.findall("programme"):
                cid = p.get("channel", "")
                if cid not in ids or not (p.get("start") or "").startswith(DATE):
                    continue
                text = " ".join(p.itertext())
                if re.search(r"(?:[❶❷❸❹❺❻❼❽❾❿⓫⓬]ℛ|\b(?:[1-9]|1[0-2])R\b)", text):
                    active.add(cid)
        except Exception as exc:
            return category(ids, source="地方競馬情報サイト", note=f"当日出馬表を取得できませんでした: {exc}")
        return category(
            ids,
            active=active,
            source="地方競馬情報サイト（生成済み当日出馬表）",
            verified=bool(active),
            note="再取得不能のため非開催側はunknownのまま保持します",
        )
    return category(
        ids,
        active=active,
        inactive=ids - active,
        source="地方競馬情報サイト 当日出馬表",
        verified=True,
    )


def verify_boat():
    ids = set(epg.BOAT_MAP.values())
    source = epg.fetch_text(
        epg.BOAT_OFFICIAL_INDEX_URL.format(date=DATE),
        f"BOAT VERIFY {DATE}",
    )
    if not source:
        return category(ids, source="BOAT RACE本日のレース", note="公式一覧を取得できませんでした")
    codes = epg.extract_boat_active_codes(source)
    active = {
        epg.BOAT_MAP[name]
        for code in codes
        for name in [epg.BOAT_NAME_BY_CODE.get(code)]
        if name in epg.BOAT_MAP
    }
    # The official page may legitimately be empty, but it still has the dated
    # race heading.  Do not certify a login/error page as an all-off day.
    plain = epg.strip_html_tags(source)
    page_ok = bool(codes) or ("レース情報" in plain and f"{TODAY.month}月{TODAY.day}日" in plain)
    if not page_ok:
        return category(ids, active=active, source="BOAT RACE本日のレース", note="公式一覧の形式を確認できませんでした")
    return category(
        ids,
        active=active,
        inactive=ids - active,
        source="BOAT RACE本日のレース",
        verified=True,
    )


def verify_autorace():
    ids = set(epg.AUTO_MAP.values())
    status_path = Path("/tmp/autorace_official_status.json")
    if not status_path.exists():
        return category(ids, source="AutoRace.JP公式出走表", note="直前検証結果がありません")
    try:
        data = json.loads(status_path.read_text(encoding="utf-8"))
    except Exception as exc:
        return category(ids, source="AutoRace.JP公式出走表", note=f"検証結果を読めません: {exc}")
    if data.get("date") != DATE:
        return category(ids, source="AutoRace.JP公式出走表", note="検証結果の日付が違います")
    active = set(data.get("active", [])) & ids
    inactive = set(data.get("inactive", [])) & ids
    return category(
        ids,
        active=active,
        inactive=inactive,
        source="AutoRace.JP公式出走表",
        verified=bool(active or inactive),
        note="一部取得不能はunknownのまま保持します",
    )


def main():
    result = {
        "date": DATE,
        "generated_at": datetime.datetime.now(JST).isoformat(),
        "categories": {
            "keirin": verify_keirin(),
            "keiba": verify_keiba(),
            "autorace": verify_autorace(),
            "boat": verify_boat(),
        },
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for name, info in result["categories"].items():
        print(
            f"VERIFY {name}: verified={info['verified']} "
            f"active={len(info['active'])} inactive={len(info['inactive'])} "
            f"unknown={len(info['unknown'])}"
        )
        if info.get("note"):
            print(f"  {info['note']}")
    print(f"Verified daily status: {OUT}")


if __name__ == "__main__":
    main()
