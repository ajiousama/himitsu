import datetime
import xml.etree.ElementTree as ET

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
    "熊本": "keirin.kumamoto", "千葉PIST6": "keirin.pist6", "伊東温泉": "keirin.ito"
}

KEIBA_MAP = {
    "帯広": "chihou.obihiro", "門別": "chihou.mombetsu", "盛岡": "chihou.morioka",
    "水沢": "chihou.mizusawa", "浦和": "chihou.urawa", "船橋": "chihou.funabashi",
    "大井": "chihou.oi", "川崎": "chihou.kawasaki_keiba", "金沢": "chihou.kanazawa",
    "名古屋": "chihou.nagoya_keiba", "笠松": "chihou.kasamatsu", "園田": "chihou.sonoda",
    "姫路": "chihou.himeji", "高知": "chihou.kochi_keiba", "佐賀": "chihou.saga",
    "ＪＲＡ公式": "jra.official", "ＪＲＡグリーン": "jra.green"
}

AUTO_MAP = {
    "川口": "auto.kawaguchi", "伊勢崎": "auto.isesaki", "浜松": "auto.hamamatsu",
    "飯塚": "auto.iizuka", "山陽": "auto.sanyo"
}

# 8/8を削除し、8/9以降のみを保持
SCHEDULES = {
    "20260809": {
        "keirin": {"岐阜": "モーニング🌅 最終日", "平塚": "モーニング🌅 初日", "和歌山": "G3 デイ☀ 💛 決勝", "立川": "FI デイ☀ 2日目", "佐世保": "G1 女子オールスター ナイター🌙 💛 決勝", "前橋": "モーニング🌅 初日", "川崎": "ミッドナイト⭐ 💛 初日", "四日市": "ミッドナイト⭐ 💛 初日"},
        "keiba": {"新潟": "レパードS GⅢ デイ☀", "中京": "CBC賞 GⅢ デイ☀", "札幌": "デイ☀", "盛岡": "薄暮🌇", "帯広": "ナイター🌙", "佐賀": "ナイター🌙", "金沢": "ナイター🌙"},
        "auto": {"川口": "デイ☀ 最終日"}
    },
    "20260810": {
        "keirin": {"前橋": "モーニング🌅 2日目", "立川": "FI デイ☀ 最終日", "平塚": "ナイター🌙 💛 2日目", "川崎": "ナイター🌙 💛 2日目", "四日市": "ナイター🌙 💛 2日目", "富山": "ミッドナイト⭐ 💛 初日"},
        "keiba": {"盛岡": "デイ☀", "浦和": "薄暮🌇", "帯広": "ナイター🌙", "金沢": "ナイター🌙"},
        "auto": {"飯塚": "ミッドナイト⭐ 3日目"}
    },
    "20260811": {
        "keirin": {"弥彦": "FI デイ☀ 初日", "前橋": "モーニング🌅 最終日", "川崎": "ナイター🌙 💛 最終日", "平塚": "ナイター🌙 💛 最終日", "富山": "ミッドナイト⭐ 💛 2日目", "四日市": "ナイター🌙 💛 最終日", "松山": "G1 オールスター競輪ナイター🌙 💛 初日", "熊本": "FI デイ☀ 初日"},
        "keiba": {"盛岡": "クラスターカップ JpnⅢ デイ☀", "浦和": "薄暮🌇", "金沢": "ナイター🌙", "帯広": "ナイター🌙"},
        "auto": {"伊勢崎": "SG オートレースグランプリ 初日🌙"}
    },
    "20260812": {
        "keirin": {"青森": "F2 ミッドナイト⭐ 💛 初日", "弥彦": "FI デイ☀ 2日目", "岐阜": "F2 モーニング🌅 初日", "富山": "F2 ミッドナイト⭐ 💛 最終日", "松山": "G1 オールスター競輪ナイター🌙 💛 2日目", "武雄": "F2 ミッドナイト⭐ 💛 初日", "熊本": "FI デイ☀ 2日目"},
        "keiba": {"盛岡": "デイ☀", "浦和": "薄暮🌇", "園田": "デイ☀", "金沢": "ナイター🌙", "帯広": "ナイター🌙"},
        "auto": {"伊勢崎": "SG オートレースグランプリ 2日目🌙"}
    },
    "20260813": {
        "keirin": {"青森": "F2 ミッドナイト⭐ 💛 最終日", "弥彦": "FI デイ☀ 最終日", "岐阜": "F2 モーニング🌅 2日目", "松山": "G1 オールスター競輪ナイター🌙 💛 3日目", "武雄": "F2 ミッドナイト⭐ 💛 2日目", "熊本": "FI デイ☀ 最終日"},
        "keiba": {"門別": "北海道スプリントカップ JpnⅢ ナイター🌙", "大井": "ナイター🌙", "笠松": "デイ☀", "園田": "薄暮🌇"},
        "auto": {"伊勢崎": "SG オートレースグランプリ 3日目🌙", "飯塚": "ミッドナイト⭐ 初日"}
    },
    "20260814": {
        "keirin": {"青森": "F2 ミッドナイト⭐ 💛 最終日", "西武園": "F2 モーニング🌅 💛 2日目", "京王閣": "FI デイ☀ 初日", "岐阜": "F2 モーニング🌅 最終日", "奈良": "FI デイ☀ 初日", "松山": "G1 オールスター競輪ナイター🌙 💛 4日目", "武雄": "F2 ミッドナイト⭐ 💛 最終日"},
        "keiba": {"門別": "ナイター🌙", "大井": "ナイター🌙", "笠松": "デイ☀", "園田": "デイ☀"},
        "auto": {"伊勢崎": "SG オートレースグランプリ 4日目🌙"}
    },
    "20260815": {
        "keirin": {"前橋": "F2 ミッドナイト⭐ 💛 初日", "西武園": "F2 モーニング🌅 💛 最終日", "京王閣": "FI デイ☀ 2日目", "静岡": "F2 ミッドナイト⭐ 💛 初日", "奈良": "FI デイ☀ 2日目", "松山": "G1 オールスター競輪ナイター🌙 💛 5日目"},
        "keiba": {"新潟": "新潟ジャンプS (J・GⅢ) デイ☀", "中京": "デイ☀", "札幌": "デイ☀", "帯広": "ナイター🌙", "大井": "ナイター🌙", "佐賀": "ナイター🌙"},
        "auto": {"伊勢崎": "SG オートレースグランプリ 5日目🌙"}
    },
    "20260816": {
        "keirin": {"前橋": "F2 ミッドナイト⭐ 💛 2日目", "京王閣": "FI デイ☀ 最終日", "伊東温泉": "F2 モーニング🌅 初日", "静岡": "F2 ミッドナイト⭐ 💛 2日目", "奈良": "FI デイ☀ 最終日", "松山": "G1 オールスター競輪ナイター🌙 💛 最終日", "別府": "F2 ミッドナイト⭐ 💛 初日"},
        "keiba": {"新潟": "デイ☀", "中京": "中京記念 GⅢ デイ☀", "札幌": "札幌記念 GⅡ デイ☀", "帯広": "ナイター🌙", "大井": "ナイター🌙", "佐賀": "ナイター🌙"},
        "auto": {"伊勢崎": "SG オートレースグランプリ 最終日🌙"}
    }
}

