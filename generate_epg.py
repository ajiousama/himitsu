import datetime
import xml.etree.ElementTree as ET

KEIRIN_MAP = {
    "函館": "keirin.hakodate", "青森": "keirin.aomori", "いわき平": "keirin.iwakitaira", "弥彦": "keirin.yahiko",
    "前橋": "keirin.maebashi", "取手": "keirin.toride", "宇都宮": "keirin.utsunomiya", "大宮": "keirin.omiya",
    "西武園": "keirin.seibuen", "京王閣": "keirin.keiogatsu", "立川": "keirin.tachikawa", "松戸": "keirin.matsudo",
    "川崎": "keirin.kawasaki", "平塚": "keirin.hiratsuka", "小田原": "keirin.odawara", "伊東": "keirin.ito",
    "静岡": "keirin.shizuoka", "名古屋": "keirin.nagoya", "岐阜": "keirin.gifu", "大垣": "keirin.ogaki",
    "豊橋": "keirin.toyohashi", "松阪": "keirin.matsusaka", "四日市": "keirin.yokkaichi", "富山": "keirin.toyama",
    "福井": "keirin.fukui", "奈良": "keirin.nara", "岸和田": "keirin.kishiwada", "和歌山": "keirin.wakayama",
    "玉野": "keirin.tamano", "広島": "keirin.hiroshima", "防府": "keirin.hofu", "小松島": "keirin.komatsushima",
    "松山": "keirin.matsuyama", "高知": "keirin.kochi", "高松": "keirin.takamatsu", "向日町": "keirin.mukomachi",
    "小倉": "keirin.kokura", "久留米": "keirin.kurume", "武雄": "keirin.takeo", "佐世保": "keirin.sasebo",
    "別府": "keirin.beppu", "熊本": "keirin.kumamoto", "千葉": "keirin.pist6"
}
KEIBA_MAP = {
    "帯広": "chihou.obihiro", "門別": "chihou.mombetsu", "盛岡": "chihou.morioka", "水沢": "chihou.mizusawa",
    "浦和": "chihou.urawa", "船橋": "chihou.funabashi", "大井": "chihou.oi", "川崎": "chihou.kawasaki_keiba",
    "金沢": "chihou.kanazawa", "名古屋": "chihou.nagoya_keiba", "笠松": "chihou.kasamatsu", "園田": "chihou.sonoda",
    "姫路": "chihou.himeji", "高知": "chihou.kochi_keiba", "佐賀": "chihou.saga", "札幌": "jra.sapporo",
    "新潟": "jra.niigata", "中京": "jra.chukyo", "ＪＲＡ公式": "jra.official", "ＪＲＡグリーン": "jra.green"
}
AUTO_MAP = {"川口": "auto.kawaguchi", "伊勢崎": "auto.isesaki", "浜松": "auto.hamamatsu", "飯塚": "auto.iizuka", "山陽": "auto.sanyo"}

