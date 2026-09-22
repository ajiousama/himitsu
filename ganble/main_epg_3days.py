import datetime
import html as html_lib
import json
import re
import urllib.parse
import urllib.request
import http.cookiejar
import xml.etree.ElementTree as ET
from html.parser import HTMLParser

KEIRIN_MAP = {
    "函館": "keirin.hakodate", "青森": "keirin.aomori", "いわき平": "keirin.iwakitaira", "弥彦": "keirin.yahiko",
    "前橋": "keirin.maebashi", "取手": "keirin.toride", "宇都宮": "keirin.utsunomiya", "大宮": "keirin.omiya",
    "西武園": "keirin.seibuen", "京王閣": "keirin.keiogatsu", "立川": "keirin.tachikawa", "松戸": "keirin.matsudo",
    "川崎": "keirin.kawasaki", "平塚": "keirin.hiratsuka", "小田原": "keirin.odawara", "伊東": "keirin.ito",
    "静岡": "keirin.shizuoka", "名古屋": "keirin.nagoya", "岐阜": "keirin.gifu", "大垣": "keirin.ogaki",
    "豊橋": "keirin.toyohashi", "松阪": "keirin.matsusaka", "四日市": "keirin.yokkaichi", "富山": "keirin.toyama",
    "福井": "keirin.fukui", "奈良": "keirin.nara", "岸和田": "keirin.kishiwada", "和歌山": "keirin.wakayama",
    "玉野": "keirin.tamano", "広島": "keirin.hiroshima", "防府": "keirin.hofu", "小松島": "keirin.komatsushima",
    "松山": "keirin.matsuyama", "高知": "keirin.kochi", "高松": "keirin.takamatsu", "向日町": "keirin.mukomachi",
    "小倉": "keirin.kokura", "久留米": "keirin.kurume", "武雄": "keirin.takeo", "佐世保": "keirin.sasebo",
    "別府": "keirin.beppu", "熊本": "keirin.kumamoto", "千葉": "keirin.pist6"
}
KEIBA_MAP = {
    "帯広": "chihou.obihiro", "門別": "chihou.mombetsu", "盛岡": "chihou.morioka", "水沢": "chihou.mizusawa",
    "浦和": "chihou.urawa", "船橋": "chihou.funabashi", "大井": "chihou.oi", "川崎": "chihou.kawasaki_keiba",
    "金沢": "chihou.kanazawa", "名古屋": "chihou.nagoya_keiba", "笠松": "chihou.kasamatsu", "園田": "chihou.sonoda",
    "姫路": "chihou.himeji", "高知": "chihou.kochi_keiba", "佐賀": "chihou.saga",
}

JRA_STREAM_MAP = {
    "JRA EAST": "jra.east",
    "JRA WEST": "jra.west",
    "JRA HOKKAIDO": "jra.hokkaido",
}

JRA_VENUE_TO_STREAM = {
    "東京": "JRA EAST", "中山": "JRA EAST", "新潟": "JRA EAST", "福島": "JRA EAST",
    "京都": "JRA WEST", "阪神": "JRA WEST", "中京": "JRA WEST", "小倉": "JRA WEST",
    "札幌": "JRA HOKKAIDO", "函館": "JRA HOKKAIDO",
}

AUTO_MAP = {"川口": "auto.kawaguchi", "伊勢崎": "auto.isesaki", "浜松": "auto.hamamatsu", "飯塚": "auto.iizuka", "山陽": "auto.sanyo"}


NAR_VENUE_CODES = {
    "帯広": "03", "盛岡": "10", "水沢": "11", "浦和": "18", "船橋": "19",
    "大井": "20", "川崎": "21", "金沢": "22", "笠松": "23", "名古屋": "24",
    "園田": "27", "姫路": "28", "高知": "31", "佐賀": "32", "門別": "36",
}

NAR_RACE_LIST_URL = (
    "https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo/RaceList"
    "?k_babaCode={code}&k_raceDate={date}"
)



BOAT_MAP = {
    "01 桐生": "boat.kiryu",
    "02 戸田": "boat.toda",
    "03 江戸川": "boat.edogawa",
    "04 平和島": "boat.heiwajima",
    "05 多摩川": "boat.tamagawa",
    "06 浜名湖": "boat.hamanako",
    "07 蒲郡": "boat.gamagori",
    "08 常滑": "boat.tokoname",
    "09 津": "boat.tsu",
    "10 三国": "boat.mikuni",
    "11 びわこ": "boat.biwako",
    "12 住之江": "boat.suminoe",
    "13 尼崎": "boat.amagasaki",
    "14 鳴門": "boat.naruto",
    "15 丸亀": "boat.marugame",
    "16 児島": "boat.kojima",
    "17 宮島": "boat.miyajima",
    "18 徳山": "boat.tokuyama",
    "19 下関": "boat.shimonoseki",
    "20 若松": "boat.wakamatsu",
    "21 芦屋": "boat.ashiya",
    "22 福岡": "boat.fukuoka",
    "23 からつ": "boat.karatsu",
    "24 大村": "boat.omura",
}



BOAT_OFFICIAL_INDEX_URL = (
    "https://www.boatrace.jp/owpc/pc/race/index?hd={date}"
)

BOAT_OFFICIAL_RACEINDEX_URL = (
    "https://www.boatrace.jp/owpc/pc/race/raceindex?hd={date}&jcd={code}"
)

BOAT_CODE_BY_NAME = {
    "01 桐生": "01",
    "02 戸田": "02",
    "03 江戸川": "03",
    "04 平和島": "04",
    "05 多摩川": "05",
    "06 浜名湖": "06",
    "07 蒲郡": "07",
    "08 常滑": "08",
    "09 津": "09",
    "10 三国": "10",
    "11 びわこ": "11",
    "12 住之江": "12",
    "13 尼崎": "13",
    "14 鳴門": "14",
    "15 丸亀": "15",
    "16 児島": "16",
    "17 宮島": "17",
    "18 徳山": "18",
    "19 下関": "19",
    "20 若松": "20",
    "21 芦屋": "21",
    "22 福岡": "22",
    "23 からつ": "23",
    "24 大村": "24",
}

BOAT_NAME_BY_CODE = {code: name for name, code in BOAT_CODE_BY_NAME.items()}

# EPG generation window.
# Always generate today + tomorrow + the day after tomorrow.
EPG_DAYS = 3

# 日付更新後、当日データの自動取得・反映が完了する基準時刻。
# 現在の当日更新は08:00運用。
DATA_READY_TIME = "08:00"

ICON_MAP = {
    "keirin": "🚲",
    "keiba": "🏇",
    "auto": "🏍️",
    "boat": "🚤",
}


GCH_GUIDES_URL = (
    "https://raw.githubusercontent.com/ajiousama/himitsu/main/guides.xml"
)
GCH_TVG_ID = "jra.gch"
GCH_DISPLAY_NAME = "グリーンチャンネル"


def format_time_xml(dt):
    return dt.strftime("%Y%m%d%H%M%S +0900")


def fetch_json(url, label):
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Cache-Control": "no-cache",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            text = response.read().decode("utf-8-sig")
        data = json.loads(text)
        print(f"{label}: 取得成功")
        return data
    except Exception as e:
        print(f"{label}: 取得失敗: {e}")
        return {}



R_CIRCLED = {
    1:"❶", 2:"❷", 3:"❸", 4:"❹", 5:"❺", 6:"❻",
    7:"❼", 8:"❽", 9:"❾", 10:"❿", 11:"⓫", 12:"⓬",
}

def race_no_deco(race_no):
    try:
        n = int(str(race_no).strip())
    except Exception:
        return f"{race_no}R"
    return f"{R_CIRCLED.get(n, str(n))}ℛ"

def race_front_deco(name="", race_type="", grade="", is_semi=False, is_final=False):
    s = " ".join(str(x or "") for x in (name, race_type, grade))
    if is_final or any(k in s for k in ("優勝戦", "決勝", "ファイナル")):
        return "🏆決勝🏆"
    if is_semi or "準決" in s:
        return "🔥準決勝🔥"
    if "GⅠ" in s or "GI" in s or "ＧⅠ" in s:
        return "👑GⅠ👑"
    if "GⅡ" in s or "GII" in s or "ＧⅡ" in s:
        return "✨GⅡ✨"
    if "GⅢ" in s or "GIII" in s or "ＧⅢ" in s:
        return "🌟GⅢ🌟"
    return ""

def decorate_race_title(title, race_no, name="", race_type="", grade="", is_semi=False, is_final=False):
    front = race_front_deco(name, race_type, grade, is_semi, is_final)
    rn = race_no_deco(race_no)
    # 既存タイトル中の「1R」「12R」等は重複を避けるため削る
    cleaned = re.sub(rf"(?<!\d){re.escape(str(race_no))}\s*R\b", "", str(title), count=1, flags=re.I)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return " ".join(x for x in (front, rn, cleaned) if x)

def add_programme(tv, channel, start_dt, stop_dt, title, desc=""):
    if stop_dt <= start_dt:
        return None

    prog = ET.SubElement(
        tv,
        "programme",
        start=format_time_xml(start_dt),
        stop=format_time_xml(stop_dt),
        channel=channel,
    )
    ET.SubElement(prog, "title", lang="ja").text = title

    if desc:
        ET.SubElement(prog, "desc", lang="ja").text = desc

    return prog


def non_event_title(venue, category):
    icon = {"JRA":"🐴","競馬":"🐴","オートレース":"🏍️","競輪":"🚲","ボートレース":"🚤"}.get(category, "⭐")
    return f"🌼{icon} 本日は開催していません 💤🍀 {venue}（{category}）"

def finished_title(venue, category):
    icon = {"JRA":"🐴","競馬":"🐴","オートレース":"🏍️","競輪":"🚲","ボートレース":"🚤"}.get(category, "⭐")
    return f"🏁✨ 本日の開催は終了しました {icon}🌙 {venue}（{category}）"

def preparing_title(venue, category):
    return f"🔄 ただ今データ取得準備中です。 {venue}（{category}）"

def day_emoji(day_type):
    return {
        "モーニング": "🌅",
        "通常": "☀️",
        "デイ": "☀️",
        "薄暮": "🌇",
        "サマータイム": "🌇",
        "ナイター": "🌙",
        "ミッドナイト": "⭐",
    }.get(day_type, "☀️")


def build_manual_category(
    tv,
    date_str,
    category,
    target_map,
    cat_data,
    JST,
    today_display,
):
    cat_label = {
        "keirin": "競輪",
        "keiba": "競馬",
        "auto": "オートレース",
    }.get(category, "")

    for v_name, tvg_id in target_map.items():
        day_start = datetime.datetime.strptime(
            f"{date_str} {DATA_READY_TIME}", "%Y%m%d %H:%M"
        ).replace(tzinfo=JST)

        day_end = datetime.datetime.strptime(
            f"{date_str} 23:59", "%Y%m%d %H:%M"
        ).replace(tzinfo=JST)

        if v_name not in cat_data:
            add_programme(
                tv,
                tvg_id,
                day_start,
                day_end,
                non_event_title(v_name, cat_label),
                f"本日は{v_name}での開催予定はありません。",
            )
            continue

        info = cat_data[v_name]
        is_girls = info.get("is_girls", False)
        day_type = info.get("day_type", "デイ")
        emoji = day_emoji(day_type)
        girls_tag = "💛ガールズ" if is_girls else ""

        grade_list = [
            "JpnIII", "JpnII", "JpnI",
            "GIII", "GII", "GI",
            "FII", "FI", "SG",
        ]
        grade_found = next(
            (g for g in grade_list if g in info["desc"]),
            "",
        )

        day_match_str = ""
        for term in [
            "初日", "2日目", "3日目", "4日目",
            "5日目", "決勝戦", "最終日",
        ]:
            if term in info["desc"]:
                day_match_str = term
                break

        match_text = (
            "🏆 決勝戦"
            if "決勝戦" in info["desc"]
            else day_match_str
        )

        grade_prefix = f"【{grade_found}】" if grade_found else ""

        title_parts = [
            grade_prefix,
            "🔴 LIVE",
            v_name,
            f"{emoji}{day_type}",
            match_text,
            girls_tag,
            f"（{cat_label}）",
        ]
        title_live = " ".join(p for p in title_parts if p)

        start_dt = datetime.datetime.strptime(
            f"{date_str} {info['start']}", "%Y%m%d %H:%M"
        ).replace(tzinfo=JST)

        end_dt = datetime.datetime.strptime(
            f"{date_str} {info['end']}", "%Y%m%d %H:%M"
        ).replace(tzinfo=JST)

        if end_dt <= start_dt:
            end_dt += datetime.timedelta(days=1)

        pre_start = start_dt - datetime.timedelta(minutes=10)
        post_end = end_dt + datetime.timedelta(minutes=10)

        desc_text = (
            f"{ICON_MAP.get(category, '⭐')} 開催地: {v_name} ({day_type})\n"
            f"🏆 グレード: {grade_found if grade_found else '通常開催'}\n"
            f"✨ ガールズ: {'あり 💛' if is_girls else 'なし'}\n"
            f"📢 内容: {info['desc']}\n"
            f"⏰ 時間: {info['start']} - {info['end']}\n"
            f"📅 日付: {today_display}"
        )

        if day_start < pre_start:
            add_programme(
                tv,
                tvg_id,
                day_start,
                pre_start,
                f"⏳ 待機 {v_name} ({emoji}{day_type} "
                f"1R {info['start']}開始)（{cat_label}）",
                desc_text,
            )

        add_programme(
            tv,
            tvg_id,
            max(pre_start, day_start),
            post_end,
            title_live,
            desc_text,
        )

        if post_end < day_end:
            add_programme(
                tv,
                tvg_id,
                post_end,
                day_end,
                finished_title(v_name, cat_label),
                f"{v_name} ({day_type}) の放送は終了しました。",
            )



