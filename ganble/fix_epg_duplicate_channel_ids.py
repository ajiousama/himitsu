from pathlib import Path
import xml.etree.ElementTree as ET

EPG = Path("epg.xml")

# 同名の競輪／地方競馬を完全に分離する。
# 競輪側だけひらがな、地方競馬側は漢字の正式表示。
REQUIRED_CHANNELS = {
    "keirin.kawasaki": "かわさきけいりん",
    "keirin.nagoya": "なごやけいりん",
    "keirin.kochi": "こうちけいりん",
    "chihou.kawasaki_keiba": "川崎けいば",
    "chihou.nagoya_keiba": "名古屋けいば",
    "chihou.kochi_keiba": "高知けいば",
}

root = ET.parse(EPG).getroot()

# 既存channel定義をidで管理する。
channels = {}
for ch in root.findall("channel"):
    cid = ch.get("id")
    if cid:
        if cid in channels:
            raise SystemExit(f"duplicate channel id before fix: {cid}")
        channels[cid] = ch

# programmeより前へ不足channelを追加し、対象表示名を必ず正規化する。
first_programme_index = next(
    (i for i, child in enumerate(list(root)) if child.tag == "programme"),
    len(root),
)

added = 0
updated = 0

for channel_id, display_name in REQUIRED_CHANNELS.items():
    ch = channels.get(channel_id)

    if ch is None:
        ch = ET.Element("channel", id=channel_id)
        ET.SubElement(ch, "display-name").text = display_name
        root.insert(first_programme_index, ch)
        first_programme_index += 1
        channels[channel_id] = ch
        added += 1
    else:
        dn = ch.find("display-name")
        if dn is None:
            dn = ET.SubElement(ch, "display-name")

        if (dn.text or "") != display_name:
            dn.text = display_name
            updated += 1

# 最終検証。6chが1つずつ存在し、表示名も完全一致しない限りWorkflowを失敗させる。
final_channels = {}
for ch in root.findall("channel"):
    cid = ch.get("id")
    if not cid:
        continue
    if cid in final_channels:
        raise SystemExit(f"duplicate channel id after fix: {cid}")
    final_channels[cid] = ch

for channel_id, expected_name in REQUIRED_CHANNELS.items():
    ch = final_channels.get(channel_id)
    if ch is None:
        raise SystemExit(f"missing required channel: {channel_id}")

    dn = ch.find("display-name")
    actual_name = (dn.text or "") if dn is not None else ""
    if actual_name != expected_name:
        raise SystemExit(
            f"wrong display-name: {channel_id}: {actual_name!r} != {expected_name!r}"
        )

# programmeがこの6chを使う場合、channel定義が存在することも保証。
for prog in root.findall("programme"):
    cid = prog.get("channel")
    if cid in REQUIRED_CHANNELS and cid not in final_channels:
        raise SystemExit(f"programme references undefined channel: {cid}")

tree = ET.ElementTree(root)
if hasattr(ET, "indent"):
    ET.indent(tree, space="    ")
tree.write(EPG, encoding="utf-8", xml_declaration=True)

print(f"EPG same-name channel separation: added={added} updated={updated}")
for cid, name in REQUIRED_CHANNELS.items():
    print("OK", cid, name)
