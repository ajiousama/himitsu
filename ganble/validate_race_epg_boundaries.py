from pathlib import Path
import datetime as dt
import re
import xml.etree.ElementTree as ET

JST = dt.timezone(dt.timedelta(hours=9))
TARGET_PREFIXES = ("keirin.", "chihou.", "keiba.", "auto.", "boat.")
TARGET_JRA = {"jra.east", "jra.west", "jra.hokkaido"}
RACE_RE = re.compile(r"(?:【\s*\d{1,2}\s*[RＲ]\s*】|[❶❷❸❹❺❻❼❽❾❿⓫⓬]ℛ|(?<!\d)\d{1,2}\s*R\b)")
DATE_PATTERNS = [
    re.compile(r"📅\s*(\d{4})年(\d{1,2})月(\d{1,2})日"),
    re.compile(r"📅\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})"),
]


def parse_xmltv(v):
    m = re.match(r"(\d{14})\s*([+-]\d{4})?", str(v or "").strip())
    if not m:
        return None
    digits, off = m.groups()
    if off:
        return dt.datetime.strptime(f"{digits} {off}", "%Y%m%d%H%M%S %z").astimezone(JST)
    return dt.datetime.strptime(digits, "%Y%m%d%H%M%S").replace(tzinfo=JST)


def fmt(x):
    return x.astimezone(JST).strftime("%Y%m%d%H%M%S +0900")


def is_target(cid):
    return cid.startswith(TARGET_PREFIXES) or cid in TARGET_JRA


def title_of(p):
    return (p.findtext("title") or "").strip()


def desc_of(p):
    return (p.findtext("desc") or "").strip()


def is_race(p):
    return bool(RACE_RE.search(title_of(p)))


def race_date(p):
    text = desc_of(p)
    for pat in DATE_PATTERNS:
        m = pat.search(text)
        if m:
            try:
                return dt.date(*map(int, m.groups()))
            except ValueError:
                return None
    return None


def intro_title(cid, programmes):
    text = " ".join(title_of(p) + " " + desc_of(p) for p in programmes)
    day = ""
    m = re.search(r"(?:開催日次[:：]?\s*|[（(])(\d+)日目", text)
    if m:
        day = f"（{m.group(1)}日目）"
    if cid.startswith("keirin."):
        if "ミッドナイト" in text: kind = "🌟ミッドナイト競輪🌟"
        elif "モーニング" in text: kind = "🌅モーニング競輪🌅"
        elif "ナイター" in text: kind = "🌙ナイター競輪🌙"
        else: kind = "🚲競輪🚲"
    elif cid.startswith("boat."):
        kind = "🌙ナイターボートレース🌙" if "ナイター" in text else "🚤ボートレース🚤"
    elif cid.startswith("auto."):
        if "オーバーミッドナイト" in text: kind = "🌌オーバーミッドナイトオート🌌"
        elif "ミッドナイト" in text: kind = "🌟ミッドナイトオート🌟"
        elif "ナイター" in text: kind = "🌙ナイターオート🌙"
        else: kind = "🏍️オートレース🏍️"
    elif cid.startswith(("chihou.", "keiba.")):
        kind = "🌙ナイター競馬🌙" if "ナイター" in text else "🏇地方競馬🏇"
    else:
        kind = "🏇JRA中央競馬🏇"
    return f"本日は {kind}{day}をお送りします", kind


def add_block(root, cid, start, stop, title, desc):
    if stop <= start:
        return
    p = ET.SubElement(root, "programme", start=fmt(start), stop=fmt(stop), channel=cid)
    ET.SubElement(p, "title", lang="ja").text = title
    ET.SubElement(p, "desc", lang="ja").text = desc