def infer_local_keiba_day_type(races):
    if not races:
        return "デイ"
    try:
        first_hour = int(races[0].get("time", "12:00").split(":")[0])
        last_hour = int(races[-1].get("time", "17:00").split(":")[0])
    except Exception:
        return "デイ"
    if first_hour < 10:
        return "モーニング"
    if last_hour >= 19 or first_hour >= 14:
        return "ナイター"
    if last_hour >= 17:
        return "薄暮"
    return "デイ"


def fetch_nar_future_schedule(date_str):
    """NAR公式の指定日出馬表から地方競馬の各R時刻・名称を取得する。"""
    date_param = f"{date_str[:4]}/{date_str[4:6]}/{date_str[6:8]}"
    encoded_date = urllib.parse.quote(date_param, safe="")
    local = {}

    for venue, code in NAR_VENUE_CODES.items():
        url = NAR_RACE_LIST_URL.format(code=code, date=encoded_date)
        source = fetch_text(url, f"NAR {date_str} {venue}")
        if not source:
            continue

        plain = strip_html_tags(source)
        if venue not in plain or "当日メニュー" not in plain:
            continue

        row_re = re.compile(
            r"\b(\d{1,2})R\b\s+([0-2]?\d:[0-5]\d)\s+(.*?)"
            r"(?=\s+\d{1,2}R\s+[0-2]?\d:[0-5]\d|\s+重賞競走優勝馬検索|\Z)",
            flags=re.S,
        )
        races_by_no = {}
        for m in row_re.finditer(plain):
            race_no = int(m.group(1))
            if not 1 <= race_no <= 12:
                continue
            hhmm = m.group(2)
            if len(hhmm) == 4:
                hhmm = "0" + hhmm
            tail = re.sub(r"\s+", " ", m.group(3)).strip()
            name = re.split(
                r"\s+(?:右|左|直線)\d+m|\s+オッズ\b|\s+映像\b|\s+成績\b",
                tail,
                maxsplit=1,
            )[0].strip()[:160]
            races_by_no[race_no] = {
                "race": str(race_no),
                "time": hhmm,
                "name": name or "競走",
                "race_type": "一般",
                "icon": "🐎",
                "main": race_no == 12,
            }

        races = [races_by_no[n] for n in sorted(races_by_no)]
        local[venue] = {
            "day_type": infer_local_keiba_day_type(races) if races else "デイ",
            "races": races,
            "source": "NAR公式",
            "confirmed": True,
        }

    return {
        "date": date_str,
        "updated_at": datetime.datetime.now(
            datetime.timezone(datetime.timedelta(hours=9))
        ).isoformat(),
        "jra": {},
        "local": local,
    }


def fetch_nar_epg_days(today_date, days):
    out = {}
    for offset in range(days):
        d = today_date + datetime.timedelta(days=offset)
        date_str = d.strftime("%Y%m%d")
        print(f"NAR指定日: {date_str} ...", end="", flush=True)
        data = fetch_nar_future_schedule(date_str)
        out[date_str] = data
        print(f" {len(data.get('local', {}))}場")
    return out


def build_keiba_race_epg(
    tv,
    date_str,
    keiba_data,
    JST,
    today_display,
):
    """
    指定日の競馬データの各Rを1番組としてEPG化。
    その日のJSONが無い場合は False を返して手入力へフォールバック。
    """
    if not keiba_data:
        return False

    if keiba_data.get("date") != date_str:
        return False

    merged = {}

    for category_key in ("jra", "local"):
        for venue, info in keiba_data.get(category_key, {}).items():
            merged[venue] = {
                **info,
                "_category": category_key,
            }

    if not merged:
        return False

    handled = set()

    for venue, info in merged.items():
        tvg_id = KEIBA_MAP.get(venue)
        if not tvg_id:
            print(f"KEIBA: tvg-id未登録: {venue}")
            continue

        races = info.get("races", [])
        if not races:
            if info.get("confirmed"):
                handled.add(venue)
                add_provisional_event(
                    tv, tvg_id, date_str, venue, "地方競馬", "🏇",
                    info.get("day_type", "デイ"), JST, today_display,
                    extra_title="開催予定",
                    extra_desc=["NAR公式で開催を確認済み。各R時刻は未公表または未取得です。"],
                )
            continue

        handled.add(venue)

        day_type = info.get("day_type", "デイ")
        emoji = day_emoji(day_type)
        category_name = "JRA" if info.get("_category") == "jra" else "地方競馬"

        day_start = datetime.datetime.strptime(
            f"{date_str} {DATA_READY_TIME}", "%Y%m%d %H:%M"
        ).replace(tzinfo=JST)

        day_end = datetime.datetime.strptime(
            f"{date_str} 23:59", "%Y%m%d %H:%M"
        ).replace(tzinfo=JST)

        race_times = []
        for race in races:
            time_text = race.get("time", "")
            try:
                dt = datetime.datetime.strptime(
                    f"{date_str} {time_text}", "%Y%m%d %H:%M"
                ).replace(tzinfo=JST)
            except Exception:
                continue
            race_times.append((race, dt))

        if not race_times:
            continue

        first_race_dt = race_times[0][1]
        pre_start = max(
            day_start,
            first_race_dt - datetime.timedelta(minutes=20),
        )

        if day_start < pre_start:
            add_programme(
                tv,
                tvg_id,
                day_start,
                pre_start,
                f"⏳ 待機 {venue} {emoji}{day_type}",
                f"{category_name} {venue}\n"
                f"1R発走予定 {race_times[0][0].get('time', '')}\n"
                f"📅 {today_display}",
            )

        # 各Rを「発走10分前～次R発走10分前」で連続表示
        for idx, (race, start_time) in enumerate(race_times):
            block_start = max(
                pre_start,
                start_time - datetime.timedelta(minutes=10),
            )

            if idx + 1 < len(race_times):
                next_time = race_times[idx + 1][1]
                block_stop = next_time - datetime.timedelta(minutes=10)
            else:
                block_stop = start_time + datetime.timedelta(minutes=30)

            if block_stop <= block_start:
                block_stop = start_time + datetime.timedelta(minutes=15)

            race_no = race.get("race", "")
            race_name = race.get("name", "").strip()
            race_type = race.get("race_type", "一般")
            icon = race.get("icon", "🐎")
            main = bool(race.get("main"))
            conditions = race.get("conditions", "").strip()

            main_mark = "🏆 MAIN " if main else ""
            display_name = race_name if race_name else race_type

            # Visible EPG title:
            # venue / R / start / official race title / class or conditions.
            title_parts = [
                f"{main_mark}{icon}".strip(),
                venue,
                f"{race_no}R",
                f"{race.get('time', '')}発走",
                display_name,
            ]

            if race_type and race_type not in {"一般", display_name}:
                title_parts.append(f"【{race_type}】")

            if (
                conditions
                and conditions != race_name
                and conditions != race_type
                and conditions not in display_name
            ):
                title_parts.append(conditions)

            title = " ".join(x for x in title_parts if x).strip()

            desc_lines = [
                f"{category_name} {venue}",
                f"{emoji} 開催区分: {day_type}",
                f"⏰ 発走予定: {race.get('time', '')}",
                f"🏷️ 種別: {race_type}",
            ]

            if race_name:
                desc_lines.append(f"📢 レース名: {race_name}")

            if conditions and conditions != race_name:
                desc_lines.append(f"📋 条件: {conditions}")

            if main:
                desc_lines.append("🏆 メインレース")

            desc_lines.append(f"📅 {today_display}")

            add_programme(
                tv,
                tvg_id,
                block_start,
                min(block_stop, day_end),
                title,
                "\n".join(desc_lines),
            )

        finish_start = race_times[-1][1] + datetime.timedelta(minutes=30)

        if finish_start < day_end:
            add_programme(
                tv,
                tvg_id,
                finish_start,
                day_end,
                finished_title(venue, "競馬"),
                f"{venue}の本日の競馬は全て終了しました。",
            )

    # JSONに無い地方競馬チャンネルは非開催表示。
    # JRA系は別処理、GCHは guides.xml から取得するためここでは除外。
    for venue, tvg_id in KEIBA_MAP.items():
        if venue in {"ＪＲＡ公式", "ＪＲＡグリーン"}:
            continue
        if venue in handled:
            continue

        day_start = datetime.datetime.strptime(
            f"{date_str} {DATA_READY_TIME}", "%Y%m%d %H:%M"
        ).replace(tzinfo=JST)

        day_end = datetime.datetime.strptime(
            f"{date_str} 23:59", "%Y%m%d %H:%M"
        ).replace(tzinfo=JST)

        add_programme(
            tv,
            tvg_id,
            day_start,
            day_end,
            non_event_title(venue, "競馬"),
            f"本日は{venue}のレース情報を取得していません。",
        )

    print(f"KEIBA EPG: {len(handled)}場を各R単位で生成")
    return True



def build_keirin_race_epg(
    tv,
    date_str,
    keirin_data,
    JST,
    today_display,
):
    if not keirin_data or keirin_data.get("date") != date_str:
        return False

    venues = keirin_data.get("venues", {})
    if not venues:
        return False

    handled = set()

    for venue, info in venues.items():
        tvg_id = KEIRIN_MAP.get(venue) or info.get("tvg_id", "")
        if not tvg_id:
            print(f"KEIRIN: tvg-id未登録: {venue}")
            continue

        races = info.get("races", [])
        if not races:
            continue

        race_times = []
        for race in races:
            try:
                dt = datetime.datetime.strptime(
                    f"{date_str} {race.get('time','')}",
                    "%Y%m%d %H:%M",
                ).replace(tzinfo=JST)
            except Exception:
                continue
            race_times.append((race, dt))

        if not race_times:
            continue

        handled.add(venue)

        day_type = info.get("day_type", "デイ")
        day_icon = info.get("day_emoji", day_emoji(day_type))
        grade = info.get("grade", "")
        event_name = clean_epg_meta_text(info.get("event_name", ""))
        event_day = clean_epg_meta_text(info.get("event_day", ""))

        day_start = datetime.datetime.strptime(
            f"{date_str} {DATA_READY_TIME}", "%Y%m%d %H:%M"
        ).replace(tzinfo=JST)
        day_end = datetime.datetime.strptime(
            f"{date_str} 23:59", "%Y%m%d %H:%M"
        ).replace(tzinfo=JST)

        pre_start = max(
            day_start,
            race_times[0][1] - datetime.timedelta(minutes=20),
        )

        if day_start < pre_start:
            add_programme(
                tv, tvg_id, day_start, pre_start,
                f"⏳ 待機 {venue} {day_icon}{day_type}",
                "\n".join(
                    x for x in [
                        f"🚲 競輪 {venue}",
                        f"{grade} {event_name}".strip(),
                        event_day,
                        f"1R発走予定 {race_times[0][0].get('time','')}",
                        f"📅 {today_display}",
                    ] if x
                ),
            )

        for idx, (race, start_time) in enumerate(race_times):
            block_start = max(
                pre_start,
                start_time - datetime.timedelta(minutes=8),
            )

            if idx + 1 < len(race_times):
                next_time = race_times[idx + 1][1]
                block_stop = next_time - datetime.timedelta(minutes=8)
            else:
                block_stop = start_time + datetime.timedelta(minutes=25)

            if block_stop <= block_start:
                block_stop = start_time + datetime.timedelta(minutes=12)

            race_name = race.get("name", "").strip() or "競走"
            race_no = race.get("race", "")
            main = bool(race.get("main"))
            girls = bool(race.get("girls"))

            title_parts = []
            if main:
                title_parts.append("🏆 MAIN")
            if girls:
                title_parts.append("💛")
            else:
                title_parts.append("🚲")
            if grade and main:
                title_parts.append(f"【{grade}】")
            title_parts.append(f"{venue} {race_no}R")
            title_parts.append(f"{race.get('time', '')}発走")
            # Keep the exact source race name, e.g. A級予選 / 一次予選 / 準決勝 / 決勝.
            title_parts.append(race_name)

            race_class = race.get("race_class", "").strip()
            if race_class and race_class not in race_name:
                title_parts.append(f"【{race_class}】")

            desc_lines = [
                f"🚲 競輪 {venue}",
                f"{day_icon} 開催区分: {day_type}",
                f"⏰ 発走予定: {race.get('time','')}",
                f"🏷️ {race.get('race_class','競輪')}",
            ]
            if grade:
                desc_lines.append(f"🏆 グレード: {grade}")
            if event_name:
                desc_lines.append(f"📢 開催名: {event_name}")
            if event_day:
                desc_lines.append(f"📅 開催日次: {event_day}")
            if girls:
                desc_lines.append("💛 ガールズ")
            is_semi = bool(race.get("is_semi")) or "準決" in race_name
            is_final = bool(race.get("is_final")) and not is_semi

            if is_semi:
                desc_lines.append("🔥 準決勝")
            if is_final:
                desc_lines.append("🏆 決勝")
            if main:
                desc_lines.append("🏆 メインレース")

            add_programme(
                tv,
                tvg_id,
                block_start,
                min(block_stop, day_end),
                " ".join(x for x in title_parts if x),
                "\n".join(desc_lines),
            )

        finish = race_times[-1][1] + datetime.timedelta(minutes=25)
        if finish < day_end:
            add_programme(
                tv, tvg_id, finish, day_end,
                finished_title(venue, "競輪"),
                f"{venue}の本日の競輪は全て終了しました。",
            )

    print(f"KEIRIN EPG: {len(handled)}場を各R単位で生成")
    return True


