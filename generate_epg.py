import datetime
import json
import xml.etree.ElementTree as ET
import requests

# さきほどM3Uで定義した tvg-id と競輪場名のマッピング（全43場＋PIST6）
VENUE_MAP = {
    "函館": "keirin.hakodate",
    "青森": "keirin.aomori",
    "いわき平": "keirin.iwakitaira",
    "弥彦": "keirin.yahiko",
    "前橋": "keirin.maebashi",
    "取手": "keirin.toride",
    "宇都宮": "keirin.utsunomiya",
    "大宮": "keirin.omiya",
    "西武園": "keirin.seibuen",
    "京王閣": "keirin.keiogatsu",
    "立川": "keirin.tachikawa",
    "松戸": "keirin.matsudo",
    "川崎": "keirin.kawasaki",
    "平塚": "keirin.hiratsuka",
    "小田原": "keirin.odawara",
    "伊東温泉": "keirin.ito",
    "静岡": "keirin.shizuoka",
    "名古屋": "keirin.nagoya",
    "岐阜": "keirin.gifu",
    "大垣": "keirin.ogaki",
    "豊橋": "keirin.toyohashi",
    "松阪": "keirin.matsusaka",
    "四日市": "keirin.yokkaichi",
    "富山": "keirin.toyama",
    "福井": "keirin.fukui",
    "奈良": "keirin.nara",
    "岸和田": "keirin.kishiwada",
    "和歌山": "keirin.wakayama",
    "玉野": "keirin.tamano",
    "広島": "keirin.hiroshima",
    "防府": "keirin.hofu",
    "小松島": "keirin.komatsushima",
    "松山": "keirin.matsuyama",
    "高知": "keirin.kochi",
    "小倉": "keirin.kokura",
    "久留米": "keirin.kurume",
    "武雄": "keirin.takeo",
    "佐世保": "keirin.sasebo",
    "別府": "keirin.beppu",
    "熊本": "keirin.kumamoto",
    "千葉PIST6": "keirin.pist6",
}


def fetch_today_keirin_schedule(date_str):
    """KEIRIN.JP の公式開催日程データ(JSON)を取得"""
    url = f"https://keirin.jp/pc/dfw/datainfo/SCHEDULE/schedule_{date_str[:6]}.json"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=10)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"データ取得エラー: {e}")

    return []


def build_epg_xml():
    now = datetime.datetime.now()
    today_str = now.strftime("%Y%m%d")  # YYYYMMDD
    today_display = now.strftime("%Y年%m月%d日")

    # XMLのルート要素生成
    tv = ET.Element("tv", {"generator-info-name": "KeirinAutoEPG"})

    # 本日の開催スケジュールデータを取得
    raw_schedule = fetch_today_keirin_schedule(today_str)

    # 本日開催されている競輪場の情報を解析・抽出
    active_venues = {}
    for item in raw_schedule:
        # 本日の日付と一致する開催情報をパース
        if item.get("hd") == today_str:
            v_name = item.get("joName")  # 場名（例: 和歌山）
            day_num = item.get("kaiDayName", "")  # 日数（例: 初日、最終日）
            grade = item.get("gradeName", "")  # グレード（例: G3, FI）
            last_time_str = item.get("lastRaceTime", "")  # 最終レース発走予定時刻 (例: "16:24")

            if v_name in VENUE_MAP:
                active_venues[v_name] = {
                    "day_num": day_num,
                    "grade": grade,
                    "last_time_str": last_time_str,
                }

    # 全競輪場ループして EPG（<channel> と <programme>）を作成
    for v_name, tvg_id in VENUE_MAP.items():
        # <channel> の追加
        channel = ET.SubElement(tv, "channel", id=tvg_id)
        disp_name = ET.SubElement(channel, "display-name")
        disp_name.text = f"{v_name}競輪"

        # 番組枠の時間（本日終日 00:00:00 〜 23:59:59）
        start_xml = f"{today_str}000000 +0900"
        stop_xml = f"{today_str}235959 +0900"

        # 状態判定ロジック
        if v_name in active_venues:
            info = active_venues[v_name]
            day_num = info["day_num"]
            grade = info["grade"]
            last_time_str = info["last_time_str"]

            # 最終レースの終了時刻（発走から約30分後）を判定
            is_finished = False
            if last_time_str:
                try:
                    last_h, last_m = map(int, last_time_str.split(":"))
                    last_race_dt = now.replace(
                        hour=last_h, minute=last_m, second=0
                    ) + datetime.timedelta(minutes=30)
                    if now > last_race_dt:
                        is_finished = True
                except ValueError:
                    pass

            if is_finished:
                title_text = "本日のレースは全レース終了しました"
                desc_text = f"{today_display} {day_num} ({grade}) の全レース・払戻は終了いたしました。"
            else:
                title_text = f"【開催】{day_num} ({grade})"
                desc_text = f"{today_display} {v_name}競輪 開催中"
                if last_time_str:
                    desc_text += f"（最終R発走予定 {last_time_str} 頃）"
        else:
            title_text = "本日非開催"
            desc_text = f"{today_display} 本日のレース開催はありません。"

        # <programme> の追加
        programme = ET.SubElement(
            tv,
            "programme",
            start=start_xml,
            stop=stop_xml,
            channel=tvg_id,
        )
        title = ET.SubElement(programme, "title", lang="ja")
        title.text = title_text
        desc = ET.SubElement(programme, "desc", lang="ja")
        desc.text = desc_text

    # XMLファイルへ保存
    tree = ET.ElementTree(tv)
    ET.indent(tree, space="  ")
    tree.write("epg.xml", encoding="utf-8", xml_declaration=True)
    print("epg.xml の自動生成が完了しました。")


if __name__ == "__main__":
    build_epg_xml()
