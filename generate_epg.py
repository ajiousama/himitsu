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

SCHEDULES = {
    "20260809": {
        "keirin": {
            "前橋": "F2 ナイター🌙 初日（1R 15:48発走）",
            "立川": "FI デイ☀ 2日目（1R 10:30発走）",
            "川崎": "F2 ミッドナイト⭐ 初日（1R 20:35発走）",
            "平塚": "F2 モーニング🌅 初日（1R 8:30発走）",
            "岐阜": "F2 モーニング🌅 最終日（1R 8:35発走）",
            "四日市": "F2 ミッドナイト⭐ 初日（1R 20:50発走）",
            "和歌山": "G3 デイ☀ 💛最終日（1R 10:40発走）",
            "佐世保": "G1 オールガールズクラシックナイター🌙 💛最終日（1R 15:35発走）"
        },
        "keiba": {
            "新潟": "新潟11R レパードステークス（GⅢ） デイ☀（1R 9:40発走）",
            "中京": "中京11R CBC賞（GⅢ） デイ☀（1R 9:50発走）",
            "札幌": "デイ☀（1R 10:00発走）",
            "帯広": "ナイター🌙（1R 14:25発走）",
            "盛岡": "ナイター🌙（1R 13:30発走、メイン11R ひまわり賞 19:15発走）",
            "金沢": "ナイター🌙（1R 16:35発走）",
            "佐賀": "ナイター🌙（1R 15:55発走）"
        },
        "auto": {
            "川口": "デイ☀ 最終日（1R 10:56発走）",
            "飯塚": "ミッドナイト⭐ 2日目（1R 20:19発走）"
        }
    },
    "20260810": {
        "keirin": {
            "前橋": "F2 モーニング🌅 2日目（1R 8:30発走）",
            "立川": "FI デイ☀ 最終日（1R 10:57発走）",
            "平塚": "F2 ナイター🌙 💛 2日目（1R 15:00発走）",
            "川崎": "F2 ナイター🌙 💛 2日目（1R 20:40発走）",
            "四日市": "F2 ナイター🌙 💛 2日目（1R 20:50発走）",
            "富山": "F2 ミッドナイト⭐ 💛 初日（1R 20:40発走）"
        },
        "keiba": {
            "盛岡": "デイ☀（1R 11:40発走）",
            "浦和": "薄暮🌇（1R 13:30発走）",
            "帯広": "ナイター🌙（1R 14:20発走）",
            "金沢": "ナイター🌙（1R 16:35発走）"
        },
        "auto": {
            "飯塚": "ミッドナイト⭐ 3日目（1R 20:20発走）"
        }
    },
    "20260811": {
        "keirin": {
            "弥彦": "FI デイ☀ 初日（1R 10:30発走）",
            "前橋": "F2 モーニング🌅 最終日（1R 8:30発走）",
            "川崎": "F2 ナイター🌙 💛 最終日（1R 20:40発走）",
            "平塚": "F2 ナイター🌙 💛 最終日（1R 15:00発走）",
            "富山": "F2 ミッドナイト⭐ 💛 2日目（1R 20:40発走）",
            "四日市": "F2 ナイター🌙 💛 最終日（1R 20:50発走）",
            "松山": "G1 オールスター競輪ナイター🌙 💛 初日（1R 15:15発走）",
            "熊本": "FI デイ☀ 初日（1R 10:30発走）"
        },
        "keiba": {
            "盛岡": "クラスターカップ JpnⅢ デイ☀（1R 11:40発走）",
            "浦和": "薄暮🌇（1R 13:30発走）",
            "金沢": "ナイター🌙（1R 15:05発走）",
            "帯広": "ナイター🌙（1R 14:20発走）"
        },
        "auto": {
            "伊勢崎": "SG オートレースグランプリ 初日🌙（1R 18:00発走）"
        }
    },
    "20260812": {
        "keirin": {
            "青森": "F2 ミッドナイト⭐ 💛 初日（1R 20:40発走）",
            "弥彦": "FI デイ☀ 2日目（1R 10:30発走）",
            "岐阜": "F2 モーニング🌅 初日（1R 8:50発走）",
            "富山": "F2 ミッドナイト⭐ 💛 最終日（1R 20:40発走）",
            "松山": "G1 オールスター競輪ナイター🌙 💛 2日目（1R 15:15発走）",
            "武雄": "F2 ミッドナイト⭐ 💛 初日（1R 20:40発走）",
            "熊本": "FI デイ☀ 2日目（1R 10:30発走）"
        },
        "keiba": {
            "盛岡": "デイ☀（1R 11:40発走）",
            "浦和": "薄暮🌇（1R 13:30発走）",
            "園田": "デイ☀（1R 10:30発走）",
            "金沢": "ナイター🌙（1R 15:05発走）",
            "帯広": "ナイター🌙（1R 14:20発走）"
        },
        "auto": {
            "伊勢崎": "SG オートレースグランプリ 2日目🌙（1R 18:00発走）"
        }
    },
    "20260813": {
        "keirin": {
            "青森": "F2 ミッドナイト⭐ 💛 最終日（1R 20:40発走）",
            "弥彦": "FI デイ☀ 最終日（1R 10:30発走）",
            "岐阜": "F2 モーニング🌅 2日目（1R 8:50発走）",
            "松山": "G1 オールスター競輪ナイター🌙 💛 3日目（1R 15:15発走）",
            "武雄": "F2 ミッドナイト⭐ 💛 2日目（1R 20:40発走）",
            "熊本": "FI デイ☀ 最終日（1R 10:30発走）"
        },
        "keiba": {
            "門別": "北海道スプリントカップ JpnⅢ ナイター🌙（1R 14:00発走）",
            "大井": "ナイター🌙（1R 14:25発走）",
            "笠松": "デイ☀（1R 11:15発走）",
            "園田": "薄暮🌇（1R 13:30発走）"
        },
        "auto": {
            "伊勢崎": "SG オートレースグランプリ 3日目🌙（1R 18:00発走）",
            "飯塚": "ミッドナイト⭐ 初日（1R 20:20発走）"
        }
    },
    "20260814": {
        "keirin": {
            "青森": "F2 ミッドナイト⭐ 💛 最終日（1R 20:40発走）",
            "西武園": "F2 モーニング🌅 💛 2日目（1R 8:30発走）",
            "京王閣": "FI デイ☀ 初日（1R 10:30発走）",
            "岐阜": "F2 モーニング🌅 最終日（1R 8:50発走）",
            "奈良": "FI デイ☀ 初日（1R 10:30発走）",
            "松山": "G1 オールスター競輪ナイター🌙 💛 4日目（1R 15:15発走）",
            "武雄": "F2 ミッドナイト⭐ 💛 最終日（1R 20:40発走）"
        },
        "keiba": {
            "門別": "ナイター🌙（1R 14:00発走）",
            "大井": "ナイター🌙（1R 14:25発走）",
            "笠松": "デイ☀（1R 11:15発走）",
            "園田": "デイ☀（1R 10:30発走）"
        },
        "auto": {
            "伊勢崎": "SG オートレースグランプリ 4日目🌙（1R 18:00発走）"
        }
    },
    "20260815": {
        "keirin": {
            "前橋": "F2 ミッドナイト⭐ 💛 初日（1R 20:40発走）",
            "西武園": "F2 モーニング🌅 💛 最終日（1R 8:30発走）",
            "京王閣": "FI デイ☀ 2日目（1R 10:30発走）",
            "静岡": "F2 ミッドナイト⭐ 💛 初日（1R 20:40発走）",
            "奈良": "FI デイ☀ 2日目（1R 10:30発走）",
            "松山": "G1 オールスター競輪ナイター🌙 💛 5日目（1R 15:15発走）"
        },
        "keiba": {
            "新潟": "新潟ジャンプS (J・GⅢ) デイ☀（1R 9:40発走）",
            "中京": "デイ☀（1R 9:50発走）",
            "札幌": "デイ☀（1R 10:00発走）",
            "帯広": "ナイター🌙（1R 14:20発走）",
            "大井": "ナイター🌙（1R 14:25発走）",
            "佐賀": "ナイター🌙（1R 15:55発走）"
        },
        "auto": {
            "伊勢崎": "SG オートレースグランプリ 5日目🌙（1R 18:00発走）"
        }
    },
    "20260816": {
        "keirin": {
            "前橋": "F2 ミッドナイト⭐ 💛 2日目（1R 20:40発走）",
            "京王閣": "FI デイ☀ 最終日（1R 10:30発走）",
            "伊東温泉": "F2 モーニング🌅 初日（1R 8:30発走）",
            "静岡": "F2 ミッドナイト⭐ 💛 2日目（1R 20:40発走）",
            "奈良": "FI デイ☀ 最終日（1R 10:30発走）",
            "松山": "G1 オールスター競輪ナイター🌙 💛 最終日（1R 15:15発走）",
            "別府": "F2 ミッドナイト⭐ 💛 初日（1R 20:40発走）"
        },
        "keiba": {
            "新潟": "デイ☀（1R 9:40発走）",
            "中京": "中京記念 GⅢ デイ☀（1R 9:50発走）",
            "札幌": "札幌記念 GⅡ デイ☀（1R 10:00発走）",
            "帯広": "ナイター🌙（1R 14:20発走）",
            "大井": "ナイター🌙（1R 14:25発走）",
            "佐賀": "ナイター🌙（1R 15:55発走）"
        },
        "auto": {
            "伊勢崎": "SG オートレースグランプリ 最終日🌙（1R 18:00発走）"
        }
    }
}

def build_epg_xml():
    tv = ET.Element("tv", {"generator-info-name": "CombinedEPGGenerator"})
    JST = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(JST)
    
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