def clean_epg_meta_text(value):
    """Drop broken metadata such as a lone Japanese parenthesis from EPG."""
    s = re.sub(r"\s+", " ", str(value or "")).strip()
    if not s:
        return ""
    s = s.strip(" \t\r\n-|｜()（）[]【】『』「」・:：,，.。")
    if not s:
        return ""
    if not re.search(r"[0-9A-Za-zぁ-んァ-ヶ一-龠々〆ヶ]", s):
        return ""
    return s


def build_autorace_race_epg(
    tv,
    date_str,
    autorace_data,
    JST,
    today_display,
):
    if not autorace_data or autorace_data.get("date") != date_str:
        return False

    venues = autorace_data.get("venues", {})
    if not venues:
        return False

    handled = set()

    for venue, info in venues.items():
        tvg_id = AUTO_MAP.get(venue) or info.get("tvg_id", "")
        if not tvg_id:
            print(f"AUTORACE: tvg-id未登録: {venue}")
            continue

        races = info.get("races", [])
        if not races:
            continue

        race_times = []
        for race in races:
            try:
                dt = datetime.datetime.strptime(
                    f"{date_str} {race.get('time','')}",
                    "%Y%m%d %H:%M",
                ).replace(tzinfo=JST)
            except Exception:
                continue
            race_times.append((race, dt))

        if not race_times:
            continue

        handled.add(venue)

        day_type = info.get("day_type", "デイ")
        day_icon = info.get("day_emoji", day_emoji(day_type))
        grade = info.get("grade", "")
        event_name = info.get("event_name", "")
        event_day = info.get("event_day", "")

        day_start = datetime.datetime.strptime(
            f"{date_str} {DATA_READY_TIME}", "%Y%m%d %H:%M"
        ).replace(tzinfo=JST)
        day_end = datetime.datetime.strptime(
            f"{date_str} 23:59", "%Y%m%d %H:%M"
        ).replace(tzinfo=JST)

        pre_start = max(
            day_start,
            race_times[0][1] - datetime.timedelta(minutes=20),
        )

        if day_start < pre_start:
            add_programme(
                tv, tvg_id, day_start, pre_start,
                f"⏳ 待機 {venue} {day_icon}{day_type}",
                "\n".join(
                    x for x in [
                        f"🏍️ オートレース {venue}",
                        f"{grade} {event_name}".strip(),
                        event_day,
                        f"1R発走予定 {race_times[0][0].get('time','')}",
                        f"📅 {today_display}",
                    ] if x
                ),
            )

        for idx, (race, start_time) in enumerate(race_times):
            block_start = max(
                pre_start,
                start_time - datetime.timedelta(minutes=8),
            )

            if idx + 1 < len(race_times):
                next_time = race_times[idx + 1][1]
                block_stop = next_time - datetime.timedelta(minutes=8)
            else:
                block_stop = start_time + datetime.timedelta(minutes=25)

            if block_stop <= block_start:
                block_stop = start_time + datetime.timedelta(minutes=12)

            race_no = race.get("race", "")
            race_name = race.get("name", "").strip() or race.get("race_type", "競走")
            raw_main = bool(race.get("main"))
            is_semi = bool(race.get("is_semi")) or "準決" in race_name
            is_final = (
                bool(race.get("is_final"))
                or "優勝" in race_name
                or "決勝" in race_name
            ) and not is_semi
            is_special_main = any(
                word in race_name
                for word in ("特選", "特別選抜", "選抜戦")
            )
            main = raw_main and (is_final or is_special_main)
            icon = race.get("icon", "🏍️")

            title_parts = []
            if main:
                title_parts.append("🏆 MAIN")
            title_parts.append(icon)
            if grade and main:
                title_parts.append(f"【{grade}】")
            title_parts.append(f"{venue} {race_no}R")
            title_parts.append(f"{race.get('time', '')}発走")
            # Keep the exact source race title/stage, e.g. 一次予選 / 準決勝 / 優勝戦.
            title_parts.append(race_name)

            race_type = race.get("race_type", "").strip()
            if race_type and race_type not in race_name:
                title_parts.append(f"【{race_type}】")

            desc_lines = [
                f"🏍️ オートレース {venue}",
                f"{day_icon} 開催区分: {day_type}",
                f"⏰ 発走予定: {race.get('time','')}",
                f"🏷️ 種別: {race.get('race_type','')}",
            ]
            if grade:
                desc_lines.append(f"🏆 グレード: {grade}")
            if event_name:
                desc_lines.append(f"📢 開催名: {event_name}")
            if event_day:
                desc_lines.append(f"📅 開催日次: {event_day}")
            if is_semi:
                desc_lines.append("🔥 準決勝")
            if is_final:
                desc_lines.append("🏆 優勝戦")
            if main:
                desc_lines.append("🏆 メインレース")

            add_programme(
                tv,
                tvg_id,
                block_start,
                min(block_stop, day_end),
                " ".join(x for x in title_parts if x),
                "\n".join(desc_lines),
            )

        finish = race_times[-1][1] + datetime.timedelta(minutes=25)
        if finish < day_end:
            add_programme(
                tv, tvg_id, finish, day_end,
                finished_title(venue, "オートレース"),
                f"{venue}の本日のオートレースは全て終了しました。",
            )

    print(f"AUTORACE EPG: {len(handled)}場を各R単位で生成")
    return True


def parse_xmltv_datetime(value, default_tz):
    """XMLTV start/stop (YYYYMMDDHHMMSS +0900 等)をtimezone付きdatetimeへ変換。"""
    s = str(value or "").strip()
    m = re.match(r"^(\d{8,14})\s*([+-]\d{4})?", s)
    if not m:
        return None

    digits = m.group(1)
    offset = m.group(2)

    if len(digits) == 8:
        digits += "000000"
    elif len(digits) == 10:
        digits += "0000"
    elif len(digits) == 12:
        digits += "00"
    elif len(digits) != 14:
        return None

    try:
        if offset:
            return datetime.datetime.strptime(
                f"{digits} {offset}",
                "%Y%m%d%H%M%S %z",
            )
        return datetime.datetime.strptime(
            digits,
            "%Y%m%d%H%M%S",
        ).replace(tzinfo=default_tz)
    except Exception:
        return None


def normalize_channel_name(value):
    return re.sub(r"[\s　]+", "", str(value or "")).strip()


def import_gch_from_guides(tv, today_date, days, JST):
    """
    karenda-jp guides.xml からグリーンチャンネルだけを抽出し、
    channel id を jra.gch に統一して本番EPGへ追加する。
    """
    try:
        req = urllib.request.Request(
            GCH_GUIDES_URL,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Cache-Control": "no-cache",
            },
        )
        with urllib.request.urlopen(req, timeout=60) as response:
            raw = response.read()
        source_root = ET.fromstring(raw)
    except Exception as e:
        print(f"GCH guides.xml: 取得失敗: {e}")
        return 0

    exact_ids = []
    fallback_ids = []
    target_norm = normalize_channel_name(GCH_DISPLAY_NAME)

    for ch in source_root.findall("channel"):
        ch_id = ch.get("id", "")
        names = [
            normalize_channel_name(x.text)
            for x in ch.findall("display-name")
            if x.text
        ]
        if target_norm in names:
            exact_ids.append(ch_id)
        elif any(target_norm in name for name in names):
            fallback_ids.append(ch_id)

    source_ids = exact_ids or fallback_ids
    source_ids = [x for x in source_ids if x]

    if not source_ids:
        print("GCH guides.xml: グリーンチャンネルのchannel idを発見できません")
        return 0

    window_start = datetime.datetime.combine(
        today_date,
        datetime.time.min,
        tzinfo=JST,
    )
    window_end = window_start + datetime.timedelta(days=days)

    imported = 0
    for prog in source_root.findall("programme"):
        if prog.get("channel", "") not in source_ids:
            continue

        start_dt = parse_xmltv_datetime(prog.get("start"), JST)
        stop_dt = parse_xmltv_datetime(prog.get("stop"), JST)
        if not start_dt:
            continue

        start_jst = start_dt.astimezone(JST)
        stop_jst = stop_dt.astimezone(JST) if stop_dt else start_jst + datetime.timedelta(hours=1)

        # 今日0:00～3日後0:00と重なる番組だけ採用。
        if stop_jst <= window_start or start_jst >= window_end:
            continue

        copied = ET.fromstring(ET.tostring(prog, encoding="utf-8"))
        copied.set("channel", GCH_TVG_ID)
        tv.append(copied)
        imported += 1

    print(
        f"GCH guides.xml: source={','.join(source_ids)} / "
        f"{imported}番組を{GCH_TVG_ID}へ統合"
    )
    return imported


def fetch_text(url, label="URL"):
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Cache-Control": "no-cache",
                "Accept-Language": "ja-JP,ja;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"{label}: 取得失敗: {e}")
        return ""


def strip_html_tags(source):
    if not source:
        return ""
    source = re.sub(r"(?is)<script.*?</script>", " ", source)
    source = re.sub(r"(?is)<style.*?</style>", " ", source)
    source = re.sub(r"(?s)<[^>]+>", " ", source)
    source = html_lib.unescape(source)
    source = re.sub(r"\s+", " ", source)
    return source.strip()


def extract_boat_active_codes(index_html):
    # Official daily index links contain jcd=01 ... jcd=24.
    found = set(
        re.findall(r"(?:[?&]|&amp;)jcd=(\d{2})", index_html or "")
    )
    return sorted(code for code in found if code in BOAT_NAME_BY_CODE)


def extract_boat_race_times(race_html):
    """Return [(race_no, HH:MM), ...] from official raceindex HTML."""
    if not race_html:
        return []

    compact = re.sub(r"\s+", " ", html_lib.unescape(race_html))
    found = {}

    # Works with both visible table text and link-heavy HTML:
    # 1R ... 15:28, 2R ... 16:02, ...
    for race_no in range(1, 13):
        patterns = [
            rf">\s*{race_no}R\s*<.*?([0-2]?\d:[0-5]\d)",
            rf"\b{race_no}R\b.{{0,1200}}?([0-2]?\d:[0-5]\d)",
        ]
        for pat in patterns:
            m = re.search(pat, compact, flags=re.I | re.S)
            if m:
                found[race_no] = m.group(1)
                break

    # Fallback on stripped text.
    if len(found) < 2:
        plain = strip_html_tags(race_html)
        for race_no in range(1, 13):
            if race_no in found:
                continue
            m = re.search(
                rf"\b{race_no}R\b.{{0,150}}?([0-2]?\d:[0-5]\d)",
                plain,
                flags=re.I,
            )
            if m:
                found[race_no] = m.group(1)

    return [(n, found[n]) for n in sorted(found)]


