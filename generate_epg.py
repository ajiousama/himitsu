import datetime
import xml.etree.ElementTree as ET

KEIRIN_MAP = {
    "函館": "keirin.hakodate", "青森": "keirin.aomori", "いわき平": "keirin.iwakitaira",
    "弥彦": "keirin.yahiko", "前橋": "keirin.matsusaka", "取手": "keirin.toride",
    "宇都宮": "keirin.utsunomiya", "大宮": "keirin.omiya", "西武園": "keirin.seibuen",
    "京王閣": "keirin.keiogatsu", "立川": "keirin.tachikawa", "松戸": "keirin.matsudo",
    "川崎": "keirin.kawasaki", "平塚": "keirin.hiratsuka", "小田原": "keirin.odawara",
    "伊東": "keirin.ito", "静岡": "keirin.shizuoka", "名古屋": "keirin.nagoya",
    "岐阜": "keirin.gifu", "大垣": "keirin.ogaki", "豊橋": "keirin.toyohashi",
    "松阪": "keirin.matsusaka", "四日市": "keirin.yokkaichi", "富山": "keirin.toyama",
    "福井": "keirin.fukui", "奈良": "keirin.nara", "岸和田": "keirin.kishiwada",
    "和歌山": "keirin.wakayama", "玉野": "keirin.tamano", "広島": "keirin.hiroshima",
    "防府": "keirin.hofu", "小松島": "keirin.komatsushima", "松山": "keirin.matsuyama",
    "高知": "keirin.kochi", "高松": "keirin.takamatsu", "向日町": "keirin.mukomachi",
    "小倉": "keirin.kokura", "久留米": "keirin.kurume", "武雄": "keirin.takeo", 
    "佐世保": "keirin.sasebo", "別府": "keirin.beppu", "熊本": "keirin.kumamoto", 
    "千葉PIST6": "keirin.pist6"
}

KEIBA_MAP = {
    "帯広": "chihou.obihiro", "門別": "chihou.mombetsu", "盛岡": "chihou.morioka",
    "浦和": "chihou.urawa", "大井": "chihou.oi", "金沢": "chihou.kanazawa",
    "笠松": "chihou.kasamatsu", "園田": "chihou.sonoda", "佐賀": "chihou.saga",
    "札幌": "jra.sapporo", "新潟": "jra.niigata", "中京": "jra.chukyo"
}

AUTO_MAP = {
    "伊勢崎": "auto.isesaki", "飯塚": "auto.iizuka"
}

