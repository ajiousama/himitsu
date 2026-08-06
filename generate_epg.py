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
    "伊東": "keirin.ito", "静岡": "keirin.shizuoka", "名古屋": "keirin.nagoya",
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
    "佐賀競馬": "chihou.saga", 
    "ＪＲＡ公式": "jra.official", "ＪＲＡグリーン": "jra.green"
}

AUTO_MAP = {
    "川口": "auto.kawaguchi", "伊勢崎": "auto.isesaki", "浜松": "auto.hamamatsu",
    "飯塚": "auto.iizuka", "山陽": "auto.sanyo"
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

def get_tags(snippet):
    tags = []
    if any(x in snippet for x in ["morning", "モーニング", "🌅"]): tags.append("モーニング🌅")
    if any(x in snippet for x in ["night", "ナイター", "🌙", "☆"]): tags.append("ナイター🌙")
    if any(x in snippet for x in ["midnight", "ミッドナイト", "⭐"]): tags.append("ミッドナイト⭐")
    if any(x in snippet for x in ["girl", "ガールズ", "💛"]): tags.append("ガールズ💛")
    if any(x in snippet for x in ["重賞", "Jpn", "SG", "GI", "重"]): tags.append("重賞🔥")
    return tags

def fetch_keirin():
    active = {}
    try:
        res = requests.get("https://www.winticket.jp/keirin/schedules", headers=HEADERS, timeout=5)
        if res.status_code == 200:
            today = datetime.date.today()
            month_day_str = f"{today.month}月{today.day}日"
            for k in KEIRIN_MAP.keys():
                pos = 0
                while True:
                    idx = res.text.find(k, pos)
                    if idx == -1:
                        break
                    snippet = res.text[max(0, idx-100):idx+500]
                    if month_day_str in snippet and "非開催" not in snippet:
                        tags = get_tags(snippet)
                        if not tags: tags = ["デイ"]
                        active[k] = f"【本日開催】 ({' '.join(tags)})"
                        break
                    pos = idx + len(k)
    except Exception as e:
        print(f"競輪取得スキップ: {e}")
    return active

def fetch_keiba():
    active = {}
    try:
        res = requests.get("https://keiba.rakuten.co.jp/calendar", headers=HEADERS, timeout=5)
        if res.status_code == 200:
            html = res.text
            for map_key in KEIBA_MAP.keys():
                if "ＪＲＡ" not in map_key and "競馬" in map_key:
                    if map_key in html:
                        idx = html.find(map_key)
                        snippet = html[idx:idx + 1500]
                        if "開催" in snippet or "重賞" in snippet or "Jpn" in snippet:
                            tags = get_tags(snippet)
                            if not tags: tags = ["デイ"]
                            active[map_key] = f"【本日開催】 ({' '.join(tags)})"
    except Exception as e:
        print(f"地方競馬取得スキップ: {e}")

    now = datetime.datetime.now()
    if now.weekday() in [5, 6]:
        active["ＪＲＡ公式"] = "【本日開催】 (デイ) (中央競馬開催中)"
        active["ＪＲＡグリーン"] = "【本日開催】 (デイ) (中央競馬中継)"

    return active

def fetch_autorace():
    active = {}
    try:
        res = requests.get("https://autorace.jp/calendar/first/", headers=HEADERS, timeout=5)
        if res.status_code == 200:
            html = res.text
            for k in AUTO_MAP.keys():
                if k in html:
                    idx = html.find(k)
                    snippet = html[idx:idx + 1500]
                    if "開催" in snippet or "ナイター" in snippet or "ミッドナイト" in snippet or "SG" in snippet or "GI" in snippet:
                        tags = get_tags(snippet)
                        if not tags: tags = ["デイ"]
                        active[k] = f"【本日開催】 ({' '.join(tags)})"
    except Exception as e:
        print(f"オートレース取得スキップ: {e}")
    return active

def build_epg_xml():
    tv = ET.Element("tv", {"generator-info-name": "CombinedEPGGenerator"})
    today = datetime.datetime.now().strftime("%Y%m%d")
    today_display = datetime.datetime.now().strftime("%Y年%m月%d日")

    keirin = fetch_keirin()
    keiba = fetch_keiba()
    auto = fetch_autorace()

    print(f"競輪検出: {keirin}")
    print(f"地方競馬検出: {keiba}")
    print(f"オートレース検出: {auto}")

    all_data = {**keirin, **keiba, **auto}
    all_maps = {**KEIRIN_MAP, **KEIBA_MAP, **AUTO_MAP}

    for v_name, tvg_id in all_maps.items():
        channel = ET.SubElement(tv, "channel", id=tvg_id)
        ET.SubElement(channel, "display-name").text = v_name

        status = all_data.get(v_name, "本日非開催")
        prog = ET.SubElement(tv, "programme", start=f"{today}000000 +0900", stop=f"{today}235959 +0900", channel=tvg_id)
        ET.SubElement(prog, "title", lang="ja").text = status
        ET.SubElement(prog, "desc", lang="ja").text = f"{today_display} {v_name} ステータス: {status}"

    tree = ET.ElementTree(tv)
    if hasattr(ET, "indent"): ET.indent(tree, space="  ")
    tree.write("epg.xml", encoding="utf-8", xml_declaration=True)
    print("epg.xml の生成が完了しました。")

if __name__ == "__main__":
    build_epg_xml()
