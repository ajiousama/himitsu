"""Keep actual programme metadata for the selected Coffee channels for six days."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
import copy
import xml.etree.ElementTree as ET

JST = timezone(timedelta(hours=9))
GCH = ("jra.gch.hq", "jra.gch.lq")
IDS = GCH + ("フジテレビONE_jp", "フジテレビTWO_jp", "ヌーヴェルパラダイス_jp", "Pigoo_jp")
MARKERS = ("番組詳細EPG未取得", "実EPG未対応", "番組表取得待ち", "実レースEPG取得失敗", "データ取得準備中", "番組表を取得できなかった", "番組情報を取得できていません")

def time_of(value):
    try:
        return datetime.strptime(value.strip(), "%Y%m%d%H%M%S %z").astimezone(JST)
    except (AttributeError, ValueError):
        try:
            return datetime.strptime(value.strip(), "%Y%m%d%H%M%S").replace(tzinfo=JST)
        except (AttributeError, ValueError):
            return None

def real(p):
    title = (p.findtext("title") or "").strip()
    desc = p.findtext("desc") or ""
    return bool(title) and not any(m in title + desc for m in MARKERS)

def load(path):
    try:
        return ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return None

def recover_pigoo_history(now=None):
    """Recover real Pigoo programme metadata from verified November EPG snapshots."""
    import subprocess
    now = now or datetime.now(JST)
    archive = ET.Element("tv")
    if now >= datetime(2026, 11, 30, tzinfo=JST):
        return archive
    for ref in (
        "f34cd772585f274ceb727e3d318fc1543791f3e0",
        "90b37d3f52682483a896b6a6dd30d528de6c1823",
    ):
        try:
            raw = subprocess.check_output(["git", "show", ref + ":guides.xml"], stderr=subprocess.DEVNULL)
            source = ET.fromstring(raw)
        except (OSError, subprocess.CalledProcessError, ET.ParseError):
            print("Pigoo historical snapshot unavailable:", ref[:7])
            continue
        count = 0
        for p in source.findall("programme"):
            if p.get("channel") != "Pigoo_jp" or not real(p):
                continue
            a, b = time_of(p.get("start")), time_of(p.get("stop"))
            if a and b and a < b and b > now - timedelta(days=6) and b <= now.replace(hour=0, minute=0, second=0, microsecond=0):
                archive.append(copy.deepcopy(p))
                count += 1
        print("Pigoo historical snapshot:", ref[:7], "eligible programmes:", count)
    return archive

def merge_history(root, previous=None, now=None):
    now = now or datetime.now(JST)
    cutoff = now - timedelta(days=6)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    ids = {ch.get("id") for ch in root.findall("channel")}
    sources = [root] + ([previous] if previous is not None else [])
    if "Pigoo_jp" in ids and now.date() >= datetime(2026, 11, 26, tzinfo=JST).date():
        sources.append(recover_pigoo_history(now))
    gathered = {cid: [] for cid in IDS}
    for source in sources:
        for p in source.findall("programme"):
            cid = p.get("channel")
            if cid not in gathered or not real(p):
                continue
            a,b = time_of(p.get("start")),time_of(p.get("stop"))
            if a and b and a < b and b > cutoff and b <= midnight:
                gathered[cid].append((a,b,p))
    # The current guide wins. Retain only non-overlapping real historical slots.
    def dedup(items):
        selected = []
        for a,b,p in items:
            if not any(a < y and b > x for x,y,_ in selected):
                selected.append((a,b,p))
        return sorted(selected,key=lambda x:x[0])
    shared = dedup(gathered[GCH[0]] + gathered[GCH[1]])
    for p in list(root.findall("programme")):
        if p.get("channel") in IDS:
            a,b = time_of(p.get("start")),time_of(p.get("stop"))
            if b and b <= midnight:
                root.remove(p)
    counts = {}
    for cid in IDS:
        if cid not in ids:
            continue
        items = shared if cid in GCH else dedup(gathered[cid])
        # Do not overlap programmes that cross midnight.
        occupied = [(time_of(p.get("start")), time_of(p.get("stop"))) for p in root.findall("programme") if p.get("channel")==cid]
        count = 0
        for a,b,p in items:
            if any(x and y and a < y and b > x for x,y in occupied):
                continue
            q = copy.deepcopy(p)
            q.set("channel",cid)
            root.append(q)
            count += 1
        counts[cid]=count
    return counts

def main():
    import sys
    target = Path(sys.argv[1] if len(sys.argv)>1 else "guides.xml")
    previous = load(sys.argv[2]) if len(sys.argv)>2 else None
    tree = ET.parse(target)
    counts = merge_history(tree.getroot(), previous)
    ET.indent(tree,space="  ")
    tree.write(target,encoding="utf-8",xml_declaration=True)
    print("Coffee actual historical EPG:", counts)

if __name__ == "__main__":
    main()