SCHEDULES = {
    "20260810": {
        "keirin": {
            "前橋": {"desc": "FII モーニング🌅 2日目", "start": "08:30", "end": "11:55"},
            "立川": {"desc": "FI デイ☀ 最終日", "start": "10:40", "end": "16:35"},
            "平塚": {"desc": "FII ナイター🌙 2日目", "start": "15:00", "end": "20:25"},
            "川崎": {"desc": "FII ナイター🌙 2日目", "start": "15:00", "end": "20:25"},
            "四日市": {"desc": "FII ナイター🌙 2日目", "start": "15:00", "end": "20:25"},
            "富山": {"desc": "FII ミッドナイト⭐ 初日", "start": "20:40", "end": "23:40"}
        },
        "keiba": {
            "盛岡": {"desc": "薄暮🌇", "start": "11:40", "end": "18:10"},
            "浦和": {"desc": "薄暮🌇", "start": "13:30", "end": "19:30"},
            "帯広": {"desc": "ナイター🌙", "start": "14:20", "end": "20:40"},
            "金沢": {"desc": "ナイター🌙", "start": "16:35", "end": "20:50"}
        },
        "auto": {"飯塚": {"desc": "ミッドナイト⭐ 3日目", "start": "20:19", "end": "23:45"}}
    },
    "20260811": {
        "keirin": {
            "熊本": {"desc": "FI デイ☀ 初日", "start": "10:30", "end": "16:30"},
            "弥彦": {"desc": "FI デイ☀ 初日", "start": "10:30", "end": "16:30"},
            "前橋": {"desc": "FII モーニング🌅 最終日", "start": "08:30", "end": "11:55"},
            "平塚": {"desc": "FII ナイター🌙 💛 最終日", "start": "15:00", "end": "20:25"},
            "川崎": {"desc": "FII ナイター🌙 💛 最終日", "start": "15:00", "end": "20:25"},
            "四日市": {"desc": "FII ナイター🌙 💛 最終日", "start": "15:00", "end": "20:25"},
            "松山": {"desc": "GI オールスター競輪ナイター🌙 💛 初日", "start": "15:15", "end": "20:50"},
            "富山": {"desc": "FII ミッドナイト⭐ 💛 2日目", "start": "20:40", "end": "23:40"}
        },
        "keiba": {
            "盛岡": {"desc": "クラスターカップ JpnⅢ (17:05発走) デイ☀", "start": "11:40", "end": "18:10"},
            "浦和": {"desc": "ルーキーズサマーカップ (18:55発走) 薄暮🌇", "start": "13:30", "end": "19:30"},
            "金沢": {"desc": "読売レディス杯 (20:00発走) ナイター🌙", "start": "15:05", "end": "20:50"},
            "帯広": {"desc": "ナイター🌙", "start": "14:20", "end": "20:40"}
        },
        "auto": {"伊勢崎": {"desc": "SG オートレースグランプリ 初日🌙", "start": "18:00", "end": "21:30"}}
    },
    "20260812": {
        "keirin": {
            "青森": {"desc": "FII ミッドナイト⭐ 💛 初日", "start": "20:40", "end": "23:40"},
            "弥彦": {"desc": "FI デイ☀ 2日目", "start": "10:30", "end": "16:30"},
            "岐阜": {"desc": "FII モーニング🌅 初日", "start": "08:50", "end": "11:55"},
            "富山": {"desc": "FII ミッドナイト⭐ 💛 最終日", "start": "20:40", "end": "23:40"},
            "松山": {"desc": "GI オールスター競輪ナイター🌙 💛 2日目", "start": "15:15", "end": "20:50"},
            "武雄": {"desc": "FII ミッドナイト⭐ 💛 初日", "start": "20:40", "end": "23:40"},
            "熊本": {"desc": "FI デイ☀ 2日目", "start": "10:30", "end": "16:30"}
        },
        "keiba": {
            "笠松": {"desc": "くろゆり賞 (16:35発走) デイ☀", "start": "11:15", "end": "17:00"},
            "浦和": {"desc": "薄暮🌇", "start": "13:30", "end": "19:30"},
            "金沢": {"desc": "ナイター🌙", "start": "15:05", "end": "20:50"},
            "帯広": {"desc": "ナイター🌙", "start": "14:20", "end": "20:40"}
        },
        "auto": {"伊勢崎": {"desc": "SG オートレースグランプリ 2日目🌙", "start": "18:00", "end": "21:30"}}
    },
    "20260813": {
        "keirin": {
            "青森": {"desc": "FII ミッドナイト⭐ 💛 最終日", "start": "20:40", "end": "23:40"},
            "弥彦": {"desc": "FI デイ☀ 最終日", "start": "10:30", "end": "16:30"},
            "岐阜": {"desc": "FII モーニング🌅 2日目", "start": "08:50", "end": "11:55"},
            "松山": {"desc": "GI オールスター競輪ナイター🌙 💛 3日目", "start": "15:15", "end": "20:50"},
            "武雄": {"desc": "FII ミッドナイト⭐ 💛 2日目", "start": "20:40", "end": "23:40"},
            "熊本": {"desc": "FI デイ☀ 最終日", "start": "10:30", "end": "16:30"}
        },
        "keiba": {
            "門別": {"desc": "北海道スプリントカップ JpnⅢ (19:55発走) ナイター🌙", "start": "14:00", "end": "20:40"},
            "大井": {"desc": "ナイター🌙", "start": "14:25", "end": "20:50"},
            "笠松": {"desc": "デイ☀", "start": "11:15", "end": "16:30"},
            "園田": {"desc": "薄暮🌇", "start": "13:30", "end": "19:30"}
        },
        "auto": {
            "伊勢崎": {"desc": "SG オートレースグランプリ 3日目🌙", "start": "18:00", "end": "21:30"},
            "飯塚": {"desc": "ミッドナイト⭐ 初日", "start": "20:20", "end": "23:45"}
        }
    },
    "20260814": {
        "keirin": {
            "青森": {"desc": "FII ミッドナイト⭐ 💛 最終日", "start": "20:40", "end": "23:40"},
            "西武園": {"desc": "FII モーニング🌅 💛 2日目", "start": "08:30", "end": "11:55"},
            "京王閣": {"desc": "FI デイ☀ 初日", "start": "10:30", "end": "16:30"},
            "岐阜": {"desc": "FII モーニング🌅 最終日", "start": "08:50", "end": "11:55"},
            "奈良": {"desc": "FI デイ☀ 初日", "start": "10:30", "end": "16:30"},
            "松山": {"desc": "GI オールスター競輪ナイター🌙 💛 4日目", "start": "15:15", "end": "20:50"},
            "武雄": {"desc": "FII ミッドナイト⭐ 💛 最終日", "start": "20:40", "end": "23:40"}
        },
        "keiba": {
            "園田": {"desc": "その金ナイター🌇 (摂津盃 19:55発走)", "start": "15:00", "end": "20:30"},
            "門別": {"desc": "ナイター🌙", "start": "14:00", "end": "20:40"},
            "大井": {"desc": "ナイター🌙", "start": "14:25", "end": "20:50"},
            "笠松": {"desc": "デイ☀", "start": "11:15", "end": "16:30"}
        },
        "auto": {"伊勢崎": {"desc": "SG オートレースグランプリ 4日目🌙", "start": "18:00", "end": "21:30"}}
    },
    "20260815": {
        "keirin": {
            "前橋": {"desc": "FII ミッドナイト⭐ 💛 初日", "start": "20:40", "end": "23:40"},
            "西武園": {"desc": "FII モーニング🌅 💛 最終日", "start": "08:30", "end": "11:55"},
            "京王閣": {"desc": "FI デイ☀ 2日目", "start": "10:30", "end": "16:30"},
            "静岡": {"desc": "FII ミッドナイト⭐ 💛 初日", "start": "20:40", "end": "23:40"},
            "奈良": {"desc": "FI デイ☀ 2日目", "start": "10:30", "end": "16:30"},
            "松山": {"desc": "GI オールスター競輪ナイター🌙 💛 5日目", "start": "15:15", "end": "20:50"}
        },
        "keiba": {
            "新潟": {"desc": "新潟ジャンプS (15:45発走) デイ☀", "start": "09:40", "end": "18:15"},
            "中京": {"desc": "デイ☀", "start": "09:40", "end": "18:15"},
            "札幌": {"desc": "デイ☀", "start": "09:40", "end": "18:15"},
            "帯広": {"desc": "ナイター🌙", "start": "14:20", "end": "20:40"},
            "大井": {"desc": "ナイター🌙", "start": "14:25", "end": "20:50"},
            "佐賀": {"desc": "ナイター🌙", "start": "15:55", "end": "20:50"}
        },
        "auto": {"伊勢崎": {"desc": "SG オートレースグランプリ 最終日🌙", "start": "18:00", "end": "21:30"}}
    },
    "20260816": {
        "keirin": {
            "前橋": {"desc": "FII ミッドナイト⭐ 💛 2日目", "start": "20:40", "end": "23:40"},
            "西武園": {"desc": "FII モーニング🌅 💛 初日", "start": "08:30", "end": "11:55"},
            "京王閣": {"desc": "FI デイ☀ 最終日", "start": "10:30", "end": "16:30"},
            "静岡": {"desc": "FII ミッドナイト⭐ 💛 2日目", "start": "20:40", "end": "23:40"},
            "奈良": {"desc": "FI デイ☀ 最終日", "start": "10:30", "end": "16:30"},
            "松山": {"desc": "GI オールスター競輪ナイター🌙 💛 決勝戦", "start": "15:15", "end": "20:50"}
        },
        "keiba": {
            "札幌": {"desc": "札幌記念 (GⅡ 15:45発走) デイ☀", "start": "09:40", "end": "18:15"},
            "新潟": {"desc": "デイ☀", "start": "09:40", "end": "18:15"},
            "中京": {"desc": "デイ☀", "start": "09:40", "end": "18:15"},
            "帯広": {"desc": "ナイター🌙", "start": "14:20", "end": "20:40"},
            "大井": {"desc": "ナイター🌙", "start": "14:25", "end": "20:50"},
            "佐賀": {"desc": "ナイター🌙", "start": "15:55", "end": "20:50"}
        },
        "auto": {"飯塚": {"desc": "ミッドナイト⭐ 2日目", "start": "20:20", "end": "23:45"}}
    }
}

