#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

JST = dt.timezone(dt.timedelta(hours=9))
GUIDES = Path("guides.xml")
UA = {"User-Agent": "Mozilla/5.0 (FreeWiFi community radio EPG)"}

STATIONS = {
    "community.FMOTOKUNI": "FMおとくに（ラジオ）",
    "community.FM845": "FM845（ラジオ）",
    "community.BARIBARI": "FMラヂオバリバリ（ラジオ）",
}

DAY_SLUGS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

# FM845's official weekday pages can be slow or unreachable from a GitHub
# runner.  Keep a snapshot of the current official weekly timetable as a
# fallback.  The live HTML is always preferred; this table is used only when
# the official host cannot be fetched/parsed.  Times before 05:00 belong to the
# following calendar day, matching FM845's 05:00 programme-day boundary.
FM845_SNAPSHOT: dict[int, list[tuple[str, str]]] = {
    0: [
        ("05:00", "令和ニューリリース"),
        ("07:00", "845名曲アルバム"),
        ("08:00", "845今月の新曲"),
        ("10:00", "ピッカピカラジオ（葛山知佳子）"),
        ("12:00", "山下忠彦LIVE！太陽のあたる場所"),
        ("13:00", "ワカバンneo"),
        ("15:00", "845歌謡ベストテン"),
        ("18:00", "木下晃一☆キラキラ"),
        ("18:30", "橘あきらとMAYUMI愛のお帰りなさい！"),
        ("19:00", "845名曲アルバム"),
        ("20:00", "845今月の新曲"),
        ("22:00", "ピッカピカラジオ（再）"),
        ("24:00", "ノンストップ演歌"),
        ("04:00", "令和ニューリリース"),
    ],
    1: [
        ("05:00", "令和ニューリリース"),
        ("07:00", "845名曲アルバム"),
        ("08:00", "845今月の新曲"),
        ("10:00", "ピッカピカラジオ（羽川英樹）"),
        ("12:00", "北岡ひろしのひとひら重ねて"),
        ("12:30", "フォークの時代"),
        ("13:00", "ワカバンneo"),
        ("15:00", "せいちゃんの昭和歌謡とグルメ探訪"),
        ("16:00", "フォークの時代"),
        ("18:00", "マグナム石井のKeep on Running Again"),
        ("18:30", "伏見で一献！"),
        ("19:00", "845名曲アルバム"),
        ("20:00", "845今月の新曲"),
        ("22:00", "ピッカピカラジオ（再）"),
        ("24:00", "ノンストップ演歌"),
        ("04:00", "令和ニューリリース"),
    ],
    2: [
        ("05:00", "令和ニューリリース"),
        ("07:00", "845名曲アルバム"),
        ("08:00", "845今月の新曲"),
        ("10:00", "ピッカピカラジオ（秀円タッチ）"),
        ("12:00", "山崎ていじのラジオオンステージ"),
        ("12:30", "フォークの時代"),
        ("13:00", "ワカバンneo"),
        ("15:00", "Dr.ヒロLab（ドクターヒロラボ）"),
        ("15:30", "フォークの時代"),
        ("16:00", "佐藤ゆかりの 今日は何色？"),
        ("16:30", "フォークの時代"),
        ("18:00", "えんか興味新々"),
        ("19:00", "FM845"),
        ("20:00", "845今月の新曲"),
        ("22:00", "ピッカピカラジオ（再）"),
        ("24:00", "ノンストップ演歌"),
        ("04:00", "令和ニューリリース"),
    ],
    3: [
        ("05:00", "令和ニューリリース"),
        ("07:00", "845名曲アルバム"),
        ("08:00", "845今月の新曲"),
        ("10:00", "ピッカピカラジオ（西田ゆい）"),
        ("12:00", "ただいまHAPPY〜ブレイクちゅ〜"),
        ("12:30", "フォークの時代"),
        ("15:00", "響竜也の歌手やっちゅうねん"),
        ("16:00", "赤坂マリアまかしとき"),
        ("17:00", "新垣健の『人生春秋』"),
        ("17:15", "Fabulous Radio"),
        ("17:25", "フォークの時代"),
        ("18:00", "えんか興味新々"),
        ("19:00", "845名曲アルバム"),
        ("20:00", "845今月の新曲"),
        ("22:00", "ピッカピカラジオ（再）"),
        ("24:00", "ノンストップ演歌"),
        ("04:00", "令和ニューリリース"),
    ],
    4: [
        ("05:00", "令和ニューリリース"),
        ("07:00", "845名曲アルバム"),
        ("08:00", "845今月の新曲"),
        ("10:00", "ピッカピカラジオ（若林奈緒子）"),
        ("12:00", "ノンストップ演歌"),
        ("13:00", "845演歌ジョッキー"),
        ("15:00", "フォークの時代"),
        ("16:00", "フォークの時代"),
        ("18:00", "えんか興味新々"),
        ("19:00", "845名曲アルバム"),
        ("20:00", "845今月の新曲"),
        ("22:00", "ピッカピカラジオ（再）"),
        ("24:00", "ノンストップ演歌"),
        ("04:00", "令和ニューリリース"),
    ],
    5: [
        ("05:00", "令和ニューリリース"),
        ("07:00", "845名曲アルバム"),
        ("08:00", "845今月の新曲"),
        ("10:00", "ノンストップ演歌"),
        ("13:00", "845演歌ジョッキー（再）"),
        ("15:00", "845歌謡ベストテン（再）"),
        ("18:00", "ノンストップ演歌"),
        ("19:00", "845名曲アルバム"),
        ("20:00", "845今月の新曲"),
        ("22:00", "人生はなさくメロディー"),
        ("22:30", "ノンストップ演歌"),
        ("04:00", "令和ニューリリース"),
    ],
    6: [
        ("05:00", "令和ニューリリース"),
        ("07:00", "845名曲アルバム"),
        ("08:00", "845今月の新曲"),
        ("10:00", "ノンストップ演歌"),
        ("13:00", "845演歌ジョッキー（再）"),
        ("15:00", "845歌謡ベストテン（再）"),
        ("18:00", "ノンストップ演歌"),
        ("19:00", "845名曲アルバム"),
        ("20:00", "845今月の新曲"),
        ("22:00", "ノンストップ演歌"),
        ("04:00", "令和ニューリリース"),
    ],
}