def infer_boat_day_type(race_times):
    if not race_times:
        return "開催", "🚤"

    first = race_times[0][1]
    try:
        hour = int(first.split(":")[0])
    except Exception:
        return "開催", "🚤"

    if hour < 10:
        return "モーニング", "🌅"
    if hour >= 14:
        return "ナイター", "🌙"
    return "デイ", "☀️"


def fetch_boat_week_schedule(today_date, days):
    """
    Official BOAT RACE pages:
      index?hd=YYYYMMDD -> active venues for that date
      raceindex?hd=YYYYMMDD&jcd=XX -> 1R..12R race times
    """
    week = {}

    for offset in range(days):
        d = today_date + datetime.timedelta(days=offset)
        date_str = d.strftime("%Y%m%d")
        print(f"BOAT 週間予定: {date_str} ...", end="", flush=True)

        index_url = BOAT_OFFICIAL_INDEX_URL.format(date=date_str)
        index_html = fetch_text(index_url, f"BOAT index {date_str}")

        if not index_html:
            week[date_str] = {
                "ok": False,
                "venues": {},
            }
            print(" 取得失敗")
            continue

        active_codes = extract_boat_active_codes(index_html)

        # BOAT RACE公式は実質「今日＋明日」までの詳細取得を基本とする。
        # 3日目が未公表（0場）の場合は非開催と断定せず、
        # 全24場を区分別の仮時間でEPG表示する。
        if not active_codes and offset >= 2:
            week[date_str] = {
                "ok": True,
                "status": "provisional_all",
                "venues": {},
            }
            print(" 3日目未公表 -> 全24場を仮時間で生成")
            continue

        # 明日までで0場の場合も、掲載遅延の可能性があるため確認待ち。
        if not active_codes and d > today_date:
            week[date_str] = {
                "ok": True,
                "status": "pending",
                "venues": {},
            }
            print(" 開催情報確認待ち")
            continue

        venues = {}

        for code in active_codes:
            v_name = BOAT_NAME_BY_CODE.get(code)
            if not v_name:
                continue

            race_url = BOAT_OFFICIAL_RACEINDEX_URL.format(
                date=date_str,
                code=code,
            )
            race_html = fetch_text(race_url, f"BOAT {date_str} {code}")
            race_times = extract_boat_race_times(race_html)
            day_type, emoji = infer_boat_day_type(race_times)

            # Race title = first H2-like heading from the race page when available.
            title = ""
            if race_html:
                m = re.search(r"(?is)<h2[^>]*>(.*?)</h2>", race_html)
                if m:
                    title = strip_html_tags(m.group(1))

            venues[v_name] = {
                "code": code,
                "title": title,
                "day_type": day_type,
                "emoji": emoji,
                "races": [
                    {"race": str(race_no), "time": hhmm}
                    for race_no, hhmm in race_times
                ],
            }

        week[date_str] = {
            "ok": True,
            "status": "published",
            "venues": venues,
        }
        print(f" {len(venues)}場")

    return week


def build_boat_race_epg(
    tv,
    date_str,
    boat_week,
    JST,
    today_display,
):
    """
    Build BOAT EPG for one date from official schedule.
    Returns True if the daily official index was available.
    """
    day_info = boat_week.get(date_str, {})
    if not day_info.get("ok"):
        return False

    venues = day_info.get("venues", {})
    schedule_status = day_info.get("status", "published")

    for v_name, tvg_id in BOAT_MAP.items():
        day_start = datetime.datetime.strptime(
            f"{date_str} {DATA_READY_TIME}", "%Y%m%d %H:%M"
        ).replace(tzinfo=JST)
        day_end = datetime.datetime.strptime(
            f"{date_str} 23:59", "%Y%m%d %H:%M"
        ).replace(tzinfo=JST)

        info = venues.get(v_name)
        if not info:
            if schedule_status == "provisional_all":
                # 3日目は公式詳細未公表のため、開催・非開催を断定せず
                # デイ相当の仮枠を全24場へ入れて3日分EPGを維持する。
                add_provisional_event(
                    tv,
                    tvg_id,
                    date_str,
                    v_name,
                    "ボートレース",
                    "🚤",
                    "デイ",
                    JST,
                    today_display,
                    extra_title="開催予定（公式詳細未公表）",
                    extra_desc=[
                        "BOAT RACE公式の3日目詳細はまだ未公表です。",
                        "開催・非開催および実際の発走時刻は未確定です。",
                    ],
                )
            elif schedule_status == "pending":
                add_programme(
                    tv,
                    tvg_id,
                    day_start,
                    day_end,
                    f"⏳ 開催情報確認待ち {v_name}（ボートレース）",
                    f"BOAT RACE公式の{today_display}開催一覧は未公表または確認待ちです。\n"
                    "開催・非開催をまだ確定していません。",
                )
            else:
                add_programme(
                    tv,
                    tvg_id,
                    day_start,
                    day_end,
                    non_event_title(v_name, "ボートレース"),
                    f"BOAT RACE公式の{today_display}開催一覧に"
                    f"{v_name}は掲載されていません。",
                )
            continue

        races = info.get("races", [])
        day_type = info.get("day_type", "開催")
        emoji = info.get("emoji", "🚤")
        event_title = info.get("title", "")

        # 開催は確認できたが各R時刻がまだ無い場合は、仮時間を明示して表示。
        if not races:
            add_provisional_event(
                tv, tvg_id, date_str, v_name, "ボートレース", "🚤",
                day_type, JST, today_display,
                extra_title=event_title or "開催予定",
                extra_desc=[
                    "BOAT RACE公式の開催一覧で開催を確認済み。",
                    "1R～12Rの発走予定時刻は未公表または未取得です。",
                ],
            )
            continue

        race_dts = []
        for race in races:
            try:
                dt = datetime.datetime.strptime(
                    f"{date_str} {race.get('time','')}",
                    "%Y%m%d %H:%M",
                ).replace(tzinfo=JST)
            except Exception:
                continue
            race_dts.append((race, dt))

        if not race_dts:
            add_provisional_event(
                tv, tvg_id, date_str, v_name, "ボートレース", "🚤",
                day_type, JST, today_display,
                extra_title=event_title or "開催予定",
                extra_desc=[
                    "BOAT RACE公式で開催を確認済み。",
                    "発走予定時刻を利用できないため仮時間で表示しています。",
                ],
            )
            continue

        pre_start = max(
            day_start,
            race_dts[0][1] - datetime.timedelta(minutes=20),
        )

        if day_start < pre_start:
            add_programme(
                tv,
                tvg_id,
                day_start,
                pre_start,
                f"⏳ 待機 {v_name} {emoji}{day_type}",
                "\n".join(
                    x for x in [
                        f"🚤 ボートレース {v_name}",
                        f"📢 {event_title}" if event_title else "",
                        f"1R {race_dts[0][0].get('time','')} 発走予定",
                        f"📅 {today_display}",
                    ] if x
                ),
            )

        # Continuous race blocks:
        # from 10 min before each deadline until 10 min before next race.
        for idx, (race, race_dt) in enumerate(race_dts):
            block_start = max(
                pre_start,
                race_dt - datetime.timedelta(minutes=10),
            )

            if idx + 1 < len(race_dts):
                next_dt = race_dts[idx + 1][1]
                block_stop = next_dt - datetime.timedelta(minutes=10)
            else:
                block_stop = race_dt + datetime.timedelta(minutes=30)

            if block_stop <= block_start:
                block_stop = race_dt + datetime.timedelta(minutes=15)

            race_no = race.get("race", "")
            race_time = race.get("time", "")

            title_parts = [
                "🚤",
                v_name,
                f"{race_no}R",
                f"{race_time}発走",
                f"{emoji}{day_type}",
            ]
            if event_title:
                title_parts.append(event_title)
            title = " ".join(x for x in title_parts if x).strip()

            desc_lines = [
                f"🚤 ボートレース {v_name}",
                f"{emoji} 開催区分: {day_type}",
                f"⏰ 発走予定: {race_time}",
                f"📅 {today_display}",
            ]
            if event_title:
                desc_lines.insert(1, f"📢 {event_title}")

            add_programme(
                tv,
                tvg_id,
                block_start,
                min(block_stop, day_end),
                title,
                "\n".join(desc_lines),
            )

        finish = race_dts[-1][1] + datetime.timedelta(minutes=30)
        if finish < day_end:
            add_programme(
                tv,
                tvg_id,
                finish,
                day_end,
                finished_title(v_name, "ボートレース"),
                f"{v_name}の本日のボートレースは全て終了しました。",
            )

    return True





# -------------------------------------------------
# 当日競輪 各R実時刻取得 (netkeirin)
# KEIRIN.JP月間開催表を開催場の基準にし、当日だけ各R詳細を取得する。
# 取得失敗時は従来のKEIRIN.JP月間表・仮時間へフォールバックする。
# -------------------------------------------------
NETKEIRIN_RACE_URL = (
    "https://keirin.netkeiba.com/race/entry/?race_id={race_id}"
)

# 競輪場コード（race_id: YYYYMMDD + 場コード2桁 + R2桁）
NETKEIRIN_VENUE_CODE = {
    "函館": "11", "青森": "12", "いわき平": "13",
    "弥彦": "21", "前橋": "22", "取手": "23", "宇都宮": "24",
    "大宮": "25", "西武園": "26", "京王閣": "27", "立川": "28",
    "松戸": "31", "千葉": "32", "川崎": "34", "平塚": "35",
    "小田原": "36", "伊東": "37", "静岡": "38",
    "名古屋": "42", "岐阜": "43", "大垣": "44", "豊橋": "45",
    "富山": "46", "松阪": "47", "四日市": "48",
    "福井": "51", "奈良": "53", "向日町": "54", "和歌山": "55",
    "岸和田": "56",
    "玉野": "61", "広島": "62", "防府": "63",
    "高松": "71", "小松島": "73", "高知": "74", "松山": "75",
    "小倉": "81", "久留米": "83", "武雄": "84", "佐世保": "85",
    "別府": "86", "熊本": "87",
}


def fetch_netkeirin_text(url, label="netkeirin"):
    """netkeirinの当日出走表HTMLを取得。失敗時は空文字。"""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/151.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "ja-JP,ja;q=0.9",
                "Referer": "https://keirin.netkeiba.com/",
                "Cache-Control": "no-cache",
            },
        )
        with urllib.request.urlopen(req, timeout=20) as response:
            raw = response.read()
        # netkeirinはUTF-8。念のためreplaceで落とさない。
        return raw.decode("utf-8", errors="replace")
    except Exception as e:
        print(f"{label}: 取得失敗: {e}")
        return ""


