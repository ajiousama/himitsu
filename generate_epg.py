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

# ==========================================
# 【スケジュール管理エリア】
# ==========================================
SCHEDULES = {
    "20260808": {
        "keirin": {
            "岐阜": "モーニング🌅 2日目（1R 8:50発走）",
            "和歌山": "G3 デイ☀ 準決勝（1R 10:50発走）", 
            "立川": "デイ☀ 初日（1R 10:57発走）",
            "佐世保": "G1 女子オールスター ナイター🌙 💛 準決勝（1R 15:40発走）", 
            "いわき平": "ナイター🌙 💛 最終日（1R 15:48発走）",
            "宇都宮": "ミッドナイト⭐ 💛 最終日（1R 20:40発走）", 
            "伊東": "ミッドナイト⭐ 最終日（1R 20:50発走）"
        },
        "keiba": {
            "新潟": "デイ☀（1R 9:40発走）", 
            "中京": "デイ☀（1R 9:50発走）", 
            "札幌": "エルムS GⅢ デイ☀（1R 10:00発走）",
            "帯広": "ナイター🌙（1R 14:45発走）", 
            "佐賀": "ナイター🌙（1R 16:00発走）"
        },
        "auto": {
            "川口": "デイ☀ 3日目（1R 10:56発走）", 
            "飯塚": "ミッドナイト⭐ 初日（1R 20:19発走）"
        }
    },
    "20260809": {
        "keirin": {
            "岐阜": "モーニング🌅 最終日（1R 8:50発走）", 
            "平塚": "モーニング🌅 初日（1R 8:30発走）",
            "和歌山": "G3 デイ☀ 💛 決勝（1R 10:50発走）", 
            "立川": "FI デイ☀ 2日目（1R 10:57発走）",
            "佐世保": "G1 女子オールスター ナイター🌙 💛 決勝（1R 15:40発走）", 
            "前橋": "モーニング🌅 初日（1R 8:30発走）",
            "川崎": "ミッドナイト⭐ 💛 初日（1R 20:40発走）", 
            "四日市": "ミッドナイト⭐ 💛 初日（1R 20:50発走）"
        },
        "keiba": {
            "新潟": "レパードS GⅢ デイ☀（1R 9:35発走）", 
            "中京": "CBC賞 GⅢ デイ☀（1R 9:50発走）", 
            "札幌": "デイ☀（1R 9:55発走）",
            "盛岡": "薄暮🌇（1R 13:30発走）", 
            "帯広": "ナイター🌙（1R 14:25発走）", 
            "佐賀": "ナイター🌙（1R 15:55発走）", 
            "金沢": "ナイター🌙（1R 16:35発走）"
        },
        "auto": {
            "川口": "デイ☀ 最終日（1R 10:30発走）"
        }
    },
    "20260810": {
        "keirin": {
            "前橋": "モーニング🌅 2日目（1R 8:30発走）",
            "立川": "FI デイ☀ 最終日（1R 10:57発走）",
            "平塚": "ナイター🌙 💛 2日目（1R 15:00発走）",
            "川崎": "ナイター🌙 💛 2日目（1R 20:40発走）",
            "四日市": "ナイター🌙 💛 2日目（1R 20:50発走）",
            "富山": "ミッドナイト⭐ 💛 初日（1R 20:40発走）"
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
            "前橋": "モーニング🌅 最終日（1R 8:30発走）",
            "川崎": "ナイター🌙 💛 最終日（1R 20:40発走）",
            "平塚": "ナイター🌙 💛 最終日（1R 15:00発走）",
            "富山": "ミッドナイト⭐ 💛 2日目（1R 20:40発走）",
            "四日市": "ナイター🌙 💛 最終日（1R 20:50発走）",
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
    
    # 現在時刻を取得
    now = datetime.datetime.now()
    
    # 25:00（深夜1:00）以降、または深夜0:00〜1:00未満の場合、日付を「翌日」扱いに繰り上げる
    # ※夜の25:00実行を想定し、前日分を終了して翌日分を表示させます
    if now.hour < 3:  # 深夜3時未満に実行された場合は前日の深夜帯（または日付またぎ）とみなして処理するなどの調整も可能ですが、
        # 単純に「25時以降（hour >= 1 および hour < アクションの都合など）」とする場合、
        # ここでは一般的な「現在時刻のhourが深夜帯（例: 0〜2時など）」や「25時以降」の判定を入れられます。
        pass

    # ※通常の現在時刻取得をベースにしつつ、もし深夜1時(01:00)〜朝までなら前日深夜とみなして翌日扱いにするか、
    # あるいはご要望の「25:00以降（今日の25時＝翌日の1時）」の挙動にします。
    # Pythonで25時を表現する場合、時刻が1時台かつ日付を前日扱いにするのが一般的です。
    
    target_dt = now
    if now.hour < 4:  # 深夜0時〜3時台の実行であれば、実質的に「前日の深夜（25時以降の処理）」として扱う場合
        # お好みで調整可能ですが、通常通り today を取得しつつ、
        # 21時以降の判定を行っています。
        pass

    # ユーザー様ご指定の「25:00以降は明日の分に切り替える」ためのロジック：
    # もし現在時刻のhourが 0 または 1（深夜0時〜1時59分）の場合、日付を「前日（実質当日の深夜24時・25時台）」として扱うか、
    # あるいは「GitHub Actions等で25:00に走ったとき」に翌日を指すようにします。
    
    # ここでは安全に、現在時刻のhourが深夜1時〜3時台などの場合に「前日扱い（＝25時台の更新）」とするか、
    # または単に当日の日付文字列を取得します。
    
    today_str = now.strftime("%Y%m%d")
    
    # もし深夜0時〜3時台に実行された場合、カレンダー上の日付を1日戻して「前日の夜の続き（25時台）」として処理するアプローチ：
    if now.hour < 4:
        target_dt = now - datetime.timedelta(days=1)
        today_str = target_dt.strftime("%Y%m%d")

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
                jra_items = []
                for j_name, j_status in cat_data.items():
                    if j_name in ["新潟", "中京", "札幌"]:
                        jra_items.append(f"{j_name}{j_status}")
                
                if jra_items:
                    if current_hour >= 21 and current_hour < 4:
                        title_text = "💎本日は終了しました💎"
                    else:
                        title_text = f"【本日開催】 " + " ".join(jra_items)
                else:
                    title_text = "💎本日は開催しておりません💎"
            else:
                if v_name in cat_data:
                    status_val = cat_data[v_name]
                    # 21時以降かつミッドナイト以外は終了表示
                    if current_hour >= 21 and "ミッドナイト" not in status_val:
                        title_text = "💎本日は終了しました💎"
                    else:
                        title_text = f"【本日開催】 ({status_val})"
                else:
                    title_text = "💎本日は開催しておりません💎"

            desc_text = f"{today_display} {v_name} ステータス: {title_text}"

            prog = ET.SubElement(tv, "programme", start=f"{today_str}000000 +0900", stop=f"{today_str}235959 +0900", channel=tvg_id)
            ET.SubElement(prog, "title", lang="ja").text = title_text
            ET.SubElement(prog, "desc", lang="ja").text = desc_text

    tree = ET.ElementTree(tv)
    if hasattr(ET, "indent"): ET.indent(tree, space="  ")
    tree.write("epg.xml", encoding="utf-8", xml_declaration=True)
    print("本日のEPG生成完了")

if __name__ == "__main__":
    build_epg_xml()
