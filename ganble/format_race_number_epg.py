from pathlib import Path
import re
import xml.etree.ElementTree as ET

TARGET_PREFIXES = ("keirin.", "chihou.", "keiba.", "auto.", "boat.")
TARGET_JRA = {"jra.east", "jra.west", "jra.hokkaido"}
CIRCLED_R = {
    "❶": "1", "❷": "2", "❸": "3", "❹": "4", "❺": "5", "❻": "6",
    "❼": "7", "❽": "8", "❾": "9", "❿": "10", "⓫": "11", "⓬": "12",
}
FULLWIDTH = str.maketrans("0123456789R", "０１２３４５６７８９Ｒ")


def is_target(cid):
    return cid.startswith(TARGET_PREFIXES) or cid in TARGET_JRA


def bracket_race_no(n):
    return f"【{str(n).translate(FULLWIDTH)}Ｒ】" if not str(n).endswith("R") else f"【{str(n).translate(FULLWIDTH)}】"


def format_title(title):
    s = str(title or "")

    # Current decorated form: ❼ℛ ... / ⓫ℛ ...
    for symbol, n in CIRCLED_R.items():
        s, count = re.subn(rf"(?<!\S){re.escape(symbol)}ℛ(?=\s|$)", bracket_race_no(n), s, count=1)
        if count:
            return s

    # Plain form: 7R ... / 12R ...
    m = re.search(r"(?<!\d)(1[0-2]|[1-9])\s*[RＲ](?=\s|$)", s, flags=re.I)
    if m:
        return s[:m.start()] + bracket_race_no(m.group(1)) + s[m.end():]

    # Already formatted: normalize half-width digits if necessary.
    m = re.search(r"【\s*(1[0-2]|[1-9]|[０-９]{1,2})\s*[RＲ]\s*】", s, flags=re.I)
    if m:
        raw = m.group(1).translate(str.maketrans("０１２３４５６７８９", "0123456789"))
        return s[:m.start()] + bracket_race_no(raw) + s[m.end():]

    return s


def main():
    path = Path("epg.xml")
    tree = ET.parse(path)
    root = tree.getroot()
    changed = 0

    for p in root.findall("programme"):
        if not is_target(p.get("channel", "")):
            continue
        title = p.find("title")
        if title is None or not title.text:
            continue
        new_title = format_title(title.text)
        if new_title != title.text:
            title.text = new_title
            changed += 1

    ET.indent(tree, space="    ")
    tree.write(path, encoding="utf-8", xml_declaration=True)
    print(f"Race numbers formatted for OTT: {changed}")


if __name__ == "__main__":
    main()
