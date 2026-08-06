import datetime
import xml.etree.ElementTree as ET
import requests

# 競輪のIDマッピング
KEIRIN_MAP = {
    "函館": "keirin.hakodate", "青森": "keirin.aomori", "いわき平": "keirin.iwakitaira",
    "弥彦": "keirin.yahiko", "前橋": "keirin.maebashi", "取手": "keirin.toride",
    "宇都宮": "keirin.utsunomiya", "大宮": "keirin.omiya", "西武園": "keirin.seibuen",
    "京王閣": "keirin.keiogatsu", "立川": "keirin.tachikawa", "松戸": "keirin.matsudo",
    "川崎": "keirin.kawasaki", "平塚": "keirin.hiratsuka", "小田原": "keirin.odawara",
    "伊東温泉": "keirin.ito", "静岡": "keirin.shizuoka", "名古屋": "keirin.nagoya",
    "岐阜": "keirin.gifu", "大垣": "keirin.ogaki", "豊橋": "keirin.toyohashi",
    "松阪": "keirin.matsusaka", "四日市": "keirin.yokkaichi", "富山": "keirin.toyama",
    "福井": "keirin.fukui", "奈良": "keirin.nara", "岸和田": "keirin.kishiwada",
    "和歌山": "keirin.wakayama", "玉野": "keirin.tamano", "広島": "keirin.hiroshima",
    "防府": "keirin.hofu", "小松島": "keirin.komatsushima", "松山": "keirin.matsuyama",
    "高知": "keirin.kochi", "小倉": "keirin.kokura", "久留米": "keirin.kurume",
    "武雄": "keirin.takeo", "佐世保": "keirin.sasebo", "別府": "keirin.beppu",
    "熊本": "keirin.kumamoto", "千葉PIST6": "keirin.pist6"
}

# 競馬のIDマッピング
KEIBA_MAP = {
    "帯広競馬(ばんえい)": "chihou.obihiro", "ホッカイドウ競馬(門別)": "chihou.mombetsu",
    "岩手競馬(盛岡)": "chihou.morioka", "岩手競馬(水沢)": "chihou.mizusawa",
    "南関東競馬(浦和)": "chihou.urawa", "南関東競馬(船橋)": "chihou.funabashi",
    "南関東競馬(大井)": "chihou.oi", "南関東競馬(川崎)": "chihou.kawasaki_keiba",
    "金沢競馬": "chihou.kanazawa", "名古屋競馬": "chihou.nagoya_keiba",
    "笠松競馬": "chihou.kasamatsu", "園田競馬": "chihou.sonoda",
    "姫路競馬": "chihou.himeji", "高知競馬": "chihou.kochi_keiba",
    "佐賀競馬": "chihou.saga", "ＪＲＡ公式": "jra.official", "ＪＲＡグリーン": "jra.green"
}

# オートレースのIDマッピング
AUTO_MAP = {
    "川口": "auto.kawaguchi", "伊勢崎": "auto.isesaki", "浜松": "auto.hamamatsu",
    "飯塚": "auto.iizuka", "山陽": "auto.sanyo"
}


def fetch_keirin_schedule(date_str):
    """競輪の本日開催情報を取得（複数ルート取得）"""
    active = {}
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    # ルート1: KEIRIN.JP 公式月間JSON
    try:
        url = f"https://keirin.jp/pc/dfw/datainfo/SCHEDULE/schedule_{date_str[:6]}.json"
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            data = res.json()
            for item in data:
                if str(item.get("hd")) == date_str:
                    v_name = item.get("joName")
                    if v_name in KEIRIN_MAP:
                        active[v_name] = {
                            "day_num": item.get("kaiDayName", ""),
                            "grade": item.get("gradeName", ""),
                            "last_time": item.get("lastRaceTime", "")
                        }
            if active:
                return active
    except Exception:
        pass

    # ルート2: オッズパークの当日常設開催データ（予備）
    try:
        url = "https://www.oddspark.com/keirin/JsonObject.do"
        res = requests.get(url, headers=headers, timeout=5)
        if res.status_code == 200:
            for item in res.json().get("joList", []):
                v_name = item.get("joName")
                if v_name in KEIRIN_MAP:
                    active[v_name] = {
                        "day_num": item.get("day", ""),
                        "grade": item.get("grade", ""),
                        "last_time": item.get("lastRaceTime", "")
                    }
    except Exception:
        pass

    return active


def add_channel_program(tv, map_dict, active_dict, today_str, now):
    today_display = now.strftime("%Y年%m月%d日")

    for v_name, tvg_id in map_dict.items():
        # <channel> の作成
        channel = ET.SubElement(tv, "channel", id=tvg_id)
        disp = ET.SubElement(channel, "display-name")
        disp.text = v_name

        start_xml = f"{today_str}000000 +0900"
        stop_xml = f"{today_str}235959 +0900"

        # 開催状況判定
        if v_name in active_dict:
            info = active_dict[v_name]
            day_num = info.get("day_num", "")
            grade = info.get("grade", "")
            last_time = info.get("last_time", "")

            is_finished = False
            if last_time:
                try:
                    lh, lm = map(int, last_time.split(":"))
                    last_dt = now.replace(hour=lh, minute=lm, second=0) + datetime.timedelta(minutes=30)
                    if now > last_dt:
                        is_finished = True
                except ValueError:
                    pass

            if is_finished:
                title_text = "本日のレースは全レース終了しました"
                desc_text = f"{today_display} {day_num} ({grade}) の全レースおよび払戻は終了いたしました。"
            else:
                title_text = f"【開催】{day_num} ({grade})".strip()
                if title_text == "【開催】 ()":
                    title_text = "【本日開催】"
                desc_text = f"{today_display} {v_name} 開催中"
                if last_time:
                    desc_text += f"（最終R発走予定 {last_time} 頃）"
        else:
            title_text = "本日非開催"
            desc_text = f"{today_display} 本日のレース開催はありません。"

        # <programme> の作成
        prog = ET.SubElement(tv, "programme", start=start_xml, stop=stop_xml, channel=tvg_id)
        t_elem = ET.SubElement(prog, "title", lang="ja")
        t_elem.text = title_text
        d_elem = ET.SubElement(prog, "desc", lang="ja")
        d_elem.text = desc_text


def build_epg_xml():
    now = datetime.datetime.now()
    today_str = now.strftime("%Y%m%d")

    tv = ET.Element("tv", {"generator-info-name": "CombinedEPGGenerator"})

    # 本日の競輪データ取得
    keirin_active = fetch_keirin_schedule(today_str)

    # XML要素生成
    add_channel_program(tv, KEIRIN_MAP, keirin_active, today_str, now)
    add_channel_program(tv, KEIBA_MAP, {}, today_str, now)
    add_channel_program(tv, AUTO_MAP, {}, today_str, now)

    # XML書き出し
    tree = ET.ElementTree(tv)
    ET.indent(tree, space="  ")
    tree.write("epg.xml", encoding="utf-8", xml_declaration=True)
    print("生成処理完了")


if __name__ == "__main__":
    build_epg_xml()
