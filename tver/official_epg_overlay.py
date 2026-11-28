"""Apply the latest official TVer schedule to the five terrestrial IDs only."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import os
import xml.etree.ElementTree as ET

IDS = ("ntv", "ex", "tbs", "tx", "cx")

def apply(source, destination):
    official = ET.parse(source).getroot()
    tree = ET.parse(destination)
    root = tree.getroot()
    now = datetime.now(timezone.utc)
    rows = {}
    for cid in IDS:
        entries = official.findall(f"programme[@channel='{cid}']")
        if not entries or not any(
            datetime.strptime(p.attrib["stop"], "%Y%m%d%H%M%S %z") > now
            for p in entries
        ):
            raise ValueError(f"TVer official schedule missing current/future rows: {cid}")
        rows[cid] = entries
    managed = {"tver_" + cid for cid in IDS}
    existing = {}
    for ch in root.findall("channel"):
        if ch.get("id") in managed:
            existing.setdefault(ch.get("id"), ch)
    for node in list(root):
        if node.tag == "channel" and node.get("id") in managed:
            root.remove(node)
        elif node.tag == "programme" and node.get("channel") in managed:
            root.remove(node)
    for cid in IDS:
        target = "tver_" + cid
        ch = existing.get(target)
        if ch is None:
            src = official.find(f"channel[@id='{cid}']")
            if src is None:
                raise ValueError(f"missing channel {cid}")
            ch = deepcopy(src)
            ch.set("id", target)
        root.insert(0, ch)
        for p in rows[cid]:
            q = deepcopy(p)
            q.set("channel", target)
            root.append(q)
    for cid in IDS:
        target = "tver_" + cid
        assert len(root.findall(f"channel[@id='{target}']")) == 1
        assert len(root.findall(f"programme[@channel='{target}']")) == len(rows[cid])
    tmp = destination.with_suffix(".tver.tmp")
    ET.indent(tree, space="  ")
    tree.write(tmp, encoding="utf-8", xml_declaration=True)
    ET.parse(tmp)
    os.replace(tmp, destination)
    print("TVer official final overlay:", {cid:len(rows[cid]) for cid in IDS})

if __name__ == "__main__":
    apply(Path("tver/official_schedule.xml"), Path("guides.xml"))
