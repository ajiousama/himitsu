import datetime
import re
import xml.etree.ElementTree as ET
import requests

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

AUTO_MAP = {
    "川口": "auto.kawaguchi", "伊勢崎": "auto.isesaki", "浜松": "auto.hamamatsu",
    "飯塚": "auto.iizuka", "山陽": "auto.sanyo"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}


def fetch_speedchannel(today_str):
    """スピードチャンネルの番組表JSONから競輪開催場を抽出"""
    active = {}
    url = f"https://www.speedchannel.co.jp/program/json/{today_str}.json"
    try:
        res = requests.get(url, headers=HEADERS, timeout=5)
        if res.status_code == 200:
            data = res.json()
            for item in data.get("programs", []):
                title = item.get("title", "") + item.get("detail", "")
                for v_name in KEIRIN_MAP.keys():
                    if v_name in title or v_name.replace("温泉", "") in title:
                        if "終了" in title or "発売終了" in title:
                            active[v_name] = "【本日開催】 (発売終了)"
                        else:
                            active[v_name] = "【本日開催】 (中継中)"
    except Exception:
        pass

    # フォールバック（オッズパーク競輪）
    if not active:
        try:
            res = requests.get("https://www.oddspark.com/keirin/", headers=HEADERS, timeout=5)
            if res.status_code == 200:
                html = res.text
                for k in KEIRIN_MAP.keys():
                    if f">{k}<" in html or f'"{k}"' in html or f"{k}競輪" in html:
                        active[k] = "【本日開催】"
        except Exception:
            pass

    return active


def fetch_keiba_livemovie():
    """楽天競馬 ライブ動画ページ（livemovie）から正確に抽出"""
    active = {}
    try:
        url = "https://keiba.rakuten.co.jp/livemovie"
        res = requests.get(url, headers=HEADERS, timeout=5)
        if res.status_code == 200:
            html = res.text
            for map_key in KEIBA_MAP.keys():
                if "ＪＲＡ" not in map_key:
                    short = map_key.replace("競馬", "").replace("南関東", "").replace("ホッカイドウ", "").replace("岩手", "").replace("(ばんえい)", "").replace("(門別)", "").replace("(盛岡)", "").replace("(水沢)", "").replace("(浦和)", "").replace("(船橋)", "").replace("(大井)", "").replace("(川崎)", "")
                    
                    if short in html:
                        idx = html.find(short)
                        snippet = html[idx:idx + 300]
                        if "本日発売終了" in snippet or "発売終了" in snippet:
                            active[map_key] = "【本日開催】 (発売終了)"
                        elif "発走" in snippet or "R" in snippet or "まもなく" in snippet or "ライブ映像" in snippet:
                            active[map_key] = "【本日開催】 (発売中)"
    except Exception as e:
        print(f"地方競馬エラー: {e}")

    # JRA（土日判定）
    now = datetime.datetime.now()
    if now.weekday() in [5, 6]:
        active["ＪＲＡ公式"] = "【本日開催】 (中央競馬)"
        active["ＪＲＡグリーン"] = "【本日開催】 (中央競馬)"

    return active


def fetch_auto():
    """オッズパークからのオートレース判定"""
    active = set()
    try:
        res = requests.get("https://www.oddspark.com/autorace/", headers=HEADERS, timeout=5)
        if res.status_code == 200:
            html = res.text
            for k in AUTO_MAP.keys():
                if k in html:
                    idx = html.find(k)
                    snippet = html[idx:idx + 250] if idx != -1 else ""
                    if "R" in snippet or "前売" in snippet or "投票" in snippet or "発走" in snippet:
                        active.add(k)
    except Exception as e:
        print(f"オートレースエラー: {e}")
    return active


def build_epg_xml():
    now = datetime.datetime.now()
    today_str = now.strftime("%Y%m%d")
    today_display = now.strftime("%Y年%m月%d日")

    tv = ET.Element("tv", {"generator-info-name": "CombinedEPGGenerator"})

    keirin_active = fetch_speedchannel(today_str)
    keiba_active = fetch_keiba_livemovie()
    auto_active = fetch_auto()

    print(f"競輪検出: {keirin_active}")
    print(f"地方競馬検出: {keiba_active}")
    print(f"オートレース検出: {list(auto_active)}")

    def add_channels(map_dict, active_data):
        for v_name, tvg_id in map_dict.items():
            channel = ET.SubElement(tv, "channel", id=tvg_id)
            disp = ET.SubElement(channel, "display-name")
            disp.text = v_name

            start_xml = f"{today_str}000000 +0900"
            stop_xml = f"{today_str}235959 +0900"

            is_active = False
            title_text = "【本日開催】"

            if isinstance(active_data, dict) and v_name in active_data:
                is_active = True
                title_text = active_data[v_name]
            elif isinstance(active_data, set) and v_name in active_data:
                is_active = True

            if is_active:
                desc_text = f"{today_display} {v_name} レース開催中 ({title_text})"
            else:
                title_text = "本日非開催"
                desc_text = f"{today_display} 本日のレース開催はありません。"

            prog = ET.SubElement(tv, "programme", start=start_xml, stop=stop_xml, channel=tvg_id)
            t_elem = ET.SubElement(prog, "title", lang="ja")
            t_elem.text = title_text
            d_elem = ET.SubElement(prog, "desc", lang="ja")
            d_elem.text = desc_text

    add_channels(KEIRIN_MAP, keirin_active)
    add_channels(KEIBA_MAP, keiba_active)
    add_channels(AUTO_MAP, auto_active)

    tree = ET.ElementTree(tv)
    if hasattr(ET, "indent"):
        ET.indent(tree, space="  ")
    tree.write("epg.xml", encoding="utf-8", xml_declaration=True)
    print("epg.xml の生成が完了しました。")


if __name__ == "__main__":
    build_epg_xml()