def build_epg_xml():
    tv = ET.Element("tv", {"generator-info-name": "CombinedEPGGenerator"})
    JST = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(JST)
    
    # 深夜1時を過ぎたら翌日分を処理
    today_str = (now - datetime.timedelta(days=1) if now.hour < 1 else now).strftime("%Y%m%d")

    dt_obj = datetime.datetime.strptime(today_str, "%Y%m%d")
    today_display = dt_obj.strftime("%Y年%m月%d日")
    day_schedules = SCHEDULES.get(today_str, {})
    current_hour = now.hour

    for target_map, category in [(KEIRIN_MAP, "keirin"), (KEIBA_MAP, "keiba"), (AUTO_MAP, "auto")]:
        cat_data = day_schedules.get(category, {})
        for v_name, tvg_id in target_map.items():
            channel = ET.SubElement(tv, "channel", id=tvg_id)
            ET.SubElement(channel, "display-name").text = v_name

            # 開催判定
            if v_name in ["ＪＲＡ公式", "ＪＲＡグリーン"]:
                jra_items = [f"{j}{s}" for j, s in cat_data.items() if j in ["新潟", "中京", "札幌"]]
                if jra_items and (current_hour < 21):
                    title_text = f"【本日開催】 " + " ".join(jra_items)
                elif jra_items and (current_hour >= 21):
                    title_text = "💎本日は終了しました💎"
                else:
                    title_text = "💎本日は開催しておりません💎"
            else:
                if v_name in cat_data:
                    status_val = cat_data[v_name]
                    if current_hour >= 21 and "ミッドナイト" not in status_val:
                        title_text = "💎本日は終了しました💎"
                    else:
                        title_text = f"【本日開催】 ({status_val})"
                else:
                    title_text = "💎本日は開催しておりません💎"

            prog = ET.SubElement(tv, "programme", start=f"{today_str}000000 +0900", stop=f"{today_str}235959 +0900", channel=tvg_id)
            ET.SubElement(prog, "title", lang="ja").text = title_text
            ET.SubElement(prog, "desc", lang="ja").text = f"{today_display} {v_name} ステータス: {title_text}"

    tree = ET.ElementTree(tv)
    if hasattr(ET, "indent"): ET.indent(tree, space="  ")
    tree.write("epg.xml", encoding="utf-8", xml_declaration=True)
    print(f"{today_display} EPG生成完了")

if __name__ == "__main__":
    build_epg_xml()