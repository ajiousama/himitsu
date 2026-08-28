from __future__ import annotations

import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

EPG = Path("guides.xml")
CONFIG = Path("kick_channels.json")
JST = timezone(timedelta(hours=9))
TITLE = "🟢📡✨ 現在KICK配信 受信中 ✨📡🟢"
DESC = "🎬 KICK STREAM RECEIVER 🎬\n📡 KICK配信チャンネルを受信しています。\n✨ 配信の有無にかかわらず、この案内は番組表に常時表示されます。"
CATEGORY = "KICK配信"


def xmltv_time(dt: datetime) -> str:
    return dt.strftime("%Y%m%d%H%M%S +0900")


def main() -> int:
    if not EPG.exists():
        raise RuntimeError("guides.xml is missing")
    if not CONFIG.exists():
        raise RuntimeError("kick_channels.json is missing")

    config = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    channels = []
    for item in config:
        if not isinstance(item, dict):
            continue
        tvg_id = str(item.get("tvg_id") or "").strip()
        name = str(item.get("name") or "").strip()
        if tvg_id and name:
            channels.append((tvg_id, name))
    if not channels:
        raise RuntimeError("No KICK EPG channels configured")

    tree = ET.parse(EPG)
    root = tree.getroot()
    ids = {tvg_id for tvg_id, _ in channels}

    for child in list(root):
        if child.tag == "channel" and child.get("id") in ids:
            root.remove(child)
        elif child.tag == "programme" and child.get("channel") in ids:
            root.remove(child)

    now = datetime.now(JST)
    start_day = datetime(now.year, now.month, now.day, tzinfo=JST)

    for tvg_id, name in channels:
        ch = ET.SubElement(root, "channel", {"id": tvg_id})
        ET.SubElement(ch, "display-name").text = name

        for d in range(3):
            day = start_day + timedelta(days=d)
            for h in (0, 6, 12, 18):
                start = day + timedelta(hours=h)
                stop = start + timedelta(hours=6)
                p = ET.SubElement(
                    root,
                    "programme",
                    {
                        "start": xmltv_time(start),
                        "stop": xmltv_time(stop),
                        "channel": tvg_id,
                    },
                )
                ET.SubElement(p, "title", {"lang": "ja"}).text = TITLE
                ET.SubElement(p, "desc", {"lang": "ja"}).text = f"{DESC}\n📺 {name}"
                ET.SubElement(p, "category", {"lang": "ja"}).text = CATEGORY

    ET.indent(root, space="  ")
    tree.write(EPG, encoding="utf-8", xml_declaration=True)
    print(f"KICK EPG: {len(channels)} channels / {len(channels) * 12} programmes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
