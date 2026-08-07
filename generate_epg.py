import datetime
import xml.etree.ElementTree as ET

# 各マップは変更せずそのまま使用
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
    "帯広": "chihou.obihiro", "門別": "chihou.mombetsu", "盛岡": "chihou.morioka",
    "水沢": "chihou.mizusawa", "浦和": "chihou.urawa", "船橋": "chihou.funabashi",
    "大井": "chihou.oi", "川崎": "chihou.kawasaki_keiba", "金沢": "chihou.kanazawa",
    "名古屋": "chihou.nagoya_keiba", "笠松": "chihou.kasamatsu", "園田": "chihou.sonoda",
    "姫路": "chihou.himeji", "高知": "chihou.kochi_keiba", "佐賀": "chihou.saga",
    "新潟": "jra.niigata", "中京": "jra.chukyo", "札幌": "jra.sapporo",
    "ＪＲＡ公式": "jra.official", "ＪＲＡグリーン": "jra.green"
}

AUTO_MAP = {
    "川口": "auto.kawaguchi", "伊勢崎": "auto.isesaki", "浜松": "auto.hamamatsu",
    "飯塚": "auto.iizuka", "山陽": "auto.sanyo"
}

def get_offline_status(v_name, category):
    today_str = datetime.datetime.now().strftime("%Y%m%d")
    
    # 本日（8/7）の開催
    if today_str == "20260807":
        if category == "keirin":
            if v_name in ["いわき平", "佐世保"]: return "【本日開催】 (ナイター🌙)"
            if v_name in ["宇都宮", "伊東"]: return "【本日開催】 (ミッドナイト⭐)"
            if v_name in ["和歌山", "豊橋"]: return "【本日開催】 (デイ)"
            if v_name == "岐阜": return "【本日開催】 (モーニング🌅)"
        elif category == "keiba":
            if v_name == "園田": return "【本日開催】 (ナイター🌙)"
            if v_name == "浦和": return "【本日開催】 (デイ)"
        elif category == "auto":
            if v_name == "川口": return "【本日開催】 (デイ)"
            if v_name == "伊勢崎": return "【本日開催】 (ナイター🌙)"
            if v_name == "山陽": return "【本日開催】 (ミッドナイト⭐)"

    # 明日（8/8）の開催
    elif today_str == "20260808":
        if category == "keirin":
            if v_name == "岐阜": return "【本日開催】 (モーニング🌅)"
            if v_name in ["和歌山", "立川"]: return "【本日開催】 (デイ)"
            if v_name in ["佐世保", "いわき平"]: return "【本日開催】 (ナイター🌙)"
            if v_name in ["宇都宮", "伊東"]: return "【本日開催】 (ミッドナイト⭐)"
        elif category == "keiba":
            if v_name in ["新潟", "中京", "札幌"]: return "【本日開催】 (デイ) (中央競馬)"
            if v_name in ["帯広", "佐賀"]: return "【本日開催】 (ナイター🌙)"
        elif category == "auto":
            if v_name == "川口": return "【本日開催】 (デイ)"
            if v_name == "飯塚": return "【本日開催】 (ミッドナイト⭐)"
            
    return None

def build_epg_xml():
    tv = ET.Element("tv", {"generator-info-name": "CombinedEPGGenerator"})
    today = datetime.datetime.now().strftime("%Y%m%d")
    today_display = datetime.datetime.now().strftime("%Y年%m月%d日")

    for target_map, category in [(KEIRIN_MAP, "keirin"), (KEIBA_MAP, "keiba"), (AUTO_MAP, "auto")]:
        for v_name, tvg_id in target_map.items():
            channel = ET.SubElement(tv, "channel", id=tvg_id)
            ET.SubElement(channel, "display-name").text = v_name

            status = get_offline_status(v_name, category)
            title_text = status if status else "本日非開催"
            desc_text = f"{today_display} {v_name} ステータス: {title_text}"

            prog = ET.SubElement(tv, "programme", start=f"{today}000000 +0900", stop=f"{today}235959 +0900", channel=tvg_id)
            ET.SubElement(prog, "title", lang="ja").text = title_text
            ET.SubElement(prog, "desc", lang="ja").text = desc_text

    tree = ET.ElementTree(tv)
    if hasattr(ET, "indent"): ET.indent(tree, space="  ")
    tree.write("epg.xml", encoding="utf-8", xml_declaration=True)
    print("EPG生成完了")

if __name__ == "__main__":
    build_epg_xml()