def normalize_keirin_race_label(text):
    s = html_lib.unescape(str(text or ""))
    s = re.sub(r"[\u3000\t\r\n]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def parse_netkeirin_race_page(source, venue, date_str, race_no):
    """1レース分の発走時刻・競走名・級班・開催名を抽出。"""
    if not source:
        return None

    plain = strip_html_tags(source)
    if venue not in plain:
        return None

    # 発走時刻
    m_time = re.search(r"発走\s*([0-2]?\d:[0-5]\d)", plain)
    if not m_time:
        return None
    hhmm = m_time.group(1)
    if len(hhmm) == 4:
        hhmm = "0" + hhmm

    # <title> は「松山競輪 オールスター競輪 GI 2026年08月15日 7R 特選 出走表 ...」形式。
    title_text = ""
    mt = re.search(r"(?is)<title[^>]*>(.*?)</title>", source)
    if mt:
        title_text = normalize_keirin_race_label(strip_html_tags(mt.group(1)))

    race_name = ""
    event_name = ""
    race_class = ""

    # レース名はtitle末尾側を優先。
    if title_text:
        mr = re.search(
            rf"{re.escape(date_str[:4])}年{int(date_str[4:6]):02d}月{int(date_str[6:8]):02d}日\s*"
            rf"{race_no}R\s+(.+?)\s+出走表",
            title_text,
        )
        if mr:
            race_name = normalize_keirin_race_label(mr.group(1))

        # 開催名: 「<場名>競輪 <開催名> <GI/FI等> YYYY年...」
        me = re.search(
            rf"{re.escape(venue)}競輪\s+(.+?)\s+(?:GP|G[1-3I]+|F[12I]+)\s+"
            rf"{re.escape(date_str[:4])}年",
            title_text,
            flags=re.I,
        )
        if me:
            event_name = normalize_keirin_race_label(me.group(1))

    # 級班＋ステージ。例: 「Ｓ級 特選 発走 18:15」
    mc = re.search(
        r"([SＳAＡLＬ]級\s*[^ ]{1,12}(?:\s*[^ ]{1,12})?)\s+発走\s*[0-2]?\d:[0-5]\d",
        plain,
    )
    if mc:
        race_class = normalize_keirin_race_label(mc.group(1))

    # titleから取れなければ級班文字列からステージ部分を使う。
    if not race_name and race_class:
        race_name = re.sub(r"^[SＳAＡLＬ]級\s*", "", race_class).strip()
    if not race_name:
        race_name = "競走"

    girls = bool(re.search(r"[LＬ]級|ガールズ", race_class + " " + race_name))
    is_semi = "準決" in race_name
    is_final = ("決勝" in race_name or "優勝" in race_name) and not is_semi

    return {
        "race": str(race_no),
        "time": hhmm,
        "name": race_name,
        "race_class": race_class or ("L級" if girls else "競輪"),
        "girls": girls,
        "is_semi": is_semi,
        "is_final": is_final,
        "main": False,  # 全R取得後に最終Rをmain化
        "event_name": event_name,
    }


def extract_netkeirin_race_numbers(source, date_str, venue_code):
    """出走表ページ内リンクから、その開催日の存在するR番号を抽出。"""
    if not source:
        return []
    prefix = f"{date_str}{venue_code}"
    nums = set()
    for m in re.finditer(rf"race_id={re.escape(prefix)}(\d{{2}})", source):
        n = int(m.group(1))
        if 1 <= n <= 12:
            nums.add(n)
    return sorted(nums)


def fetch_keirin_today_races(date_str, month_schedule):
    """
    当日競輪のみ各R実時刻を取得する。
    開催場はKEIRIN.JP月間開催表(month_schedule)を基準にする。
    詳細取得に失敗した場はvenuesへ入れず、呼び出し側で仮時間へフォールバックする。
    """
    schedule_today = month_schedule.get(date_str, {}) if month_schedule else {}
    venues = {}

    for venue, sched in schedule_today.items():
        code = NETKEIRIN_VENUE_CODE.get(venue)
        if not code:
            print(f"KEIRIN TODAY: 場コード未登録: {venue}")
            continue

        first_id = f"{date_str}{code}01"
        first_url = NETKEIRIN_RACE_URL.format(race_id=first_id)
        first_html = fetch_netkeirin_text(first_url, f"KEIRIN TODAY {venue} 1R")
        if not first_html:
            continue

        race_numbers = extract_netkeirin_race_numbers(first_html, date_str, code)
        if 1 not in race_numbers:
            race_numbers.insert(0, 1)
        race_numbers = sorted(set(n for n in race_numbers if 1 <= n <= 12))

        # ナビリンクを拾えない場合の安全策。1Rが取れれば最大12Rまで順に試す。
        if len(race_numbers) <= 1:
            race_numbers = list(range(1, 13))

        races = []
        event_name = ""
        consecutive_missing = 0

        for race_no in race_numbers:
            if race_no == 1:
                page = first_html
            else:
                rid = f"{date_str}{code}{race_no:02d}"
                page = fetch_netkeirin_text(
                    NETKEIRIN_RACE_URL.format(race_id=rid),
                    f"KEIRIN TODAY {venue} {race_no}R",
                )

            race = parse_netkeirin_race_page(page, venue, date_str, race_no)
            if not race:
                consecutive_missing += 1
                # ナビ無しフォールバック中、連続2R無ければその先は打ち切る。
                if consecutive_missing >= 2 and len(race_numbers) == 12:
                    break
                continue

            consecutive_missing = 0
            if race.get("event_name") and not event_name:
                event_name = race["event_name"]
            races.append(race)

        if not races:
            print(f"KEIRIN TODAY {venue}: 各R実時刻を取得できず -> 仮時間へ")
            continue

        races.sort(key=lambda x: int(x.get("race", 0) or 0))
        races[-1]["main"] = True

        grade = sched.get("grade", "")
        day_type = normalize_day_type(sched.get("day_type", "デイ"))
        event_day = sched.get("event_day", "")

        venues[venue] = {
            "tvg_id": KEIRIN_MAP.get(venue, ""),
            "grade": grade,
            "day_type": day_type,
            "day_emoji": sched.get("emoji", day_emoji(day_type)),
            "event_day": event_day,
            "event_name": event_name,
            "races": races,
            "source": "netkeirin当日出走表 / KEIRIN.JP開催表",
        }
        print(f"KEIRIN TODAY {venue}: {len(races)}R 実時刻取得")

    return {
        "date": date_str,
        "venues": venues,
        "updated_at": datetime.datetime.now(
            datetime.timezone(datetime.timedelta(hours=9))
        ).isoformat(),
    }


def build_keirin_today_with_fallback(
    tv, target_date, month_schedule, JST, today_display
):
    """
    今日: 実R取得できた場は各R表示。取れなかった場だけ月間表の仮時間。
    ※同一チャンネルの重複を避けるため、実R成功場を月間表から除外して仮時間を生成。
    """
    date_str = target_date.strftime("%Y%m%d")
    today_data = fetch_keirin_today_races(date_str, month_schedule)
    real_venues = set(today_data.get("venues", {}))

    used_real = False
    if real_venues:
        used_real = build_keirin_race_epg(
            tv, date_str, today_data, JST, today_display
        )

    # 実Rを取れなかった開催場 + 非開催場は従来ロジックで埋める。
    filtered_month = {}
    for d, venues in (month_schedule or {}).items():
        if d != date_str:
            filtered_month[d] = venues
            continue
        filtered_month[d] = {
            v: info for v, info in venues.items() if v not in real_venues
        }

    # build_keirin_future_epg は「月間表に無い場=非開催」を全場生成するため、
    # 実R成功場まで非開催表示しないよう、ここでは失敗場のみ個別に生成する。
    schedule_today = (month_schedule or {}).get(date_str, {})
    day_start = datetime.datetime.strptime(
        f"{date_str} {DATA_READY_TIME}", "%Y%m%d %H:%M"
    ).replace(tzinfo=JST)
    day_end = datetime.datetime.strptime(
        f"{date_str} 23:59", "%Y%m%d %H:%M"
    ).replace(tzinfo=JST)

    for venue, tvg_id in KEIRIN_MAP.items():
        if venue in real_venues:
            continue
        info = schedule_today.get(venue)
        if not info:
            add_programme(
                tv, tvg_id, day_start, day_end,
                non_event_title(venue, "競輪"),
                f"KEIRIN.JP開催日程で{today_display}の開催予定はありません。",
            )
            continue

        grade = info.get("grade", "")
        day_type = normalize_day_type(info.get("day_type", "デイ"))
        emoji = info.get("emoji", day_emoji(day_type))
        event_day = info.get("event_day", "")
        start_dt, end_dt, start_text, end_text = build_provisional_times(
            date_str, day_type, JST
        )

        if day_start < start_dt:
            add_programme(
                tv, tvg_id, day_start, start_dt,
                f"⏳ 待機 {venue} 【{grade}】 {emoji}{day_type}",
                "\n".join(x for x in [
                    f"🚲 競輪 {venue}",
                    f"🏆 開催種別: {grade}" if grade else "",
                    f"{emoji} 開催パターン: {day_type}",
                    f"📅 {event_day}" if event_day else "",
                    f"⏰ 仮開始: {start_text}",
                    f"⚠️ {PROVISIONAL_NOTICE}",
                    f"📅 {today_display}",
                ] if x),
            )

        title_parts = [
            f"【{grade}】" if grade else "",
            venue, f"{emoji}{day_type}", event_day,
            "開催予定", PROVISIONAL_NOTICE,
        ]
        desc_lines = [
            f"🚲 競輪 {venue}",
            f"🏆 開催種別: {grade}" if grade else "",
            f"{emoji} 開催パターン: {day_type}",
            f"📅 開催日次: {event_day}" if event_day else "",
            f"⏰ 仮予定: {start_text}～{'翌' if end_dt.date() != start_dt.date() else ''}{end_text}",
            f"⚠️ {PROVISIONAL_NOTICE}",
            "当日各Rの実時刻取得に失敗したため、KEIRIN.JP月間開催表の仮時間で表示しています。",
            f"📅 {today_display}",
        ]
        add_programme(
            tv, tvg_id, start_dt, end_dt,
            " ".join(x for x in title_parts if x),
            "\n".join(x for x in desc_lines if x),
        )

        if end_dt.date() == day_start.date() and end_dt < day_end:
            add_programme(
                tv, tvg_id, end_dt, day_end,
                finished_title(venue, "競輪"),
                f"{venue}の本日の競輪は全て終了しました。",
            )

    print(
        f"KEIRIN TODAY EPG {date_str}: 実R {len(real_venues)}場 / "
        f"残りは月間表仮時間"
    )
    return used_real

# -------------------------------------------------
# KEIRIN.JP future schedule support
# Future days use official monthly schedule metadata:
# venue / grade / day pattern / event day.
# Exact race times are replaced by provisional start times.
# -------------------------------------------------

KEIRIN_JP_SCHEDULE_URL = (
    "https://keirin.jp/pc/raceschedule?scym={month}&scyy={year}"
)

KEIRIN_FUTURE_GRADE_BY_SRC = {
    "ico_f1.png": "F1",
    "ico_f2.png": "F2",
    "ico_g1.png": "G1",
    "ico_g2.png": "G2",
    "ico_g3.png": "G3",
}

KEIRIN_FUTURE_TYPE_BY_SRC = {
    "ico_kaisai_3.png": ("ナイター", "🌙"),
    "ico_kaisai_5.png": ("ミッドナイト", "⭐"),
    "ico_kaisai_8.png": ("モーニング", "🌅"),
}

PROVISIONAL_TIME_WINDOWS = {
    # 競輪モーニングは2系統。月間表だけで判別できない場合は「通常モーニング」を使う。
    "早朝モーニング": ("08:30", "12:30"),
    "モーニング": ("10:00", "14:00"),
    "デイ": ("10:30", "17:00"),
    "薄暮": ("13:30", "19:00"),
    "ナイター": ("15:00", "21:00"),
    "ミッドナイト": ("20:30", "23:30"),
    # 翌日00:30まで。build_provisional_times() で日付またぎに変換する。
    "オーバーミッドナイト": ("21:00", "00:30"),
}

# 既存の競輪未来日コードとの互換用。
KEIRIN_FUTURE_START = {
    k: v[0] for k, v in PROVISIONAL_TIME_WINDOWS.items()
}

PROVISIONAL_NOTICE = "（仮時間）※実際の時間ではありません"


def normalize_day_type(day_type):
    text = str(day_type or "").strip()
    aliases = {
        "通常": "デイ",
        "サマータイム": "薄暮",
        "オーバーミットナイト": "オーバーミッドナイト",
        "OVER MIDNIGHT": "オーバーミッドナイト",
    }
    return aliases.get(text, text or "デイ")


def build_provisional_times(date_str, day_type, JST):
    day_type = normalize_day_type(day_type)
    start_text, end_text = PROVISIONAL_TIME_WINDOWS.get(
        day_type, PROVISIONAL_TIME_WINDOWS["デイ"]
    )
    start_dt = datetime.datetime.strptime(
        f"{date_str} {start_text}", "%Y%m%d %H:%M"
    ).replace(tzinfo=JST)
    end_dt = datetime.datetime.strptime(
        f"{date_str} {end_text}", "%Y%m%d %H:%M"
    ).replace(tzinfo=JST)
    if end_dt <= start_dt:
        end_dt += datetime.timedelta(days=1)
    return start_dt, end_dt, start_text, end_text


def add_provisional_event(tv, tvg_id, date_str, venue, category_label, icon, day_type, JST, today_display, extra_title="", extra_desc=None):
    day_type = normalize_day_type(day_type)
    start_dt, end_dt, start_text, end_text = build_provisional_times(date_str, day_type, JST)
    title_parts = [icon, venue, f"{day_emoji(day_type)}{day_type}"]
    if extra_title:
        title_parts.append(extra_title)
    title_parts.append(PROVISIONAL_NOTICE)
    desc_lines = [
        f"{icon} {category_label} {venue}",
        f"{day_emoji(day_type)} 開催区分: {day_type}",
        f"⏰ 仮予定: {start_text}～{'翌' if end_dt.date() != start_dt.date() else ''}{end_text}",
        f"⚠️ {PROVISIONAL_NOTICE}",
        "開催は確認できていますが、公式の実時刻が未公表または取得できないため仮時間で表示しています。",
        f"📅 {today_display}",
    ]
    if extra_desc:
        desc_lines[1:1] = [x for x in extra_desc if x]
    add_programme(tv, tvg_id, start_dt, end_dt, " ".join(x for x in title_parts if x), "\n".join(desc_lines))


class KeirinScheduleParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_tr = False
        self.in_td = False
        self.rows = []
        self.row = []
        self.cell = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)

        if tag == "tr":
            self.in_tr = True
            self.row = []

        elif tag == "td" and self.in_tr:
            self.in_td = True
            try:
                colspan = int(attrs.get("colspan", "1") or "1")
            except Exception:
                colspan = 1

            self.cell = {
                "text": [],
                "imgs": [],
                "colspan": max(1, colspan),
            }

        elif tag == "img" and self.in_td and self.cell is not None:
            self.cell["imgs"].append(
                {
                    "src": attrs.get("src", ""),
                    "alt": attrs.get("alt", ""),
                    "title": attrs.get("title", ""),
                }
            )

    def handle_data(self, data):
        if self.in_td and self.cell is not None:
            value = re.sub(r"\s+", " ", data).strip()
            if value:
                self.cell["text"].append(value)

    def handle_endtag(self, tag):
        if tag == "td" and self.in_td:
            self.in_td = False
            self.row.append(self.cell)
            self.cell = None

        elif tag == "tr" and self.in_tr:
            self.in_tr = False
            if self.row:
                self.rows.append(self.row)
            self.row = []


