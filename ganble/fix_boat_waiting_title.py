import re
import xml.etree.ElementTree as ET

EPG = "epg.xml"


def main():
    tree = ET.parse(EPG)
    root = tree.getroot()
    changed = 0

    for prog in root.findall("programme"):
        channel = prog.get("channel", "")
        if not channel.startswith("boat."):
            continue

        title_el = prog.find("title")
        if title_el is None:
            continue

        title = title_el.text or ""
        if not title.startswith("⏳ 待機"):
            continue

        desc_el = prog.find("desc")
        desc = (desc_el.text or "") if desc_el is not None else ""

        m = re.search(r"1R\s*([0-2]?\d:[0-5]\d)\s*発走予定", desc)
        if not m:
            continue

        hhmm = m.group(1)
        # 場名は既存タイトルの「待機」の直後から、開催区分絵文字の手前までを利用。
        venue = re.sub(r"^⏳\s*待機\s*", "", title)
        venue = re.split(r"\s+(?:🌅|☀️|🌙|🚤)", venue, maxsplit=1)[0].strip()
        if not venue:
            venue = channel

        new_title = f"🚤 {venue}　本日開催　第1️⃣R {hhmm}発走予定❗️"
        if new_title != title:
            title_el.text = new_title
            changed += 1

    if hasattr(ET, "indent"):
        ET.indent(tree, space="    ")

    tree.write(EPG, encoding="utf-8", xml_declaration=True)
    print(f"BOAT waiting titles updated: {changed}")


if __name__ == "__main__":
    main()