SCHEDULES = {
    "20260811": {
        "keirin": {
            "松山": {"desc": "GI オールスター競輪 初日", "start": "15:15", "end": "20:50", "is_girls": True, "day_type": "ナイター"},
            "弥彦": {"desc": "FI KEIRINライジングスターズ 初日", "start": "10:30", "end": "16:30", "is_girls": False, "day_type": "デイ"},
            "熊本": {"desc": "FI KEIRINライジングスターズ 初日", "start": "10:30", "end": "16:30", "is_girls": False, "day_type": "デイ"},
            "富山": {"desc": "FI 仲間と繋がるTIPSTAR杯 2日目", "start": "10:30", "end": "16:30", "is_girls": False, "day_type": "デイ"},
            "前橋": {"desc": "FII ティーネットエンタープライズC 最終日", "start": "15:00", "end": "20:25", "is_girls": False, "day_type": "ナイター"},
            "川崎": {"desc": "FII チャリロト杯 最終日", "start": "20:40", "end": "23:40", "is_girls": True, "day_type": "ミッドナイト"},
            "平塚": {"desc": "FII 楽天Kドリームス杯 最終日", "start": "08:30", "end": "11:55", "is_girls": False, "day_type": "モーニング"},
            "四日市": {"desc": "FII 前検日コメならウィンチケット杯 最終日", "start": "20:40", "end": "23:40", "is_girls": False, "day_type": "ミッドナイト"}
        },
        "keiba": {
            "帯広": {"desc": "ナイター", "start": "14:20", "end": "20:40", "day_type": "ナイター"},
            "門別": {"desc": "ナイター", "start": "14:00", "end": "20:40", "day_type": "ナイター"},
            "盛岡": {"desc": "クラスターカップ JpnⅢ", "start": "11:40", "end": "18:10", "day_type": "薄暮"},
            "浦和": {"desc": "ルーキーズサマーC", "start": "13:30", "end": "19:30", "day_type": "薄暮"},
            "金沢": {"desc": "読売レディス杯", "start": "15:05", "end": "20:50", "day_type": "ナイター"},
            "笠松": {"desc": "薄暮", "start": "11:15", "end": "18:00", "day_type": "薄暮"}
        },
        "auto": {"伊勢崎": {"desc": "SG オートレースグランプリ 初日", "start": "18:00", "end": "21:30", "day_type": "ナイター"}}
    },
    "20260812": {
        "keirin": {
            "松山": {"desc": "GI オールスター競輪 2日目", "start": "15:15", "end": "20:50", "is_girls": True, "day_type": "ナイター"},
            "弥彦": {"desc": "FI KEIRINライジングスターズ 2日目", "start": "10:30", "end": "16:30", "is_girls": False, "day_type": "デイ"},
            "熊本": {"desc": "FI KEIRINライジングスターズ 2日目", "start": "10:30", "end": "16:30", "is_girls": False, "day_type": "デイ"},
            "青森": {"desc": "FII AI競輪も大人気チャリロト杯 初日", "start": "20:40", "end": "23:40", "is_girls": False, "day_type": "ミッドナイト"},
            "岐阜": {"desc": "FII 前検日コメならウィンチケット杯 初日", "start": "08:50", "end": "11:55", "is_girls": False, "day_type": "モーニング"},
            "富山": {"desc": "FI 仲間と繋がるTIPSTAR杯 最終日", "start": "10:30", "end": "16:30", "is_girls": False, "day_type": "デイ"},
            "武雄": {"desc": "FII 前検日コメならウィンチケット杯 初日", "start": "20:40", "end": "23:40", "is_girls": True, "day_type": "ミッドナイト"}
        },
        "keiba": {
            "帯広": {"desc": "ナイター", "start": "14:20", "end": "20:40", "day_type": "ナイター"},
            "浦和": {"desc": "薄暮", "start": "13:30", "end": "19:30", "day_type": "薄暮"},
            "大井": {"desc": "ナイター", "start": "14:25", "end": "20:50", "day_type": "ナイター"},
            "笠松": {"desc": "薄暮", "start": "11:15", "end": "18:00", "day_type": "薄暮"},
            "園田": {"desc": "薄暮", "start": "13:30", "end": "19:30", "day_type": "薄暮"},
            "金沢": {"desc": "ナイター", "start": "15:05", "end": "20:50", "day_type": "ナイター"}
        },
        "auto": {"伊勢崎": {"desc": "SG 2日目", "start": "18:00", "end": "21:30", "day_type": "ナイター"}}
    },
    "20260813": {
        "keirin": {
            "松山": {"desc": "GI オールスター競輪 3日目", "start": "15:15", "end": "20:50", "is_girls": True, "day_type": "ナイター"},
            "弥彦": {"desc": "FI KEIRINライジングスターズ 最終日", "start": "10:30", "end": "16:30", "is_girls": False, "day_type": "デイ"},
            "熊本": {"desc": "FI KEIRINライジングスターズ 最終日", "start": "10:30", "end": "16:30", "is_girls": False, "day_type": "デイ"},
            "青森": {"desc": "FII AI競輪も大人気チャリロト杯 2日目", "start": "20:40", "end": "23:40", "is_girls": False, "day_type": "ミッドナイト"},
            "西武園": {"desc": "FII オッズパーク杯 初日", "start": "08:30", "end": "11:55", "is_girls": False, "day_type": "モーニング"},
            "岐阜": {"desc": "FII 前検日コメならウィンチケット杯 2日目", "start": "08:50", "end": "11:55", "is_girls": False, "day_type": "モーニング"},
            "武雄": {"desc": "FII 前検日コメならウィンチケット杯 2日目", "start": "20:40", "end": "23:40", "is_girls": True, "day_type": "ミッドナイト"}
        },
        "keiba": {
            "帯広": {"desc": "ナイター", "start": "14:20", "end": "20:40", "day_type": "ナイター"},
            "門別": {"desc": "北海道スプリントC JpnⅢ", "start": "14:00", "end": "20:40", "day_type": "ナイター"},
            "大井": {"desc": "ナイター", "start": "14:25", "end": "20:50", "day_type": "ナイター"},
            "笠松": {"desc": "薄暮", "start": "11:15", "end": "18:00", "day_type": "薄暮"},
            "園田": {"desc": "薄暮", "start": "13:30", "end": "19:30", "day_type": "薄暮"},
            "金沢": {"desc": "ナイター", "start": "15:05", "end": "20:50", "day_type": "ナイター"}
        },
        "auto": {"伊勢崎": {"desc": "SG 3日目", "start": "18:00", "end": "21:30", "day_type": "ナイター"}}
    },
    "20260814": {
        "keirin": {
            "松山": {"desc": "GI オールスター競輪 4日目", "start": "15:15", "end": "20:50", "is_girls": True, "day_type": "ナイター"},
            "京王閣": {"desc": "FI KEIRINライジングスターズ 初日", "start": "10:30", "end": "16:30", "is_girls": False, "day_type": "デイ"},
            "奈良": {"desc": "FI KEIRINライジングスターズ 初日", "start": "10:30", "end": "16:30", "is_girls": False, "day_type": "デイ"},
            "青森": {"desc": "FII AI競輪も大人気チャリロト杯 最終日", "start": "20:40", "end": "23:40", "is_girls": False, "day_type": "ミッドナイト"},
            "西武園": {"desc": "FII オッズパーク杯 2日目", "start": "08:30", "end": "11:55", "is_girls": False, "day_type": "モーニング"},
            "岐阜": {"desc": "FII 前検日コメならウィンチケット杯 最終日", "start": "08:50", "end": "11:55", "is_girls": False, "day_type": "モーニング"},
            "武雄": {"desc": "FII 前検日コメならウィンチケット杯 最終日", "start": "20:40", "end": "23:40", "is_girls": True, "day_type": "ミッドナイト"}
        },
        "keiba": {
            "帯広": {"desc": "ナイター", "start": "14:20", "end": "20:40", "day_type": "ナイター"},
            "門別": {"desc": "ナイター", "start": "14:00", "end": "20:40", "day_type": "ナイター"},
            "大井": {"desc": "ナイター", "start": "14:25", "end": "20:50", "day_type": "ナイター"},
            "笠松": {"desc": "薄暮", "start": "11:15", "end": "18:00", "day_type": "薄暮"},
            "園田": {"desc": "その金ナイター (摂津盃)", "start": "15:00", "end": "20:30", "day_type": "ナイター"}
        },
        "auto": {
            "伊勢崎": {"desc": "SG 4日目", "start": "18:00", "end": "21:30", "day_type": "ナイター"},
            "飯塚": {"desc": "ミッドナイト", "start": "20:20", "end": "23:45", "day_type": "ミッドナイト"}
        }
    },
    "20260815": {
        "keirin": {
            "松山": {"desc": "GI オールスター競輪 5日目", "start": "15:15", "end": "20:50", "is_girls": True, "day_type": "ナイター"},
            "京王閣": {"desc": "FI KEIRINライジングスターズ 2日目", "start": "10:30", "end": "16:30", "is_girls": False, "day_type": "デイ"},
            "奈良": {"desc": "FI KEIRINライジングスターズ 2日目", "start": "10:30", "end": "16:30", "is_girls": False, "day_type": "デイ"},
            "前橋": {"desc": "FII 前検日コメならウィンチケット杯 初日", "start": "20:40", "end": "23:40", "is_girls": True, "day_type": "ミッドナイト"},
            "西武園": {"desc": "FII オッズパーク杯 最終日", "start": "08:30", "end": "11:55", "is_girls": False, "day_type": "モーニング"},
            "静岡": {"desc": "FII オッズパーク杯 初日", "start": "20:40", "end": "23:40", "is_girls": False, "day_type": "ミッドナイト"}
        },
        "keiba": {
            "札幌": {"desc": "JRA 札幌開催", "start": "09:40", "end": "17:00", "day_type": "デイ"},
            "新潟": {"desc": "JRA 新潟ジャンプS", "start": "09:40", "end": "17:00", "day_type": "デイ"},
            "中京": {"desc": "JRA 中京開催", "start": "09:40", "end": "17:00", "day_type": "デイ"},
            "ＪＲＡ公式": {"desc": "JRA公式中継", "start": "09:00", "end": "17:00", "day_type": "デイ"},
            "ＪＲＡグリーン": {"desc": "グリーンチャンネル", "start": "09:00", "end": "21:00", "day_type": "デイ"},
            "帯広": {"desc": "ナイター", "start": "14:20", "end": "20:40", "day_type": "ナイター"},
            "大井": {"desc": "ナイター", "start": "14:25", "end": "20:50", "day_type": "ナイター"},
            "佐賀": {"desc": "ナイター", "start": "15:55", "end": "20:50", "day_type": "ナイター"}
        },
        "auto": {
            "伊勢崎": {"desc": "SG 最終日", "start": "18:00", "end": "21:30", "day_type": "ナイター"},
            "飯塚": {"desc": "ミッドナイト", "start": "20:20", "end": "23:45", "day_type": "ミッドナイト"}
        }
    },
    "20260816": {
        "keirin": {
            "松山": {"desc": "GI オールスター競輪 決勝戦", "start": "15:15", "end": "20:50", "is_girls": True, "day_type": "ナイター"},
            "京王閣": {"desc": "FI KEIRINライジングスターズ 最終日", "start": "10:30", "end": "16:30", "is_girls": False, "day_type": "デイ"},
            "奈良": {"desc": "FI KEIRINライジングスターズ 最終日", "start": "10:30", "end": "16:30", "is_girls": False, "day_type": "デイ"},
            "前橋": {"desc": "FII 前検日コメならウィンチケット杯 2日目", "start": "20:40", "end": "23:40", "is_girls": True, "day_type": "ミッドナイト"},
            "伊東": {"desc": "FI PayPay銀行杯 初日", "start": "10:30", "end": "16:30", "is_girls": False, "day_type": "デイ"},
            "静岡": {"desc": "FII オッズパーク杯 2日目", "start": "20:40", "end": "23:40", "is_girls": False, "day_type": "ミッドナイト"},
            "別府": {"desc": "FI CTCは3分前杯 初日", "start": "10:30", "end": "16:30", "is_girls": False, "day_type": "デイ"}
        },
        "keiba": {
            "札幌": {"desc": "札幌記念 GⅡ", "start": "09:40", "end": "17:00", "day_type": "デイ"},
            "新潟": {"desc": "JRA 新潟開催", "start": "09:40", "end": "17:00", "day_type": "デイ"},
            "中京": {"desc": "JRA 中京開催", "start": "09:40", "end": "17:00", "day_type": "デイ"},
            "ＪＲＡ公式": {"desc": "JRA公式中継", "start": "09:00", "end": "17:00", "day_type": "デイ"},
            "ＪＲＡグリーン": {"desc": "グリーンチャンネル", "start": "09:00", "end": "21:00", "day_type": "デイ"},
            "帯広": {"desc": "ナイター", "start": "14:20", "end": "20:40", "day_type": "ナイター"},
            "大井": {"desc": "ナイター", "start": "14:25", "end": "20:50", "day_type": "ナイター"},
            "佐賀": {"desc": "ナイター", "start": "15:55", "end": "20:50", "day_type": "ナイター"}
        },
        "auto": {
            "飯塚": {"desc": "ミッドナイト", "start": "20:20", "end": "23:45", "day_type": "ミッドナイト"}
        }
    },
    "20260817": {
        "keirin": {
            "前橋": {"desc": "FII 前検日コメならウィンチケット杯 最終日", "start": "20:40", "end": "23:40", "is_girls": True, "day_type": "ミッドナイト"},
            "西武園": {"desc": "FII 2日目", "start": "08:30", "end": "11:55", "is_girls": False, "day_type": "モーニング"},
            "静岡": {"desc": "FII オッズパーク杯 最終日", "start": "20:40", "end": "23:40", "is_girls": False, "day_type": "ミッドナイト"},
            "立川": {"desc": "FI 初日", "start": "10:30", "end": "16:30", "is_girls": False, "day_type": "デイ"},
            "伊東": {"desc": "FI PayPay銀行杯 2日目", "start": "10:30", "end": "16:30", "is_girls": False, "day_type": "デイ"},
            "別府": {"desc": "FI CTCは3分前杯 2日目", "start": "10:30", "end": "16:30", "is_girls": False, "day_type": "デイ"}
        },
        "keiba": {
            "盛岡": {"desc": "薄暮", "start": "11:40", "end": "18:10", "day_type": "薄暮"},
            "門別": {"desc": "ナイター", "start": "14:00", "end": "20:40", "day_type": "ナイター"},
            "金沢": {"desc": "ナイター", "start": "15:05", "end": "20:50", "day_type": "ナイター"}
        },
        "auto": {
            "飯塚": {"desc": "ミッドナイト", "start": "20:20", "end": "23:45", "day_type": "ミッドナイト"}
        }
    }
}

