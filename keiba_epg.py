#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import datetime as dt
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from functools import lru_cache

import requests
from bs4 import BeautifulSoup

# ----------------------------
# 設定
# ----------------------------
DAYS = 6                         # 今日を含めて何日分EPGを作るか
NEXT_SEARCH_DAYS = 21           # 次回開催を何日先まで探すか
OUTPUT_FILE = "keiba_epg.xml"
JST = dt.timezone(dt.timedelta(hours=9))

BASE = "https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo/RaceList"

# NAR 地方競馬場
VENUES = {
    "帯広": ("03", "chihou.obihiro"),
    "門別": ("36", "chihou.mombetsu"),
    "盛岡": ("10", "chihou.morioka"),
    "水沢": ("11", "chihou.mizusawa"),
    "浦和": ("18", "chihou.urawa"),
    "船橋": ("19", "chihou.funabashi"),
    "大井": ("20", "chihou.oi"),
    "川崎": ("21", "chihou.kawasaki_keiba"),
    "金沢": ("22", "chihou.kanazawa"),
    "笠松": ("23", "chihou.kasamatsu"),
    "名古屋": ("24", "chihou.nagoya_keiba"),
    "園田": ("27", "chihou.sonoda"),
    "姫路": ("28", "chihou.himeji"),
    "高知": ("31", "chihou.kochi_keiba"),
    "佐賀": ("32", "chihou.saga"),
}

WEEKDAYS = "月火水木金土日"

session = requests.Session()
session.headers.update({
    "User-Agent": "Mozilla/5.0 (compatible; ChihouKeibaEPG/1.0)"
})


def normalize(text):
    text = unicodedata.normalize("NFKC", text or "")
    return re.sub(r"\s+", " ", text).strip()


def xml_time(d):
    return d.strftime("%Y%m%d%H%M%S +0900")


def local_today():
    return dt.datetime.now(JST).date()


@lru_cache(maxsize=None)
def fetch_races(venue_code, date_iso):
    """
    戻り値:
      list: レースあり / 非開催なら []
      None: 通信・解析失敗
    """
    race_date = dt.date.fromisoformat(date_iso)
    params = {
        "k_babaCode": venue_code,
        "k_raceDate": race_date.strftime("%Y/%m/%d"),
    }

    try:
        r = session.get(BASE, params=params, timeout=20)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"[WARN] 取得失敗 code={venue_code} date={date_iso}: {e}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    races = []

    for tr in soup.find_all("tr"):
        cells = [normalize(x.get_text(" ", strip=True)) for x in tr.find_all(["th", "td"])]
        if len(cells) < 5:
            continue

        # 例: 1R | 14:20 | | | 2歳 未勝利 | 右1700m | ...
        m_r = re.fullmatch(r"(\d{1,2})R", cells[0], re.I)
        m_t = re.fullmatch(r"(\d{1,2}):(\d{2})", cells[1])
        if not (m_r and m_t):
            continue

        race_no = int(m_r.group(1))
        start_time = cells[1]
        kind = cells[3] if len(cells) > 3 else ""
        race_name = cells[4] if len(cells) > 4 else ""
        course = cells[5] if len(cells) > 5 else ""
        heads = cells[8] if len(cells) > 8 else ""

        if not race_name:
            race_name = "競走"

        races.append({
            "race_no": race_no,
            "time": start_time,
            "kind": kind,
            "name": race_name,
            "course": course,
            "heads": heads,
        })

    races.sort(key=lambda x: x["race_no"])
    return races


def find_next_race_date(venue_code, after_date, prefetched):
    # まずEPG期間内に取得済みの日付から探す
    for d in sorted(prefetched):
        if d > after_date and prefetched[d]:
            return d

    # 期間外を必要な分だけ探す
    for n in range(1, NEXT_SEARCH_DAYS + 1):
        d = after_date + dt.timedelta(days=n)
        if d in prefetched:
            races = prefetched[d]
        else:
            races = fetch_races(venue_code, d.isoformat())
            if races is None:
                continue
            prefetched[d] = races

        if races:
            return d

        time.sleep(0.05)

    return None


def add_programme(tv, channel, start, stop, title, desc=""):
    p = ET.SubElement(
        tv, "programme",
        start=xml_time(start),
        stop=xml_time(stop),
        channel=channel,
    )
    ET.SubElement(p, "title", lang="ja").text = title
    if desc:
        ET.SubElement(p, "desc", lang="ja").text = desc


