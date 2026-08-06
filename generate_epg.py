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
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}


def fetch_winticket():
    """WINTICKETから競輪とオートレースの本日開催場を取得"""
    active_keirin = set()
    active_auto = set()
    try:
        url = "https://www.winticket.jp/api/v1/races/today"
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            data = res.json()
            for race in data.get("keirinRaces", []):
                jojo = race.get("venueName", "")
                for k in KEIRIN_MAP.keys():
                    if k in jojo:
                        active_keirin.add(k)
            for race in data.get("autoRaces", []):
                jojo = race.get("venueName", "")
                for a in AUTO_MAP.keys():
                    if a in jojo:
                        active_auto.add(a)
    except Exception as e:
        print(f"WINTICKET取得エラー: {e}")

    # APIフォールバック（HTML判定）
    if not active_keirin:
        try:
            res_html = requests.get("https://www.winticket.jp/keirin", headers=HEADERS, timeout=10)
            if res_html.status_code == 200:
                for k in KEIRIN_MAP.keys():
                    if k in res_html.text:
                        active_keirin.add(k)
        except Exception:
            pass

    return active_keirin, active_auto


def fetch_keiba():
    """楽天競馬（地方競馬）およびJRA公式サイトから本日開催情報を取得"""
    active = {}

    # 1. 楽天競馬トップページから地方競馬の開催場を取得
    try:
        url = "https://keiba.rakuten.co.jp/"
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            html = res.text
            for map_key in KEIBA_MAP.keys():
                if "ＪＲＡ" not in map_key:
                    # 地名部分だけ取り出して検索（例: "大井", "園田", "帯広" など）
                    short_name = map_key.replace("競馬", "").replace("南関東", "").replace("ホッカイドウ", "").replace("岩手", "").replace("(ばんえい)", "").replace("(門別)", "").replace("(盛岡)", "").replace("(水沢)", "").replace("(浦和)", "").replace("(船橋)", "").replace("(大井)", "").replace("(川崎)", "")
                    if short_name and short_name in html:
                        active[map_key] = "【本日開催】"
    except Exception as e:
        print(f"楽天競馬取得エラー: {e}")

    # 2. JRA公式サイトから直接抽出
    try:
        url = "https://www.jra.go.jp/keiba/"
        res = requests.get(url, headers=HEADERS, timeout=10)
        res.encoding = res.apparent_encoding
        if res.status_code == 200:
            matches = re.findall(r'(\d+回(札幌|函館|福島|新潟|東京|中山|中京|京都|阪神|小倉)\d+日)', res.text)
            found = sorted(list(set([m[1] for m in matches])))
            if found:
                jra_desc = "・".join(found) + "競馬"
                active["ＪＲＡ公式"] = f"【開催】 ({jra_desc})"
                active["ＪＲＡグリーン"] = f"【開催】 ({jra_desc})"
    except Exception as e:
        print(f"JRA取得エラー: {e}")

    return active


def add_channel_program(tv, map_dict, active_dict_or_set, today_str, now):
    today_display = now.strftime("%Y年%m月%d日")

    for v_name, tvg_id in map_dict.items():
        channel = ET.SubElement(tv, "channel", id=tvg_id)
        disp = ET.SubElement(channel, "display-name")
        disp.text = v_name

        start_xml = f"{today_str}000000 +0900"
        stop_xml = f"{today_str}235959 +0900"

        # dict または set に含まれているか判定
        is_active = False
        title_text = "【本日開催】"

        if isinstance(active_dict_or_set, dict):
            if v_name in active_dict_or_set:
                is_active = True
                title_text = active_dict_or_set[v_name]
        elif isinstance(active_dict_or_set, set):
            if v_name in active_dict_or_set:
                is_active = True

        if is_active:
            desc_text = f"{today_display} {v_name} レース開催中"
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

    # データ取得
    keirin_active, auto_active = fetch_winticket()
    keiba_active = fetch_keiba()

    print(f"競輪検出: {list(keirin_active)}")
    print(f"競馬検出: {list(keiba_active.keys())}")
    print(f"オート検出: {list(auto_active)}")

    # XML書き出し
    add_channel_program(tv, KEIRIN_MAP, keirin_active, today_str, now)
    add_channel_program(tv, KEIBA_MAP, keiba_active, today_str, now)
    add_channel_program(tv, AUTO_MAP, auto_active, today_str, now)

    tree = ET.ElementTree(tv)
    if hasattr(ET, "indent"):
        ET.indent(tree, space="  ")
    tree.write("epg.xml", encoding="utf-8", xml_declaration=True)
    print("epg.xml の生成が完了しました。")


if __name__ == "__main__":
    build_epg_xml()