ICON_MAP = {"keirin": "🚲", "keiba": "🏇", "auto": "🏍️"}

def format_time_xml(dt):
    return dt.strftime("%Y%m%d%H%M%S +0900")

def build_epg_xml():
    tv = ET.Element("tv", {"generator-info-name": "CombinedEPGGenerator"})
    JST = datetime.timezone(datetime.timedelta(hours=9))
    
    all_channels = {**KEIRIN_MAP, **KEIBA_MAP, **AUTO_MAP}
    
    for v_name, tvg_id in all_channels.items():
        channel = ET.SubElement(tv, "channel", id=tvg_id)
        ET.SubElement(channel, "display-name").text = v_name

    for date_str in SCHEDULES.keys():
        day_schedules = SCHEDULES.get(date_str, {})
        dt_obj = datetime.datetime.strptime(date_str, "%Y%m%d")
        today_display = dt_obj.strftime("%Y年%m月%d日")

        for target_map, category in [(KEIRIN_MAP, "keirin"), (KEIBA_MAP, "keiba"), (AUTO_MAP, "auto")]:
            cat_data = day_schedules.get(category, {})
            cat_label = {"keirin": "競輪", "keiba": "競馬", "auto": "オートレース"}.get(category, "")

            for v_name, tvg_id in target_map.items():
                day_start = datetime.datetime.strptime(f"{date_str} 01:00", "%Y%m%d %H:%M").replace(tzinfo=JST)
                day_end = datetime.datetime.strptime(f"{date_str} 23:59", "%Y%m%d %H:%M").replace(tzinfo=JST)

                if v_name in cat_data:
                    info = cat_data[v_name]
                    is_girls = info.get("is_girls", False)
                    day_type = info.get("day_type", "デイ")
                    
                    type_emoji = "🌞"
                    if day_type == "ナイター":
                        type_emoji = "🌙"
                    elif day_type == "ミッドナイト":
                        type_emoji = "🌟"
                    elif day_type == "モーニング":
                        type_emoji = "🌅"

                    girls_tag = "💛ガールズ" if is_girls else ""

                    grade_list = ["GI", "GII", "GIII", "FI", "FII", "SG", "JpnI", "JpnII", "JpnIII"]
                    grade_found = next((g for g in grade_list if g in info['desc']), "")
                    
                    day_match_str = ""
                    for term in ["初日", "2日目", "3日目", "4日目", "5日目", "決勝戦", "最終日"]:
                        if term in info['desc']:
                            day_match_str = term
                            break

                    match_emoji_str = "🏆 決勝戦" if "決勝戦" in info['desc'] else day_match_str
                    grade_prefix = f"【{grade_found}】" if grade_found else ""
                    
                    title_parts = [
                        grade_prefix,
                        "🔴 LIVE",
                        v_name,
                        f"{type_emoji}{day_type}",
                        match_emoji_str,
                        girls_tag,
                        f"（{cat_label}）"
                    ]
                    title_live = " ".join([p for p in title_parts if p])

                    start_dt = datetime.datetime.strptime(f"{date_str} {info['start']}", "%Y%m%d %H:%M").replace(tzinfo=JST)
                    end_dt = datetime.datetime.strptime(f"{date_str} {info['end']}", "%Y%m%d %H:%M").replace(tzinfo=JST)
                    
                    pre_start = start_dt - datetime.timedelta(minutes=10)
                    post_end = end_dt + datetime.timedelta(minutes=10)

                    desc_text = (
                        f"{ICON_MAP.get(category, '⭐')} 開催地: {v_name} ({day_type})\n"
                        f"🏆 グレード: {grade_found if grade_found else '通常開催'}\n"
                        f"✨ ガールズ: {'あり 💛' if is_girls else 'なし'}\n"
                        f"📢 内容: {info['desc']}\n"
                        f"⏰ 時間: {info['start']} - {info['end']}\n"
                        f"📅 日付: {today_display}"
                    )

                    if day_start < pre_start:
                        prog1 = ET.SubElement(tv, "programme", start=format_time_xml(day_start), stop=format_time_xml(pre_start), channel=tvg_id)
                        ET.SubElement(prog1, "title", lang="ja").text = f"⏳ 待機 {v_name} ({type_emoji}{day_type} 1R {info['start']}開始)（{cat_label}）"
                        ET.SubElement(prog1, "desc", lang="ja").text = desc_text

                    prog2 = ET.SubElement(tv, "programme", start=format_time_xml(pre_start), stop=format_time_xml(post_end), channel=tvg_id)
                    ET.SubElement(prog2, "title", lang="ja").text = title_live
                    ET.SubElement(prog2, "desc", lang="ja").text = desc_text

                    if post_end < day_end:
                        prog3 = ET.SubElement(tv, "programme", start=format_time_xml(post_end), stop=format_time_xml(day_end), channel=tvg_id)
                        ET.SubElement(prog3, "title", lang="ja").text = f"🏁 終了 {v_name} ({type_emoji}{day_type})（{cat_label}）"
                        ET.SubElement(prog3, "desc", lang="ja").text = f"{v_name} ({day_type}) の放送は終了しました。"
                else:
                    prog = ET.SubElement(tv, "programme", start=format_time_xml(day_start), stop=format_time_xml(day_end), channel=tvg_id)
                    ET.SubElement(prog, "title", lang="ja").text = f"💤 本日非開催 {v_name}（{cat_label}）"
                    ET.SubElement(prog, "desc", lang="ja").text = f"本日は{v_name}での開催予定はありません。"

    tree = ET.ElementTree(tv)
    if hasattr(ET, "indent"): ET.indent(tree, space="    ")
    tree.write("epg.xml", encoding="utf-8", xml_declaration=True)

if __name__ == "__main__":
    build_epg_xml()