def build_epg():
    start_date = local_today()
    dates = [start_date + dt.timedelta(days=i) for i in range(DAYS)]

    tv = ET.Element("tv", {"generator-info-name": "ChihouKeibaRaceEPG"})

    # チャンネル定義
    for venue, (_, channel_id) in VENUES.items():
        c = ET.SubElement(tv, "channel", id=channel_id)
        ET.SubElement(c, "display-name").text = venue

    # 競馬場ごとに取得してEPG化
    for venue, (code, channel_id) in VENUES.items():
        print(f"=== {venue} ===")

        prefetched = {}
        for d in dates:
            races = fetch_races(code, d.isoformat())
            prefetched[d] = races
            time.sleep(0.05)

        for d in dates:
            day_start = dt.datetime.combine(d, dt.time(0, 0), JST)
            day_end = dt.datetime.combine(d, dt.time(23, 59, 59), JST)
            races = prefetched[d]

            if races is None:
                add_programme(
                    tv, channel_id, day_start, day_end,
                    f"⚠️ {venue} 情報取得失敗",
                    f"{d:%Y-%m-%d} のNARレース情報を取得できませんでした。"
                )
                continue

            if not races:
                next_date = find_next_race_date(code, d, prefetched)
                if next_date:
                    wd = WEEKDAYS[next_date.weekday()]
                    title = f"💤 {venue} 本日非開催｜次回 {next_date.month}/{next_date.day}({wd})"
                else:
                    title = f"💤 {venue} 本日非開催"

                add_programme(
                    tv, channel_id, day_start, day_end,
                    title,
                    f"{d:%Y-%m-%d} は{venue}の開催予定はありません。"
                )
                continue

            # 1R前
            first_h, first_m = map(int, races[0]["time"].split(":"))
            first_start = dt.datetime.combine(d, dt.time(first_h, first_m), JST)

            if day_start < first_start:
                first = races[0]
                add_programme(
                    tv, channel_id, day_start, first_start,
                    f"⏳ {venue} 開催待ち｜1R {first['time']}発走",
                    f"本日の{venue}は{len(races)}レース予定です。"
                )

            # 各レースを1番組にする
            for i, race in enumerate(races):
                h, m = map(int, race["time"].split(":"))
                race_start = dt.datetime.combine(d, dt.time(h, m), JST)

                if i + 1 < len(races):
                    nh, nm = map(int, races[i + 1]["time"].split(":"))
                    race_stop = dt.datetime.combine(d, dt.time(nh, nm), JST)
                else:
                    # 最終Rは発走から10分をレース枠、その後「本日開催終了」
                    race_stop = min(race_start + dt.timedelta(minutes=10), day_end)

                title = f"{race['time']} {venue}{race['race_no']}R {race['name']}"

                desc_parts = [
                    f"🏇 {venue} {race['race_no']}R",
                    f"⏰ 発走: {race['time']}",
                    f"📢 競走名: {race['name']}",
                ]
                if race["kind"]:
                    desc_parts.append(f"🏆 種類: {race['kind']}")
                if race["course"]:
                    desc_parts.append(f"📏 コース: {race['course']}")
                if race["heads"]:
                    desc_parts.append(f"🐎 頭数: {race['heads']}")

                add_programme(
                    tv, channel_id, race_start, race_stop,
                    title,
                    "\n".join(desc_parts)
                )

            # 最終R後
            last = races[-1]
            lh, lm = map(int, last["time"].split(":"))
            finish_start = dt.datetime.combine(d, dt.time(lh, lm), JST) + dt.timedelta(minutes=10)

            if finish_start < day_end:
                add_programme(
                    tv, channel_id, finish_start, day_end,
                    f"🏁 {venue} 本日開催終了",
                    f"{venue}の本日の全レースは終了しました。"
                )

    tree = ET.ElementTree(tv)
    if hasattr(ET, "indent"):
        ET.indent(tree, space="    ")
    tree.write(OUTPUT_FILE, encoding="utf-8", xml_declaration=True)
    print(f"\n完成: {OUTPUT_FILE}")


if __name__ == "__main__":
    build_epg()
