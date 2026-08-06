import datetime
import re
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

# 地方競馬・JRAのIDマッピング
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

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def fetch_keirin_schedule(date_str):
    """KEIRIN.JP公式から本日の開催日程を取得"""
    active = {}
    url = f"https://keirin.jp/pc/dfw/datainfo/SCHEDULE/schedule_{date_str[:6]}.json"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            for item in res.json():
                if str(item.get("hd")) == date_str:
                    v_name = item.get("joName", "").strip()
                    if v_name in KEIRIN_MAP:
                        active[v_name] = {
                            "day_num": item.get("kaiDayName", ""),
                            "grade": item.get("gradeName", ""),
                            "last_time": item.get("lastRaceTime", "")
                        }
    except Exception as e:
        print(f"競輪取得エラー: {e}")
    return active


def fetch_jra_official_schedule():
    """JRA（www.jra.go.jp）公式サイトから本日の開催場一覧を直接抽出"""
    jra_venues = []
    try:
        # JRA本日の開催出馬表トップ
        url = "https://www.jra.go.jp/keiba/"
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.encoding = res.apparent_encoding
        if res.status_code == 200:
            html = res.text
            # 競馬場名の正規表現抽出（例: 1回東京5日 -> 東京）
            matches = re.findall(r'(\d+回(札幌|函館|福島|新潟|東京|中山|中京|京都|阪神|小倉)\d+日)', html)
            found_set = set()
            for m in matches:
                found_set.add(m[1])
            jra_venues = sorted(list(found_set))
    except Exception as e:
        print(f"JRA公式取得エラー: {e}")

    return jra_venues


def fetch_keiba_schedule(date_str):
    """地方競馬およびJRA（公式サイト連携）の本日開催情報を取得"""
    active = {}

    # 1. 地方競馬の取得 (オッズパークAPI)
    try:
        url = "https://www.oddspark.com/keiba/JsonObject.do"
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            data = res.json()
            for item in data.get("joList", []):
                v_name = item.get("joName", "").strip()
                for map_key in KEIBA_MAP.keys():
                    if "ＪＲＡ" not in map_key and v_name in map_key:
                        active[map_key] = {
                            "day_num": item.get("day", ""),
                            "grade": item.get("title", ""),
                            "last_time": item.get("lastRaceTime", "")
                        }
    except Exception as e:
        print(f"地方競馬取得エラー: {e}")

    # 2. JRA公式サイトから直接抽出した開催場の紐付け
    jra_venues = fetch_jra_official_schedule()
    if jra_venues:
        jra_desc = "・".join(jra_venues) + "競馬"
        active["ＪＲＡ公式"] = {"day_num": "中央競馬", "grade": jra_desc, "last_time": "16:30"}
        active["ＪＲＡグリーン"] = {"day_num": "中央競馬", "grade": jra_desc, "last_time": "16:30"}

    return active


def fetch_auto_schedule(date_str):
    """オートレース公式から本日の開催日程を取得"""
    active = {}
    try:
        url = "https://www.oddspark.com/autorace/JsonObject.do"
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            data = res.json()
            for item in data.get("joList", []):
                v_name = item.get("joName", "").strip()
                if v_name in AUTO_MAP:
                    active[v_name] = {
                        "day_num": item.get("day", ""),
                        "grade": item.get("title", ""),
                        "last_time": item.get("lastRaceTime", "")
                    }
    except Exception as e:
        print(f"オートレース取得エラー: {e}")
    return active


def add_channel_program(tv, map_dict, active_dict, today_str, now):
    today_display = now.strftime("%Y年%m月%d日")

    for v_name, tvg_id in map_dict.items():
        channel = ET.SubElement(tv, "channel", id=tvg_id)
        disp = ET.SubElement(channel, "display-name")
        disp.text = v_name

        start_xml = f"{today_str}000000 +0900"
        stop_xml = f"{today_str}235959 +0900"

        if v_name in active_dict:
            info = active_dict[v_name]
            day_num = info.get("day_num", "").strip()
            grade = info.get("grade", "").strip()
            last_time = info.get("last_time", "").strip()

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
                title_parts = [p for p in [day_num, grade] if p]
                suffix = f" ({' '.join(title_parts)})" if title_parts else ""
                title_text = f"【開催】{suffix}".strip()
                if title_text in ["【開催】 ()", "【開催】"]:
                    title_text = "【本日開催】"
                desc_text = f"{today_display} {v_name} 開催中"
                if grade:
                    desc_text += f"（{grade}）"
                if last_time:
                    desc_text += f" [最終R発走予定 {last_time} 頃]"
        else:
            title_text = "本日非開催"
            desc_text = f"{today_display} 本日のレース開催はありません。"

        prog = ET.SubElement(tv, "programme", start=start_xml, stop=stop_xml, channel=tvg_id)
        t_elem = ET.SubElement(prog, "title", lang="ja")
        t_elem.text = title_text
        d_elem = ET.SubElement(prog, "desc", lang="ja")
        d_elem.text = desc_text


def build_epg_xml():
    now = datetime.datetime.now()
    today_str = now.strftime("%Y%m%d")

    tv = ET.Element("tv", {"generator-info-name": "CombinedEPGGenerator"})

    # 全競技の本日開催データ取得
    keirin_active = fetch_keirin_schedule(today_str)
    keiba_active = fetch_keiba_schedule(today_str)
    auto_active = fetch_auto_schedule(today_str)

    print(f"競輪開催: {list(keirin_active.keys())}")
    print(f"競馬開催: {list(keiba_active.keys())}")
    print(f"オート開催: {list(auto_active.keys())}")

    # XML要素生成
    add_channel_program(tv, KEIRIN_MAP, keirin_active, today_str, now)
    add_channel_program(tv, KEIBA_MAP, keiba_active, today_str, now)
    add_channel_program(tv, AUTO_MAP, auto_active, today_str, now)

    tree = ET.ElementTree(tv)
    ET.indent(tree, space="  ")
    tree.write("epg.xml", encoding="utf-8", xml_declaration=True)
    print("epg.xml の自動生成が完了しました。")


if __name__ == "__main__":
    build_epg_xml()
