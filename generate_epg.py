import datetime
import xml.etree.ElementTree as ET
import requests

KEIRIN_MAP = {
    "函館": ["函館"], "青森": ["青森"], "いわき平": ["いわき平", "いわき", "平"],
    "弥彦": ["弥彦"], "前橋": ["前橋"], "取手": ["取手"],
    "宇都宮": ["宇都宮"], "大宮": ["大宮"], "西武園": ["西武園"],
    "京王閣": ["京王閣"], "立川": ["立川"], "松戸": ["松戸"],
    "川崎": ["川崎"], "平塚": ["平塚"], "小田原": ["小田原"],
    "伊東温泉": ["伊東温泉", "伊東"], "静岡": ["静岡"], "名古屋": ["名古屋"],
    "岐阜": ["岐阜"], "大垣": ["大垣"], "豊橋": ["豊橋"],
    "松阪": ["松阪"], "四日市": ["四日市"], "富山": ["富山"],
    "福井": ["福井"], "奈良": ["奈良"], "岸和田": ["岸和田"],
    "和歌山": ["和歌山"], "玉野": ["玉野"], "広島": ["広島"],
    "防府": ["防府"], "小松島": ["小松島"], "松山": ["松山"],
    "高知": ["高知"], "小倉": ["小倉"], "久留米": ["久留米"],
    "武雄": ["武雄"], "佐世保": ["佐世保"], "別府": ["別府"],
    "熊本": ["熊本"], "千葉PIST6": ["PIST6", "千葉"]
}

KEIBA_MAP = {
    "帯広競馬(ばんえい)": ["帯広", "ばんえい"], "ホッカイドウ競馬(門別)": ["門別"],
    "岩手競馬(盛岡)": ["盛岡"], "岩手競馬(水沢)": ["水沢"],
    "南関東競馬(浦和)": ["浦和"], "南関東競馬(船橋)": ["船橋"],
    "南関東競馬(大井)": ["大井"], "南関東競馬(川崎)": ["川崎"],
    "金沢競馬": ["金沢"], "名古屋競馬": ["名古屋"],
    "笠松競馬": ["笠松"], "園田競馬": ["園田"],
    "姫路競馬": ["姫路"], "高知競馬": ["高知"],
    "佐賀競馬": ["佐賀"], "ＪＲＡ公式": ["JRA", "中央競馬"], "ＪＲＡグリーン": ["JRA", "中央競馬"]
}

AUTO_MAP = {
    "川口": ["川口"], "伊勢崎": ["伊勢崎"], "浜松": ["浜松"],
    "飯塚": ["飯塚"], "山陽": ["山陽"]
}

KEIRIN_IDS = {
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

KEIBA_IDS = {
    "帯広競馬(ばんえい)": "chihou.obihiro", "ホッカイドウ競馬(門別)": "chihou.mombetsu",
    "岩手競馬(盛岡)": "chihou.morioka", "岩手競馬(水沢)": "chihou.mizusawa",
    "南関東競馬(浦和)": "chihou.urawa", "南関東競馬(船橋)": "chihou.funabashi",
    "南関東競馬(大井)": "chihou.oi", "南関東競馬(川崎)": "chihou.kawasaki_keiba",
    "金沢競馬": "chihou.kanazawa", "名古屋競馬": "chihou.nagoya_keiba",
    "笠松競馬": "chihou.kasamatsu", "園田競馬": "chihou.sonoda",
    "姫路競馬": "chihou.himeji", "高知競馬": "chihou.kochi_keiba",
    "佐賀競馬": "chihou.saga", "ＪＲＡ公式": "jra.official", "ＪＲＡグリーン": "jra.green"
}

AUTO_IDS = {
    "川口": "auto.kawaguchi", "伊勢崎": "auto.isesaki", "浜松": "auto.hamamatsu",
    "飯塚": "auto.iizuka", "山陽": "auto.sanyo"
}

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}


def get_html_with_proxy(target_url):
    """海外IPブロック回避用プロキシ経由取得"""
    proxies = [
        f"https://api.allorigins.win/raw?url={target_url}",
        f"https://corsproxy.io/?{target_url}",
        target_url
    ]
    for url in proxies:
        try:
            res = requests.get(url, headers=HEADERS, timeout=10)
            if res.status_code == 200 and len(res.text) > 300:
                return res.text
        except Exception:
            pass
    return ""


def fetch_keirin(today_str):
    active = set()
    html = get_html_with_proxy("https://keirin.kdr.rakuten.co.jp/")
    if not html:
        html = get_html_with_proxy(f"https://keirin.jp/pc/dfw/datainfo/SCHEDULE/schedule_{today_str[:6]}.json")

    if html:
        for venue_name, aliases in KEIRIN_MAP.items():
            for alias in aliases:
                if alias in html:
                    active.add(venue_name)
                    break
    return active


def fetch_keiba():
    active = {}
    html = get_html_with_proxy("https://nar.netkeiba.com/top/")
    if not html:
        html = get_html_with_proxy("https://keiba.rakuten.co.jp/")

    if html:
        for venue_name, aliases in KEIBA_MAP.items():
            if "ＪＲＡ" not in venue_name:
                for alias in aliases:
                    if alias in html:
                        active[venue_name] = "【本日開催】"
                        break

    now = datetime.datetime.now()
    if now.weekday() in [5, 6]:
        active["ＪＲＡ公式"] = "【本日開催】 (中央競馬)"
        active["ＪＲＡグリーン"] = "【本日開催】 (中央競馬)"

    return active


def fetch_auto():
    active = set()
    html = get_html_with_proxy("https://sp.autorace.jp/")
    if html:
        for venue_name, aliases in AUTO_MAP.items():
            for alias in aliases:
                if alias in html:
                    active.add(venue_name)
                    break
    return active


def add_channel_program(tv, id_map, active_data, today_str, now):
    today_display = now.strftime("%Y年%m月%d日")

    for v_name, tvg_id in id_map.items():
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

    keirin_active = fetch_keirin(today_str)
    keiba_active = fetch_keiba()
    auto_active = fetch_auto()

    print(f"競輪検出: {list(keirin_active)}")
    print(f"地方競馬検出: {list(keiba_active.keys())}")
    print(f"オートレース検出: {list(auto_active)}")

    add_channel_program(tv, KEIRIN_IDS, keirin_active, today_str, now)
    add_channel_program(tv, KEIBA_IDS, keiba_active, today_str, now)
    add_channel_program(tv, AUTO_IDS, auto_active, today_str, now)

    tree = ET.ElementTree(tv)
    if hasattr(ET, "indent"):
        ET.indent(tree, space="  ")
    tree.write("epg.xml", encoding="utf-8", xml_declaration=True)
    print("epg.xml の生成が完了しました。")


if __name__ == "__main__":
    build_epg_xml()