def keirin_schedule_venue(cell):
    text = re.sub(r"\s+", "", " ".join(cell.get("text", [])))
    for venue in KEIRIN_MAP:
        if venue in text:
            return venue
    return ""


def classify_keirin_future_cell(cell):
    grade = ""
    day_type = "デイ"
    emoji = "☀️"

    combined_text = " ".join(
        cell.get("text", [])
        + [x.get("alt", "") for x in cell.get("imgs", [])]
        + [x.get("title", "") for x in cell.get("imgs", [])]
    )

    if "ミッドナイト" in combined_text:
        day_type, emoji = "ミッドナイト", "⭐"
    elif "モーニング" in combined_text:
        day_type, emoji = "モーニング", "🌅"
    elif "ナイター" in combined_text:
        day_type, emoji = "ナイター", "🌙"

    icons = []

    for img in cell.get("imgs", []):
        base = img.get("src", "").rsplit("/", 1)[-1]
        icons.append(base)

        if base in KEIRIN_FUTURE_GRADE_BY_SRC:
            grade = KEIRIN_FUTURE_GRADE_BY_SRC[base]

        if base in KEIRIN_FUTURE_TYPE_BY_SRC:
            day_type, emoji = KEIRIN_FUTURE_TYPE_BY_SRC[base]

    # Dokanto! and other auxiliary icons are intentionally ignored.
    return {
        "has_event": bool(grade),
        "grade": grade,
        "day_type": day_type,
        "emoji": emoji,
        "icons": icons,
    }


def keirin_event_day_label(index_in_span, span):
    if span <= 1:
        return ""
    if index_in_span == 0:
        return "初日"
    if index_in_span == span - 1:
        return "最終日"
    return f"{index_in_span + 1}日目"


def fetch_keirin_future_month(year, month):
    url = KEIRIN_JP_SCHEDULE_URL.format(
        year=year,
        month=f"{month:02d}",
    )
    source = fetch_text(url, f"KEIRIN.JP schedule {year}-{month:02d}")

    if not source:
        return {}

    parser = KeirinScheduleParser()
    parser.feed(source)

    result = {}

    for row in parser.rows:
        if len(row) < 2:
            continue

        venue = keirin_schedule_venue(row[0])
        if not venue:
            continue

        logical_day = 1

        for cell in row[1:]:
            span = max(1, int(cell.get("colspan", 1)))
            info = classify_keirin_future_cell(cell)

            for offset in range(span):
                day = logical_day + offset
                if day > 31:
                    break

                if info["has_event"]:
                    date_str = f"{year:04d}{month:02d}{day:02d}"
                    result.setdefault(date_str, {})[venue] = {
                        **info,
                        "event_day": keirin_event_day_label(offset, span),
                        "span": span,
                    }

            logical_day += span

            if logical_day > 31:
                break

    return result


def build_keirin_future_epg(
    tv,
    target_date,
    month_schedule,
    JST,
    today_display,
):
    date_str = target_date.strftime("%Y%m%d")
    day_start = datetime.datetime.strptime(
        f"{date_str} {DATA_READY_TIME}", "%Y%m%d %H:%M"
    ).replace(tzinfo=JST)
    day_end = datetime.datetime.strptime(
        f"{date_str} 23:59", "%Y%m%d %H:%M"
    ).replace(tzinfo=JST)

    venues = month_schedule.get(date_str, {})
    handled = 0

    for venue, tvg_id in KEIRIN_MAP.items():
        info = venues.get(venue)

        if not info:
            add_programme(
                tv, tvg_id, day_start, day_end,
                non_event_title(venue, "競輪"),
                f"KEIRIN.JP開催日程で{today_display}の開催予定はありません。",
            )
            continue

        handled += 1
        grade = info.get("grade", "")
        day_type = normalize_day_type(info.get("day_type", "デイ"))
        emoji = info.get("emoji", day_emoji(day_type))
        event_day = info.get("event_day", "")

        start_dt, end_dt, start_text, end_text = build_provisional_times(
            date_str, day_type, JST
        )

        if day_start < start_dt:
            add_programme(
                tv, tvg_id, day_start, start_dt,
                f"⏳ 待機 {venue} 【{grade}】 {emoji}{day_type}",
                "\n".join(x for x in [
                    f"🚲 競輪 {venue}",
                    f"🏆 開催種別: {grade}" if grade else "",
                    f"{emoji} 開催パターン: {day_type}",
                    f"📅 {event_day}" if event_day else "",
                    f"⏰ 仮開始: {start_text}",
                    f"⚠️ {PROVISIONAL_NOTICE}",
                    f"📅 {today_display}",
                ] if x),
            )

        title_parts = [
            f"【{grade}】" if grade else "", venue,
            f"{emoji}{day_type}", event_day, "開催予定",
            PROVISIONAL_NOTICE,
        ]
        desc_lines = [
            f"🚲 競輪 {venue}",
            f"🏆 開催種別: {grade}" if grade else "",
            f"{emoji} 開催パターン: {day_type}",
            f"📅 開催日次: {event_day}" if event_day else "",
            f"⏰ 仮予定: {start_text}～{'翌' if end_dt.date() != start_dt.date() else ''}{end_text}",
            f"⚠️ {PROVISIONAL_NOTICE}",
            "開催は確認できていますが、実際の各R時刻はこの情報源では未確定のため仮時間で表示しています。",
            f"📅 {today_display}",
        ]
        add_programme(
            tv, tvg_id, start_dt, end_dt,
            " ".join(x for x in title_parts if x),
            "\n".join(x for x in desc_lines if x),
        )

        # オーバーミッドナイト以外は同日内で終了表示。
        if end_dt.date() == day_start.date() and end_dt < day_end:
            add_programme(
                tv, tvg_id, end_dt, day_end,
                finished_title(venue, "競輪"),
                f"{venue}の本日の競輪は全て終了しました。",
            )

    print(f"KEIRIN EPG {date_str}: {handled}場を公式開催表＋仮時間で生成")
    return True


def build_future_placeholder(
    tv,
    date_str,
    target_map,
    category_label,
    category_icon,
    JST,
    today_display,
):
    """Future dates without race JSON: show a neutral schedule placeholder."""
    day_start = datetime.datetime.strptime(
        f"{date_str} {DATA_READY_TIME}", "%Y%m%d %H:%M"
    ).replace(tzinfo=JST)
    day_end = datetime.datetime.strptime(
        f"{date_str} 23:59", "%Y%m%d %H:%M"
    ).replace(tzinfo=JST)

    for v_name, tvg_id in target_map.items():
        add_programme(
            tv,
            tvg_id,
            day_start,
            day_end,
            f"📅 {v_name}（{category_label}）",
            f"{category_icon} {category_label} {v_name}\n"
            f"📅 {today_display}\n"
            "当日データ取得時に詳細EPGへ自動更新します。",
        )


def build_stream_channel_placeholder(
    tv,
    date_str,
    channel_names,
    JST,
    today_display,
):
    """Channels such as JRA official/Green Channel that have no race JSON."""
    day_start = datetime.datetime.strptime(
        f"{date_str} {DATA_READY_TIME}", "%Y%m%d %H:%M"
    ).replace(tzinfo=JST)
    day_end = datetime.datetime.strptime(
        f"{date_str} 23:59", "%Y%m%d %H:%M"
    ).replace(tzinfo=JST)

    for v_name in channel_names:
        tvg_id = KEIBA_MAP.get(v_name)
        if not tvg_id:
            continue
        add_programme(
            tv,
            tvg_id,
            day_start,
            day_end,
            f"📺 {v_name}",
            f"📺 {v_name}\n📅 {today_display}",
        )



def jra_calendar_url(target_date):
    year = target_date.strftime("%Y")
    month = str(int(target_date.strftime("%m")))
    mmdd = target_date.strftime("%m%d")
    return f"https://www.jra.go.jp/keiba/calendar{year}/{year}/{month}/{mmdd}.html"


JRA_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/151.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.7,en;q=0.6",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
}


def fetch_jra_html(url, label="JRA"):
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(jar)
    )

    def _open(target_url, referer=None):
        headers = dict(JRA_HEADERS)
        if referer:
            headers["Referer"] = referer

        req = urllib.request.Request(target_url, headers=headers)
        with opener.open(req, timeout=30) as response:
            body = response.read()
            ctype = response.headers.get("Content-Type", "")

        encodings = []
        m = re.search(r"charset=([A-Za-z0-9_\-]+)", ctype, flags=re.I)
        if m:
            encodings.append(m.group(1))

        head = body[:5000].decode("ascii", errors="ignore")
        m = re.search(r'charset=["\']?\s*([A-Za-z0-9_\-]+)', head, flags=re.I)
        if m:
            encodings.append(m.group(1))

        encodings += ["utf-8", "cp932", "shift_jis", "euc_jp"]

        seen = set()
        best_text = ""
        best_score = -1

        for enc in encodings:
            enc = enc.lower()
            if enc in seen:
                continue
            seen.add(enc)

            try:
                decoded = body.decode(enc)
            except Exception:
                continue

            score = sum(
                decoded.count(word)
                for word in (
                    "東京", "中山", "新潟", "福島", "京都",
                    "阪神", "中京", "小倉", "札幌", "函館",
                    "競馬番組", "レース番号", "発走時刻",
                )
            )
            if score > best_score:
                best_score = score
                best_text = decoded

        return best_text or body.decode("utf-8", errors="ignore")

    try:
        try:
            _open("https://www.jra.go.jp/", "https://www.google.com/")
        except Exception as e:
            print(f"{label}: top page prime failed: {e}")

        return _open(
            url,
            "https://www.jra.go.jp/keiba/calendar/",
        )
    except Exception as e:
        print(f"{label}: 取得失敗: {e}")
        return ""


def _extract_jra_races_from_section(section):
    races = {}

    race_re = re.compile(
        r"(\d{1,2})\s*レース\s+(.*?)\s+([0-2]?\d)\s*時\s*([0-5]\d)\s*分",
        flags=re.S,
    )

    for m in race_re.finditer(section):
        rn = int(m.group(1))
        if not 1 <= rn <= 12:
            continue

        name = re.sub(r"\s+", " ", m.group(2)).strip()
        if len(name) > 180:
            name = name[:180] + "…"

        races[rn] = {
            "race": str(rn),
            "time": f"{int(m.group(3)):02d}:{m.group(4)}",
            "name": name or "JRA競走",
        }

    return [races[n] for n in sorted(races)]


def fetch_jra_day(target_date):
    url = jra_calendar_url(target_date)
    source = fetch_jra_html(url, f"JRA {target_date:%Y%m%d}")
    if not source:
        # 403等は「非開催」ではなく取得不能として区別する。
        return None

    plain = strip_html_tags(source)

    # Actual meeting blocks on the JRA programme page are headed like:
    # "2回新潟7日", "2回中京7日", "1回札幌7日".
    # Parsing only these headings avoids false positives from navigation links.
    meeting_re = re.compile(
        r"(\d+)\s*回\s*"
        r"(東京|中山|新潟|福島|京都|阪神|中京|小倉|札幌|函館)"
        r"\s*(\d+)\s*日"
    )
    headings = list(meeting_re.finditer(plain))

    out = {}

    for i, match in enumerate(headings):
        venue = match.group(2)
        section_start = match.end()
        section_end = (
            headings[i + 1].start()
            if i + 1 < len(headings)
            else len(plain)
        )

        section = plain[section_start:section_end]
        races = _extract_jra_races_from_section(section)

        # A normal JRA meeting should have a substantial race card.
        # Keep it only when enough races were actually parsed.
        if len(races) >= 5:
            out[venue] = races

    print(
        f"JRA {target_date:%Y%m%d}: "
        + (
            ", ".join(f"{venue}={len(races)}R" for venue, races in out.items())
            if out
            else "開催場なし"
        )
    )

    return out