def format_time_xml(dt):
    return dt.strftime("%Y%m%d%H%M%S +0900")

def build_epg_xml():
    tv = ET.Element("tv", {"generator-info-name": "CombinedEPGGenerator"})
    JST = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(JST)
    
    today_str = now.strftime("%Y%m%d")
    dt_obj = datetime.datetime.strptime(today_str, "%Y%m%d")
    today_display = dt_obj.strftime("%Y年%m月%d日")
    day_schedules = SCHEDULES.get(today_str, {})

    for target_map, category in [(KEIRIN_MAP, "keirin"), (KEIBA_MAP, "keiba"), (AUTO_MAP, "auto")]:
        cat_data = day_schedules.get(category, {})
        for v_name, tvg_id in target_map.items():
            channel = ET.SubElement(tv, "channel", id=tvg_id)
            ET.SubElement(channel, "display-name").text = v_name

            day_start = datetime.datetime.strptime(f"{today_str} 01:00", "%Y%m%d %H:%M").replace(tzinfo=JST)
            day_end = datetime.datetime.strptime(f"{today_str} 23:59", "%Y%m%d %H:%M").replace(tzinfo=JST)

            if v_name in cat_data:
                info = cat_data[v_name]
                start_dt = datetime.datetime.strptime(f"{today_str} {info['start']}", "%Y%m%d %H:%M").replace(tzinfo=JST)
                end_dt = datetime.datetime.strptime(f"{today_str} {info['end']}", "%Y%m%d %H:%M").replace(tzinfo=JST)
                
                pre_start = start_dt - datetime.timedelta(minutes=30)
                post_end = end_dt + datetime.timedelta(minutes=30)

                # 1. 01:00 ～ 第①レース開始30分前
                if day_start < pre_start:
                    prog1 = ET.SubElement(tv, "programme", start=format_time_xml(day_start), stop=format_time_xml(pre_start), channel=tvg_id)
                    t1 = f"♦本日開催 実況中継前 第①レース{info['start']} 開始♦"
                    ET.SubElement(prog1, "title", lang="ja").text = t1
                    ET.SubElement(prog1, "desc", lang="ja").text = f"{today_display} {v_name} ステータス: {t1}"

                # 2. 第①レース30分前 ～ 最終レース30分後
                prog2 = ET.SubElement(tv, "programme", start=format_time_xml(pre_start), stop=format_time_xml(post_end), channel=tvg_id)
                t2 = f"♦{v_name} {info['desc']} 実況放送♦"
                ET.SubElement(prog2, "title", lang="ja").text = t2
                ET.SubElement(prog2, "desc", lang="ja").text = f"{today_display} {v_name} ステータス: {t2}"

                # 3. 最終レース30分後 ～ 翌01:00
                if post_end < day_end:
                    prog3 = ET.SubElement(tv, "programme", start=format_time_xml(post_end), stop=format_time_xml(day_end), channel=tvg_id)
                    t3 = "♦本日 全レース終了♦"
                    ET.SubElement(prog3, "title", lang="ja").text = t3
                    ET.SubElement(prog3, "desc", lang="ja").text = f"{today_display} {v_name} ステータス: {t3}"
            else:
                # 開催なし
                prog = ET.SubElement(tv, "programme", start=format_time_xml(day_start), stop=format_time_xml(day_end), channel=tvg_id)
                t_none = "💎本日は開催しておりません💎"
                ET.SubElement(prog, "title", lang="ja").text = t_none
                ET.SubElement(prog, "desc", lang="ja").text = f"{today_display} {v_name} ステータス: {t_none}"

    tree = ET.ElementTree(tv)
    if hasattr(ET, "indent"): ET.indent(tree, space="    ")
    tree.write("epg.xml", encoding="utf-8", xml_declaration=True)

if __name__ == "__main__":
    build_epg_xml()
