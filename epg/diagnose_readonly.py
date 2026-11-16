#!/usr/bin/env python3
"""Read-only FreeWiFi/XMLTV diagnostic snapshot. Never changes source files."""
import collections
import datetime
import hashlib
import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

PLAYLIST = Path("freewifi")
GUIDE = Path("guides.xml")
OUT = Path("epg_diagnostics")
OUT.mkdir(exist_ok=True)
def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    entries = []
    for line in PLAYLIST.read_text(encoding="utf-8-sig").splitlines():
        if not line.startswith("#EXTINF:"):
            continue
        def attr(k):
            m = re.search(r'\b'+re.escape(k)+r'="([^"]*)"',line)
            return m.group(1) if m else ""
        entries.append({"id":attr("tvg-id"),"group":attr("group-title"),"name":line.rsplit(",",1)[-1]})
    root=ET.parse(GUIDE).getroot()
    channels=collections.Counter(c.get("id","") for c in root.findall("channel"))
    programmes=collections.Counter(p.get("channel","") for p in root.findall("programme"))
    by_id={}
    for entry in entries:
        cid=entry["id"]
        if cid not in by_id:
            by_id[cid]={**entry,"channel_count":channels[cid],"programme_count":programmes[cid]}
    missing=[v for v in by_id.values() if not v["id"] or v["channel_count"]!=1 or v["programme_count"]==0]
    result={"timestamp_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
      "freewifi_sha256":sha(PLAYLIST),"guides_sha256":sha(GUIDE),
      "playlist_entries":len(entries),"unique_ids":len(by_id),
      "xml_channels":sum(channels.values()),"xml_programmes":sum(programmes.values()),
      "missing_or_invalid":missing,"channels":sorted(by_id.values(),key=lambda v:v["id"])}
    dest=OUT/"latest.json"
    dest.write_text(json.dumps(result,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"DIAGNOSTIC: entries={len(entries)} missing={len(missing)} file={dest}")
    for v in missing[:50]:
        print("MISSING:",v["id"],v["name"],"channels=",v["channel_count"],"programmes=",v["programme_count"])
    return 0
if __name__=="__main__":
    raise SystemExit(main())