def main():
    path = Path("epg.xml")
    tree = ET.parse(path)
    root = tree.getroot()

    shifted = 0
    # 1) レース本文の📅日付と programme の日付がずれていたら、レースを正しい日に移す。
    #    0～3時台の前日開催続行（ミッドナイト等）は例外として許可する。
    for p in root.findall("programme"):
        cid = p.get("channel", "")
        if not is_target(cid) or not is_race(p):
            continue
        rd = race_date(p)
        st = parse_xmltv(p.get("start")); en = parse_xmltv(p.get("stop"))
        if not rd or not st or not en:
            continue
        allowed_overnight = st.hour < 4 and rd == st.date() - dt.timedelta(days=1)
        if rd != st.date() and not allowed_overnight:
            delta = rd - st.date()
            # 3日EPGの範囲を超えるような異常値は触らない。
            if abs(delta.days) <= 2:
                p.set("start", fmt(st + dt.timedelta(days=delta.days)))
                p.set("stop", fmt(en + dt.timedelta(days=delta.days)))
                shifted += 1

    today = dt.datetime.now(JST).date()
    rebuilt = 0

    # 2) 今日～2日後について、各競技の「開始前」と「最終R後」をレース実体から再構成。
    #    翌日レースを当日枠へ流用しない。
    for day_offset in range(3):
        day = today + dt.timedelta(days=day_offset)
        wall_start = dt.datetime.combine(day, dt.time(0, 0), tzinfo=JST)
        wall_end = wall_start + dt.timedelta(days=1)

        channels = sorted({p.get("channel", "") for p in root.findall("programme") if is_target(p.get("channel", ""))})
        for cid in channels:
            races = []
            for p in root.findall("programme"):
                if p.get("channel") != cid or not is_race(p):
                    continue
                st = parse_xmltv(p.get("start")); en = parse_xmltv(p.get("stop")); rd = race_date(p)
                if not st or not en:
                    continue
                # 通常は壁時計日付。0～3時台のみ前日開催のレース日を許可。
                logical = rd or st.date()
                if logical == day and (st.date() == day or (st.hour < 4 and st.date() == day + dt.timedelta(days=1))):
                    races.append((st, en, p))
            if not races:
                continue

            races.sort(key=lambda x: x[0])
            first_start = races[0][0]
            last_stop = max(x[1] for x in races)
            intro, kind = intro_title(cid, [x[2] for x in races])

            # 日付内の非レース待機/案内/終了ブロックだけを除去。レース本体は保持。
            for p in list(root.findall("programme")):
                if p.get("channel") != cid or is_race(p):
                    continue
                st = parse_xmltv(p.get("start")); en = parse_xmltv(p.get("stop"))
                if st and en and en > wall_start and st < wall_end:
                    root.remove(p)

            pre_end = min(first_start, wall_end)
            if pre_end > wall_start:
                add_block(root, cid, wall_start, pre_end, intro, "本日の開催開始前案内です。")

            # 当日壁時計内で最終R後なら必ず終了表示。
            finish_start = max(last_stop, wall_start)
            if finish_start < wall_end:
                add_block(root, cid, finish_start, wall_end, f"🏁 本日の{kind}は終了しました", "本日の全レースは終了しました。")
            rebuilt += 1

    # 3) 旧「待機」表示が残っていないかを最終除去。レースがある日の旧待機だけ開催案内へ置換。
    converted = 0
    for p in root.findall("programme"):
        cid = p.get("channel", "")
        if not is_target(cid):
            continue
        te = p.find("title")
        if te is None or not te.text:
            continue
        if "待機" in te.text or "開催情報確認待ち" in te.text:
            st = parse_xmltv(p.get("start"))
            if not st:
                continue
            same_day_races = [q for q in root.findall("programme") if q.get("channel") == cid and is_race(q) and (race_date(q) or (parse_xmltv(q.get("start")) or st).date()) == st.date()]
            if same_day_races:
                te.text = intro_title(cid, same_day_races)[0]
                converted += 1

    programmes = list(root.findall("programme"))
    for p in programmes:
        root.remove(p)
    programmes.sort(key=lambda p: (parse_xmltv(p.get("start")) or dt.datetime.max.replace(tzinfo=JST), p.get("channel", "")))
    for p in programmes:
        root.append(p)

    ET.indent(tree, space="    ")
    tree.write(path, encoding="utf-8", xml_declaration=True)
    print(f"Race EPG boundary validation: shifted={shifted} rebuilt={rebuilt} old_wait_converted={converted}")


if __name__ == "__main__":
    main()
