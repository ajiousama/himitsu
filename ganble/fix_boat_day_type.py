from pathlib import Path
import datetime
import re
import xml.etree.ElementTree as ET

EPG = Path("epg.xml")
JST = datetime.timezone(datetime.timedelta(hours=9))
RACE_TIME_RE = re.compile(r"([0-2]?\d:[0-5]\d)\s*発走")


def parse_dt(value):
    m = re.match(r"(\d{14})\s*([+-]\d{4})?", str(value or ""))
    if not m:
        return None
    digits, off = m.groups()
    if off:
        return datetime.datetime.strptime(f"{digits} {off}", "%Y%m%d%H%M%S %z").astimezone(JST)
    return datetime.datetime.strptime(digits, "%Y%m%d%H%M%S").replace(tzinfo=JST)


def logical_date(dt):
    return dt.date() if dt.hour >= 4 else dt.date() - datetime.timedelta(days=1)


def race_minutes(title):
    m = RACE_TIME_RE.search(title or "")
    if not m:
        return None
    h, minute = map(int, m.group(1).split(":"))
    return h * 60 + minute


def classify(cid, times):
    if not times:
        return None
    first, last = min(times), max(times)

    # ミッドナイトBOATは通常のナイターより開始が遅く、最終Rも遅い。
    # 大村を含め、今後ほかの場で実施されても時刻から自動判定する。
    if first >= 17 * 60 and last >= 21 * 60 + 30:
        return "ミッドナイト"
    if first >= 13 * 60 + 30:
        return "ナイター"
    if first < 10 * 60:
        return "モーニング"
    return "デイ"


def main():
    tree = ET.parse(EPG)
    root = tree.getroot()
    groups = {}

    for p in root.findall("programme"):
        cid = p.get("channel", "")
        if not cid.startswith("boat."):
            continue
        start = parse_dt(p.get("start"))
        if start is None:
            continue
        minutes = race_minutes(p.findtext("title") or "")
        if minutes is None:
            continue
        key = (cid, logical_date(start))
        groups.setdefault(key, {"times": [], "programmes": []})
        groups[key]["times"].append(minutes)
        groups[key]["programmes"].append(p)

    changed = 0
    for (cid, day), info in groups.items():
        day_type = classify(cid, info["times"])
        if not day_type:
            continue
        marker = f"開催区分: {day_type}"
        for p in info["programmes"]:
            desc = p.find("desc")
            if desc is None:
                desc = ET.SubElement(p, "desc", lang="ja")
            text = desc.text or ""
            text = re.sub(r"(?:^|\s)開催区分:\s*(?:モーニング|デイ|通常|薄暮|サマータイム|ナイター|ミッドナイト|オーバーミッドナイト)", "", text).strip()
            desc.text = f"{text} {marker}".strip()
            changed += 1
        if cid == "boat.omura":
            print(f"BOATRACE大村 {day}: {day_type} ({min(info['times'])//60:02d}:{min(info['times'])%60:02d}-{max(info['times'])//60:02d}:{max(info['times'])%60:02d})")

    ET.indent(tree, space="    ")
    tree.write(EPG, encoding="utf-8", xml_declaration=True)
    print(f"BOAT day type fixed: {changed} programmes")


if __name__ == "__main__":
    main()