def build_jra_stream_epg(tv, target_date, JST, today_display):
    date_str = target_date.strftime("%Y%m%d")
    day_start = datetime.datetime.strptime(
        f"{date_str} {DATA_READY_TIME}", "%Y%m%d %H:%M"
    ).replace(tzinfo=JST)
    day_end = datetime.datetime.strptime(
        f"{date_str} 23:59", "%Y%m%d %H:%M"
    ).replace(tzinfo=JST)

    by_venue = fetch_jra_day(target_date)
    by_stream = {k: [] for k in JRA_STREAM_MAP}

    if by_venue is None:
        for stream_name, tvg_id in JRA_STREAM_MAP.items():
            add_programme(
                tv,
                tvg_id,
                day_start,
                day_end,
                f"⏳ JRA 開催情報確認待ち {stream_name}",
                f"JRA公式の{today_display}開催情報を取得できませんでした。\n"
                "開催・非開催をまだ確定していません。",
            )
        return

    for venue, races in by_venue.items():
        stream = JRA_VENUE_TO_STREAM.get(venue)
        if stream:
            by_stream[stream].append((venue, races))

    for stream_name, tvg_id in JRA_STREAM_MAP.items():
        meetings = by_stream.get(stream_name, [])

        if not meetings:
            add_programme(
                tv,
                tvg_id,
                day_start,
                day_end,
                f"🌼🐴 本日は開催していません 💤🍀 {stream_name}",
                f"JRA公式で{today_display}の対象開催を確認できませんでした。",
            )
            continue

        flat = []

        for venue, races in meetings:
            for race in races:
                try:
                    dt = datetime.datetime.strptime(
                        f"{date_str} {race['time']}",
                        "%Y%m%d %H:%M",
                    ).replace(tzinfo=JST)
                except Exception:
                    continue

                flat.append((dt, venue, race))

        flat.sort(key=lambda x: x[0])

        if not flat:
            add_programme(
                tv,
                tvg_id,
                day_start,
                day_end,
                f"📅 JRA 開催予定 {stream_name}",
                f"JRA公式で開催を確認しました。\n📅 {today_display}",
            )
            continue

        pre = max(
            day_start,
            flat[0][0] - datetime.timedelta(minutes=20),
        )

        if day_start < pre:
            add_programme(
                tv,
                tvg_id,
                day_start,
                pre,
                f"⏳ 待機 {stream_name} / {flat[0][1]}",
                f"🏇 JRA {flat[0][1]}\n"
                f"1R発走予定 {flat[0][2]['time']}\n"
                f"📅 {today_display}",
            )

        for i, (dt, venue, race) in enumerate(flat):
            block_start = max(
                pre,
                dt - datetime.timedelta(minutes=10),
            )

            next_dt = flat[i + 1][0] if i + 1 < len(flat) else None
            long_break = bool(next_dt and (next_dt - dt) >= datetime.timedelta(minutes=40))

            if next_dt:
                block_stop = (
                    dt + datetime.timedelta(minutes=20)
                    if long_break
                    else next_dt - datetime.timedelta(minutes=10)
                )
            else:
                block_stop = dt + datetime.timedelta(minutes=30)

            if block_stop <= block_start:
                block_stop = dt + datetime.timedelta(minutes=15)

            base_title = (
                f"🏇 {venue} {race['race']}R "
                f"{race['time']}発走 {race.get('name', 'JRA競走')}"
            )
            title = decorate_race_title(
                base_title,
                race["race"],
                name=race.get("name", ""),
            )

            desc = (
                f"🏇 JRA {venue}\n"
                f"⏰ 発走予定: {race['time']}\n"
                f"📢 {race.get('name', '')}\n"
                f"📅 {today_display}"
            )

            add_programme(
                tv,
                tvg_id,
                block_start,
                min(block_stop, day_end),
                title,
                desc,
            )

            if long_break:
                break_start = dt + datetime.timedelta(minutes=20)
                break_stop = next_dt - datetime.timedelta(minutes=10)
                if break_stop > break_start:
                    next_venue = flat[i + 1][1]
                    next_race = flat[i + 1][2]
                    add_programme(
                        tv,
                        tvg_id,
                        break_start,
                        min(break_stop, day_end),
                        "🌸☕ ただいまお休み中です 🐴💤",
                        (
                            f"JRA {stream_name} はただいま中休みです。\n"
                            f"次は {next_venue} {next_race.get('race','')}R "
                            f"{next_race.get('time','')}発走予定です。\n"
                            f"🌿 のんびりお待ちください 🐴☕"
                        ),
                    )

        finish = flat[-1][0] + datetime.timedelta(minutes=30)

        if finish < day_end:
            venues_text = "・".join(dict.fromkeys(v for _, v, _ in flat))
            add_programme(
                tv,
                tvg_id,
                finish,
                day_end,
                finished_title(stream_name, "JRA"),
                f"{venues_text}の本日のJRA開催は終了しました。",
            )

    print(
        "JRA EPG:",
        ", ".join(
            f"{name}={len(meetings)}場"
            for name, meetings in by_stream.items()
        ),
    )




AUTORACE_PROGRAM_BASE = "https://autorace.jp/race_info/Program/{slug}/{date}_{race_no}"
AUTORACE_SLUG = {"川口":"kawaguchi","伊勢崎":"isesaki","浜松":"hamamatsu","飯塚":"iizuka","山陽":"sanyo"}

def _extract_autorace_program_race(source, race_no):
    if not source:
        return None
    plain = strip_html_tags(source)
    if "該当レースの開催は中止となりました" in plain:
        return None
    m = re.search(r"(?:発走予定|発走時刻|発走)\s*[:：]?\s*([0-2]?\d:[0-5]\d)", plain)
    time_text = m.group(1) if m else ""
    if not time_text:
        m = re.search(r"投票締切\s*[:：]?\s*([0-2]?\d:[0-5]\d)", plain)
        if m:
            hh, mm = map(int, m.group(1).split(":"))
            t = datetime.datetime(2000,1,1,hh,mm) + datetime.timedelta(minutes=1)
            time_text = t.strftime("%H:%M")
    if not time_text:
        return None
    name = ""
    m = re.search(rf"([^\s　]{{1,30}}?)\s*{race_no}R\b", plain)
    if m:
        name = re.sub(r"\s+"," ",m.group(1)).strip()
    if not name:
        name = "オートレース"
    return {
        "race": str(race_no), "time": time_text, "name": name,
        "race_type": name, "icon": "🏍️", "main": race_no == 12,
        "is_semi": "準決" in name,
        "is_final": ("優勝" in name or "決勝" in name),
    }


def classify_autorace_day_type_from_races(races, fallback="デイ"):
    """
    当日の実レース時刻を優先して開催区分を補正する。
    最終Rの発走 + 30分を終了予定とみなし、
    23:40を超える場合は「オーバーミッドナイト」。
    """
    valid = []
    for r in races or []:
        t = str(r.get("time", "")).strip()
        if re.fullmatch(r"\d{1,2}:\d{2}", t):
            hh, mm = map(int, t.split(":"))
            valid.append((hh, mm))

    if not valid:
        return fallback or "デイ"

    hh, mm = valid[-1]
    end_minutes = hh * 60 + mm + 30

    if end_minutes > (23 * 60 + 40):
        return "オーバーミッドナイト"

    # それ以外は公式カレンダーの区分を尊重
    return fallback or "デイ"


def fetch_autorace_today_exact(target_date, month_schedule):
    date_str = target_date.strftime("%Y%m%d")
    iso_date = target_date.strftime("%Y-%m-%d")
    calendar_venues = month_schedule.get(date_str, {})
    out = {"date": date_str, "venues": {}}
    for venue, race_meta in calendar_venues.items():
        slug = AUTORACE_SLUG.get(venue)
        if not slug:
            continue
        races = []
        for race_no in range(1,13):
            url = AUTORACE_PROGRAM_BASE.format(slug=slug,date=iso_date,race_no=race_no)
            source = fetch_text(url, f"AUTORACE TODAY {venue} {race_no}R")
            r = _extract_autorace_program_race(source, race_no)
            if r:
                races.append(r)
        if not races:
            continue
        official_day_type = clean_epg_meta_text(race_meta.get("nighterName","")) or "デイ"
        day_type = classify_autorace_day_type_from_races(
            races,
            official_day_type,
        )
        out["venues"][venue] = {
            "tvg_id": AUTO_MAP.get(venue,""),
            "races": races,
            "day_type": day_type,
            "day_emoji": day_emoji(day_type),
            "grade": clean_epg_meta_text(race_meta.get("gradeName","")),
            "event_name": clean_epg_meta_text(race_meta.get("title","")) or clean_epg_meta_text(race_meta.get("titleShort","")),
            "event_day": race_meta.get("paragraphDay",""),
        }
        print(f"AUTORACE TODAY {venue}: {len(races)}R取得")
    return out


# -------------------------------------------------
# AutoRace.JP future calendar support
# Future days use the official monthly Calendar API.
# Only calendar[].race means a home-track event; outside[] is ignored.
# -------------------------------------------------
AUTORACE_CALENDAR_URL = "https://autorace.jp/race_info/XML/Calendar?date={year}-{month:02d}"

def fetch_autorace_future_month(year, month):
    data = fetch_json(
        AUTORACE_CALENDAR_URL.format(year=year, month=month),
        f"AUTORACE FUTURE {year}-{month:02d}",
    )
    result = {}
    if not isinstance(data, dict):
        return result

    body = data.get("body", [])
    if not isinstance(body, list):
        return result

    def add_range(venue, race, start_text, end_text):
        try:
            start_date = datetime.datetime.strptime(
                str(start_text), "%Y-%m-%d"
            ).date()
            end_date = datetime.datetime.strptime(
                str(end_text), "%Y-%m-%d"
            ).date()
        except Exception:
            return False

        if end_date < start_date:
            start_date, end_date = end_date, start_date

        cur = start_date
        added = False
        while cur <= end_date:
            if cur.year == year and cur.month == month:
                date_str = cur.strftime("%Y%m%d")
                result.setdefault(date_str, {})[venue] = race
                added = True
            cur += datetime.timedelta(days=1)
        return added

    def live_all_time_dates(race):
        dates = set()
        for item in race.get("liveAllTime", []) or []:
            s = str(item)

            # 例: 8/14～8/16 10:00～17:00
            m = re.search(
                r"(\d{1,2})/(\d{1,2})\s*[～~\-]\s*"
                r"(\d{1,2})/(\d{1,2})",
                s,
            )
            if m:
                sm, sd, em, ed = map(int, m.groups())
                try:
                    start_date = datetime.date(year, sm, sd)
                    end_date = datetime.date(year, em, ed)
                    if end_date < start_date:
                        continue
                    cur = start_date
                    while cur <= end_date:
                        if cur.year == year and cur.month == month:
                            dates.add(cur.strftime("%Y%m%d"))
                        cur += datetime.timedelta(days=1)
                except Exception:
                    pass
                continue

            # 例: 8/16 13:45～20:50
            m = re.search(r"(\d{1,2})/(\d{1,2})", s)
            if m:
                try:
                    d = datetime.date(year, int(m.group(1)), int(m.group(2)))
                    if d.month == month:
                        dates.add(d.strftime("%Y%m%d"))
                except Exception:
                    pass

        return dates

    for place in body:
        if not isinstance(place, dict):
            continue

        venue = re.sub(r"[\s　]+", "", str(place.get("placeName", "")))
        if venue not in AUTO_MAP:
            continue

        for day in place.get("calendar", []) or []:
            if not isinstance(day, dict):
                continue

            race = day.get("race")
            # [] means no home-track event. outside[] is off-track sales only.
            if not isinstance(race, dict) or not race:
                continue

            added = False

            # 1) 公式の開催期間を最優先。
            start_text = str(race.get("periodStartDate", "") or "").strip()
            end_text = str(race.get("periodEndDate", "") or "").strip()
            if start_text:
                if not end_text:
                    end_text = start_text
                added = add_range(venue, race, start_text, end_text)

            # 2) 開催期間が無い/使えない場合は liveAllTime を展開。
            if not added:
                for date_str in live_all_time_dates(race):
                    result.setdefault(date_str, {})[venue] = race
                    added = True

            # 3) 最後の保険として calendar 側の日付情報を利用。
            if not added:
                iso_date = str(day.get("date", "") or "").strip()
                if re.fullmatch(r"\d{4}-\d{2}-\d{2}", iso_date):
                    d = datetime.datetime.strptime(iso_date, "%Y-%m-%d").date()
                    if d.year == year and d.month == month:
                        result.setdefault(d.strftime("%Y%m%d"), {})[venue] = race
                        added = True

            # 4) month内の weekDate を最後の最後の補助にする。
            if not added:
                week_date = str(day.get("weekDate", "") or "").strip()
                if week_date.isdigit():
                    try:
                        d = datetime.date(year, month, int(week_date))
                        result.setdefault(d.strftime("%Y%m%d"), {})[venue] = race
                    except Exception:
                        pass

    total_dates = len(result)
    total_entries = sum(len(v) for v in result.values())
    print(
        f"AUTORACE CALENDAR {year}-{month:02d}: "
        f"{total_dates}日 / 延べ{total_entries}場を展開"
    )
    return result