class _Rows(HTMLParser):
    """Tiny dependency-free HTML table reader."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "tr":
            self._row = []
        elif tag in {"td", "th"} and self._row is not None:
            self._cell = []
        elif tag == "br" and self._cell is not None:
            self._cell.append(" ")

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in {"td", "th"} and self._cell is not None and self._row is not None:
            self._row.append(_clean("".join(self._cell)))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if any(self._row):
                self.rows.append(self._row)
            self._row = None
            self._cell = None


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\u3000", " ")).strip()


def _fetch(url: str, timeout: int = 12) -> str:
    last = None
    for attempt in range(2):
        try:
            req = urllib.request.Request(url, headers=UA)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw = r.read(2 * 1024 * 1024)
            return raw.decode("utf-8", "replace")
        except Exception as exc:
            last = exc
            if attempt < 1:
                time.sleep(0.8)
    raise last  # type: ignore[misc]


def _rows(url: str) -> list[list[str]]:
    p = _Rows()
    p.feed(_fetch(url))
    return p.rows


def _at(day: dt.date, hhmm: str, *, next_day_for_24: bool = True) -> dt.datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    if h == 24 and next_day_for_24:
        return dt.datetime.combine(day + dt.timedelta(days=1), dt.time(0, m), JST)
    return dt.datetime.combine(day, dt.time(h % 24, m), JST)


def _xmltime(x: dt.datetime) -> str:
    return x.strftime("%Y%m%d%H%M%S +0900")


def _week_of_month(day: dt.date) -> int:
    return (day.day - 1) // 7 + 1


def _week_rule_allows(text: str, day: dt.date) -> bool:
    if "第" not in text or "曜" not in text:
        return True
    normalized = text.translate(str.maketrans("１２３４５", "12345"))
    nums = {int(x) for x in re.findall(r"第\s*([1-5])", normalized)}
    m = re.search(r"第(.{0,18}?)曜", normalized)
    if m:
        nums.update(int(x) for x in re.findall(r"[1-5]", m.group(1)))
    return not nums or _week_of_month(day) in nums


def _strip_personality(text: str) -> str:
    text = _clean(text)
    for marker in ("■パーソナリティ", "パーソナリティ：", "パーソナリティ:"):
        if marker in text:
            text = text.split(marker, 1)[0].strip()
    return text or "放送中"


def _otokuni(day: dt.date) -> list[tuple[dt.datetime, dt.datetime, str]]:
    slug = DAY_SLUGS[day.weekday()]
    rows = _rows(f"https://fm-otokuni.com/timetable-{slug}/")
    out: list[tuple[dt.datetime, dt.datetime, str]] = []
    rx = re.compile(r"(\d{1,2}:\d{2})\s*[〜～~\-－]\s*(\d{1,2}:\d{2})")
    for cells in rows:
        joined = " | ".join(cells)
        m = rx.search(joined)
        if not m:
            continue
        time_cell_index = next((i for i, c in enumerate(cells) if rx.search(c)), -1)
        if time_cell_index < 0:
            continue
        title = _strip_personality(" ".join(cells[time_cell_index + 1:]))
        if not title or not _week_rule_allows(title, day):
            continue
        start = _at(day, m.group(1))
        stop = _at(day, m.group(2))
        if stop <= start:
            stop += dt.timedelta(days=1)
        out.append((start, stop, title))
    uniq = {(item[0], item[1], item[2]): item for item in out}
    return sorted(uniq.values(), key=lambda x: (x[0], x[1], x[2]))


def _is_num(s: str, lo: int, hi: int) -> bool:
    return bool(re.fullmatch(r"\d{1,2}", s or "")) and lo <= int(s) <= hi


def _fm845(day: dt.date) -> list[tuple[dt.datetime, dt.datetime, str]]:
    slug = DAY_SLUGS[day.weekday()]
    rows = _rows(f"https://www.fm-845.com/timetable/{slug}.html")
    starts: list[tuple[dt.datetime, str]] = []
    current_hour: int | None = None

    for cells in rows:
        cells = [_clean(c) for c in cells if _clean(c)]
        if not cells:
            continue
        hour: int | None = None
        minute: int | None = None
        title_cells: list[str] = []
        if len(cells) >= 2 and _is_num(cells[0], 0, 24) and _is_num(cells[1], 0, 59):
            hour, minute = int(cells[0]), int(cells[1])
            current_hour = hour
            title_cells = cells[2:]
        elif current_hour is not None and _is_num(cells[0], 0, 59):
            hour, minute = current_hour, int(cells[0])
            title_cells = cells[1:]
        else:
            continue
        if not title_cells:
            continue
        title = _strip_personality(" ".join(title_cells))
        if hour == 24:
            start = dt.datetime.combine(day + dt.timedelta(days=1), dt.time(0, minute), JST)
        elif hour < 5:
            start = dt.datetime.combine(day + dt.timedelta(days=1), dt.time(hour, minute), JST)
        else:
            start = dt.datetime.combine(day, dt.time(hour, minute), JST)
        starts.append((start, title))

    by_start: dict[dt.datetime, str] = {}
    for start, title in starts:
        by_start[start] = title
    ordered = sorted(by_start.items())
    out: list[tuple[dt.datetime, dt.datetime, str]] = []
    for i, (start, title) in enumerate(ordered):
        stop = ordered[i + 1][0] if i + 1 < len(ordered) else dt.datetime.combine(day + dt.timedelta(days=1), dt.time(5, 0), JST)
        if stop > start:
            out.append((start, stop, title))
    return out


def _fm845_snapshot(day: dt.date) -> list[tuple[dt.datetime, dt.datetime, str]]:
    starts: list[tuple[dt.datetime, str]] = []
    week = _week_of_month(day)
    for hhmm, base_title in FM845_SNAPSHOT[day.weekday()]:
        h, m = (int(x) for x in hhmm.split(":"))
        title = base_title
        # Current official timetable's week-specific programmes.
        if day.weekday() == 2 and hhmm == "19:00" and week == 1:
            title = "りゅうまっぷる〜あなたの街の龍大生ガイド"
        elif day.weekday() == 4 and hhmm == "12:00" and week == 2:
            title = "なやまっちラヂオ"
        elif day.weekday() == 4 and hhmm == "15:00" and week == 1:
            title = "中森万美子の洋盤グラフィティ"

        if h == 24:
            start = dt.datetime.combine(day + dt.timedelta(days=1), dt.time(0, m), JST)
        elif h < 5:
            start = dt.datetime.combine(day + dt.timedelta(days=1), dt.time(h, m), JST)
        else:
            start = dt.datetime.combine(day, dt.time(h, m), JST)
        starts.append((start, title))

    ordered = sorted(starts)
    out: list[tuple[dt.datetime, dt.datetime, str]] = []
    end = dt.datetime.combine(day + dt.timedelta(days=1), dt.time(5, 0), JST)
    for i, (start, title) in enumerate(ordered):
        stop = ordered[i + 1][0] if i + 1 < len(ordered) else end
        if stop > start:
            out.append((start, stop, title))
    return out


def _baribari(day: dt.date) -> list[tuple[dt.datetime, dt.datetime, str]]:
    """Conservative Baribari guide: verified municipal slots + named gaps."""
    known: list[tuple[str, str, str]] = [
        ("07:00", "07:15", "今治市民の広場"),
        ("12:30", "12:45", "今治市民の広場（再）"),
        ("19:30", "19:45", "今治市民の広場（再）"),
    ]
    wd = day.weekday()
    if wd == 0:
        known.append(("07:45", "08:00", "こんにちは市役所です"))
    if wd == 2:
        known.append(("19:45", "20:00", "こんにちは市役所です（再）"))
    if wd == 3:
        known.append(("17:00", "17:15", "守るぞ☆IMABARI☆"))
    if wd == 5:
        known.append(("11:00", "11:15", "守るぞ☆IMABARI☆（再）"))
    items = [(_at(day, a), _at(day, b), t) for a, b, t in known]
    return _fill_day_gaps(day, items, "FMラヂオバリバリ")


def _fill_day_gaps(day: dt.date, items, generic_title: str):
    start_of_day = dt.datetime.combine(day, dt.time(0, 0), JST)
    end_of_day = start_of_day + dt.timedelta(days=1)
    ordered = sorted((a, b, t) for a, b, t in items if b > a)
    out = []
    cursor = start_of_day
    for start, stop, title in ordered:
        if start > cursor:
            out.append((cursor, start, generic_title))
        if stop > cursor:
            out.append((max(start, cursor), stop, title))
            cursor = max(cursor, stop)
    if cursor < end_of_day:
        out.append((cursor, end_of_day, generic_title))
    return out


def _generic_days(today: dt.date, title: str, days: int = 3):
    out = []
    for i in range(days):
        day = today + dt.timedelta(days=i)
        a = dt.datetime.combine(day, dt.time(0, 0), JST)
        out.append((a, a + dt.timedelta(days=1), title + "（番組表取得待ち）"))
    return out


def _add_channel(root: ET.Element, cid: str, name: str) -> None:
    ch = ET.SubElement(root, "channel", {"id": cid})
    ET.SubElement(ch, "display-name", {"lang": "ja"}).text = name


def _add_programmes(root: ET.Element, cid: str, rows) -> int:
    count = 0
    for start, stop, title in rows:
        pr = ET.SubElement(root, "programme", {
            "start": _xmltime(start),
            "stop": _xmltime(stop),
            "channel": cid,
        })
        ET.SubElement(pr, "title", {"lang": "ja"}).text = title
        count += 1
    return count


def main() -> int:
    if not GUIDES.exists():
        raise SystemExit("guides.xml not found")
    root = ET.parse(GUIDES).getroot()
    today = dt.datetime.now(JST).date()
    wanted = set(STATIONS)

    old_channels = {
        n.get("id"): n for n in root.findall("channel") if (n.get("id") or "") in wanted
    }
    old_programmes: dict[str, list[ET.Element]] = {cid: [] for cid in wanted}
    for n in root.findall("programme"):
        cid = n.get("channel") or ""
        if cid in wanted:
            old_programmes[cid].append(n)

    built: dict[str, list[tuple[dt.datetime, dt.datetime, str]]] = {cid: [] for cid in wanted}
    failures: list[str] = []

    # FMおとくに: official daily HTML for three days.
    try:
        rows = []
        for i in range(3):
            day = today + dt.timedelta(days=i)
            daily = _otokuni(day)
            if len(daily) < 3:
                raise RuntimeError(f"{day}: timetable parsed only {len(daily)} rows")
            rows.extend(daily)
        built["community.FMOTOKUNI"] = rows
    except Exception as exc:
        failures.append(f"FMおとくに: {type(exc).__name__}: {exc}")

    # FM845: prefer live official HTML day-by-day, but never lose detailed EPG
    # merely because www.fm-845.com times out from a GitHub runner.
    fm845_rows = []
    for i in range(3):
        day = today + dt.timedelta(days=i)
        try:
            daily = _fm845(day)
            if len(daily) < 8:
                raise RuntimeError(f"timetable parsed only {len(daily)} rows")
        except Exception as exc:
            daily = _fm845_snapshot(day)
            failures.append(
                f"FM845 {day}: official HTML unavailable ({type(exc).__name__}: {exc}); "
                "using official timetable snapshot"
            )
        fm845_rows.extend(daily)
    built["community.FM845"] = fm845_rows

    # Baribari: conservative verified municipal slots + transparent generic gaps.
    for i in range(3):
        built["community.BARIBARI"].extend(_baribari(today + dt.timedelta(days=i)))

    # A transient FMおとくに failure preserves the last good EPG; on the first
    # ever failure, show a transparent acquisition-waiting guide rather than a
    # fabricated programme title.
    cid = "community.FMOTOKUNI"
    if not built[cid]:
        if not old_programmes.get(cid):
            built[cid] = _generic_days(today, "FMおとくに")

    replacing = {cid for cid, rows in built.items() if rows}
    for n in list(root.findall("channel")):
        if (n.get("id") or "") in replacing:
            root.remove(n)
    for n in list(root.findall("programme")):
        if (n.get("channel") or "") in replacing:
            root.remove(n)

    counts = {}
    for cid in STATIONS:
        if cid not in replacing:
            counts[cid] = len(old_programmes.get(cid, []))
            continue
        _add_channel(root, cid, STATIONS[cid])
        counts[cid] = _add_programmes(root, cid, built[cid])

    ET.ElementTree(root).write(GUIDES, encoding="utf-8", xml_declaration=True)
    print("Community radio EPG merged:", counts)
    for warning in failures:
        print("Community EPG warning:", warning)

    missing = [cid for cid, count in counts.items() if count < 1]
    if missing:
        raise RuntimeError(f"community EPG missing: {missing}")
    if counts.get("community.FM845", 0) < 24:
        raise RuntimeError(f"FM845 EPG unexpectedly sparse: {counts.get('community.FM845', 0)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