def build_autorace_future_epg(tv, target_date, month_schedule, JST, today_display):
    date_str = target_date.strftime("%Y%m%d")
    day_start = datetime.datetime.strptime(
        f"{date_str} {DATA_READY_TIME}", "%Y%m%d %H:%M"
    ).replace(tzinfo=JST)
    day_end = datetime.datetime.strptime(
        f"{date_str} 23:59", "%Y%m%d %H:%M"
    ).replace(tzinfo=JST)

    venues = month_schedule.get(date_str, {})
    handled = 0
    for venue, tvg_id in AUTO_MAP.items():
        race = venues.get(venue)
        if not race:
            add_programme(
                tv, tvg_id, day_start, day_end,
                non_event_title(venue, "オートレース"),
                f"AutoRace.JP公式カレンダーで{today_display}の本場開催はありません。",
            )
            continue

        handled += 1
        grade = clean_epg_meta_text(race.get("gradeName", ""))
        title = clean_epg_meta_text(race.get("title", "")) or clean_epg_meta_text(race.get("titleShort", ""))
        day_type = clean_epg_meta_text(race.get("nighterName", "")) or "デイ"
        emoji = day_emoji(day_type)
        event_day = race.get("paragraphDay", "")
        start_text = str(race.get("liveStartTime", "") or "").strip()
        end_text = str(race.get("liveEndTime", "") or "").strip()

        provisional = False
        try:
            if not start_text or not end_text:
                raise ValueError("official live time unavailable")
            start_dt = datetime.datetime.strptime(
                f"{date_str} {start_text}", "%Y%m%d %H:%M"
            ).replace(tzinfo=JST)
            end_dt = datetime.datetime.strptime(
                f"{date_str} {end_text}", "%Y%m%d %H:%M"
            ).replace(tzinfo=JST)
            if end_dt <= start_dt:
                end_dt += datetime.timedelta(days=1)
        except Exception:
            provisional = True
            start_dt, end_dt, start_text, end_text = build_provisional_times(
                date_str, day_type, JST
            )

        if day_start < start_dt:
            add_programme(
                tv, tvg_id, day_start, start_dt,
                f"⏳ 開催待ち {venue} {emoji}{day_type}",
                f"🏍️ オートレース {venue}\n📢 {title}\n📅 {today_display}",
            )

        parts = ["📅 開催予定", venue, f"{emoji}{day_type}"]
        if grade:
            parts.append(f"【{grade}】")
        if title:
            parts.append(title)
        if event_day:
            parts.append(f"{event_day}日目")
        desc = [f"🏍️ オートレース {venue}"]
        if grade:
            desc.append(f"🏆 グレード: {grade}")
        if title:
            desc.append(f"📢 開催名: {title}")
        if event_day:
            desc.append(f"📅 開催日次: {event_day}日目")
        if provisional:
            parts.append(PROVISIONAL_NOTICE)
            desc.append(f"⏰ 仮予定: {start_text}～{'翌' if end_dt.date() != start_dt.date() else ''}{end_text}")
            desc.append(f"⚠️ {PROVISIONAL_NOTICE}")
        elif start_text and end_text:
            desc.append(f"⏰ 公式LIVE予定: {start_text}～{end_text}")
        desc.append(f"📅 {today_display}")
        add_programme(tv, tvg_id, start_dt, end_dt, " ".join(parts), "\n".join(desc))

        if end_dt.date() == day_start.date() and end_dt < day_end:
            add_programme(
                tv, tvg_id, end_dt, day_end,
                finished_title(venue, "オートレース"),
                f"{venue}の本日のオートレースは全て終了しました。",
            )

    print(f"AUTORACE FUTURE EPG {date_str}: {handled}場を開催予定として生成")
    return True

def build_epg_xml():
    tv = ET.Element(
        "tv",
        {"generator-info-name": "CombinedEPGGenerator"},
    )

    JST = datetime.timezone(datetime.timedelta(hours=9))

    today_str = datetime.datetime.now(JST).strftime("%Y%m%d")

    all_channels = {
        **KEIRIN_MAP,
        **KEIBA_MAP,
        **AUTO_MAP,
        **BOAT_MAP,
        **JRA_STREAM_MAP,
        GCH_DISPLAY_NAME: GCH_TVG_ID,
    }

    for v_name, tvg_id in all_channels.items():
        channel = ET.SubElement(tv, "channel", id=tvg_id)
        ET.SubElement(channel, "display-name").text = v_name

    today_date = datetime.datetime.now(JST).date()
    boat_week = fetch_boat_week_schedule(today_date, EPG_DAYS)
    nar_future = fetch_nar_epg_days(today_date, EPG_DAYS)

    # AutoRace.JP monthly calendar for future-day EPG.
    autorace_future_months = {}
    for offset in range(EPG_DAYS):
        d = today_date + datetime.timedelta(days=offset)
        key = (d.year, d.month)
        if key not in autorace_future_months:
            autorace_future_months[key] = fetch_autorace_future_month(d.year, d.month)

    # KEIRIN.JP monthly schedule for future-day provisional EPG.
    keirin_future_months = {}
    for offset in range(EPG_DAYS):
        d = today_date + datetime.timedelta(days=offset)
        key = (d.year, d.month)
        if key not in keirin_future_months:
            keirin_future_months[key] = fetch_keirin_future_month(
                d.year,
                d.month,
            )

    for day_offset in range(EPG_DAYS):
        target_date = today_date + datetime.timedelta(days=day_offset)
        date_str = target_date.strftime("%Y%m%d")
        today_display = target_date.strftime("%Y年%m月%d日")
        is_today = (day_offset == 0)
        # 00:00～当日データ更新時刻までは次回EPGデータ取得準備中
        midnight = datetime.datetime.strptime(
            f"{date_str} 00:00", "%Y%m%d %H:%M"
        ).replace(tzinfo=JST)

        one_am = datetime.datetime.strptime(
            f"{date_str} {DATA_READY_TIME}", "%Y%m%d %H:%M"
        ).replace(tzinfo=JST)

        preparing_channels = {}
        for name, cid in KEIRIN_MAP.items():
            preparing_channels[cid] = (name, "競輪")
        for name, cid in KEIBA_MAP.items():
            preparing_channels[cid] = (name, "競馬")
        for name, cid in AUTO_MAP.items():
            preparing_channels[cid] = (name, "オートレース")
        for name, cid in BOAT_MAP.items():
            preparing_channels[cid] = (name, "ボートレース")
        for name, cid in JRA_STREAM_MAP.items():
            preparing_channels[cid] = (name, "JRA")

        for cid, (name, category) in preparing_channels.items():
            add_programme(
                tv,
                cid,
                midnight,
                one_am,
                preparing_title(name, category),
                "日付更新後の次回EPGデータ取得・反映を準備しています。",
            )

        # -------------------------------------------------
        # 競輪
        # 今日だけ各Rの実発走時刻・競走名を取得。
        # 取得失敗した開催場はKEIRIN.JP月間開催表の仮時間へフォールバック。
        # 明日・明後日は従来どおりKEIRIN.JP月間開催表＋仮時間。
        # -------------------------------------------------
        month_schedule = keirin_future_months.get(
            (target_date.year, target_date.month),
            {},
        )
        if is_today:
            build_keirin_today_with_fallback(
                tv,
                target_date,
                month_schedule,
                JST,
                today_display,
            )
        else:
            build_keirin_future_epg(
                tv,
                target_date,
                month_schedule,
                JST,
                today_display,
            )

        # -------------------------------------------------
        # 競馬
        # NAR公式の指定日出馬表から3日分を直接取得。
        # 各R時刻が取れない場合でも開催が確認できれば仮時間表示へ回す。
        # -------------------------------------------------
        used_nar = build_keiba_race_epg(
            tv,
            date_str,
            nar_future.get(date_str, {}),
            JST,
            today_display,
        )
        if not used_nar:
            regular_keiba_map = dict(KEIBA_MAP)
            build_future_placeholder(
                tv,
                date_str,
                regular_keiba_map,
                "競馬",
                "🏇",
                JST,
                today_display,
            )

        # JRA EAST / WEST / HOKKAIDO はJRA公式から3日分を生成。
        # GCHは全日ループ終了後に guides.xml から3日分だけ統合する。
        build_jra_stream_epg(
            tv,
            target_date,
            JST,
            today_display,
        )

        # -------------------------------------------------
        # オートレース
        # AutoRace.JP公式カレンダーから3日分を直接生成。
        # LIVE時刻が無い場合は開催区分ごとの仮時間を明示して使用する。
        # -------------------------------------------------
        month_schedule = autorace_future_months.get(
            (target_date.year, target_date.month),
            {},
        )
        if is_today:
            autorace_today = fetch_autorace_today_exact(target_date, month_schedule)
            used_autorace_exact = build_autorace_race_epg(
                tv, date_str, autorace_today, JST, today_display
            )
            if not used_autorace_exact:
                build_autorace_future_epg(
                    tv, target_date, month_schedule, JST, today_display
                )
        else:
            build_autorace_future_epg(
                tv, target_date, month_schedule, JST, today_display
            )

        # -------------------------------------------------
        # ボートレース
        # BOAT RACE公式サイトの指定日開催一覧 + raceindex を使用。
        # 実時刻が取得できれば実時刻、開催確認済みで時刻不明なら仮時間。
        # 公式ページ自体を取得できない場合は「開催情報確認待ち」とする。
        # -------------------------------------------------
        used_boat_official = build_boat_race_epg(
            tv,
            date_str,
            boat_week,
            JST,
            today_display,
        )

        if not used_boat_official:
            day_start = datetime.datetime.strptime(
                f"{date_str} {DATA_READY_TIME}", "%Y%m%d %H:%M"
            ).replace(tzinfo=JST)
            day_end = datetime.datetime.strptime(
                f"{date_str} 23:59", "%Y%m%d %H:%M"
            ).replace(tzinfo=JST)

            for v_name, tvg_id in BOAT_MAP.items():
                add_programme(
                    tv,
                    tvg_id,
                    day_start,
                    day_end,
                    f"⏳ 開催情報確認待ち {v_name}（ボートレース）",
                    f"BOAT RACE公式の{today_display}開催情報を取得できませんでした。\n"
                    "開催・非開催をまだ確定していません。",
                )

    # -------------------------------------------------
    # グリーンチャンネル
    # karenda-jp guides.xml から該当チャンネルだけ3日分抽出して統合。
    # -------------------------------------------------
    gch_programme_count = import_gch_from_guides(
        tv,
        today_date,
        EPG_DAYS,
        JST,
    )

    tree = ET.ElementTree(tv)

    if hasattr(ET, "indent"):
        ET.indent(tree, space="    ")

    tree.write(
        "epg.xml",
        encoding="utf-8",
        xml_declaration=True,
    )

    print("")
    print("============================")
    print("EPG生成完了")
    print("ボートEPG: BOAT RACE公式から3日分を直接取得（時刻不明時は仮時間表示）")
    print("競馬: NAR公式から3日分を直接取得（時刻不明時は仮時間表示）")
    print("競輪: KEIRIN.JP公式月間表から3日分を直接生成（仮時間表示）")
    print("オート: 当日は公式出走表から各R、明日以降は公式カレンダーから生成")
    print("JRA: EAST / WEST / HOKKAIDOをJRA公式から生成（40分以上の間隔は休憩表示）")
    print(f"GCH: guides.xmlから3日分を抽出・統合とか ({gch_programme_count}番組)")
    print("出力: epg.xml")
    print("============================")


if __name__ == "__main__":
    build_epg_xml()
