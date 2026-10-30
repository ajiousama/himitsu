#!/usr/bin/env python3
"""Verify retired blogs and YoiTV stay out of FreeWiFi while backups stay in yovi."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
REQUIRED_SHINORI = 66
REQUIRED_FREEWIFI_YOITV = 0
REQUIRED_YOVI_YOITV = 75


def entries(path):
    lines = (ROOT / path).read_text(encoding="utf-8-sig").splitlines()
    result = []
    for i, line in enumerate(lines):
        if not line.startswith("#EXTINF:"):
            continue
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        uri = lines[j].strip() if j < len(lines) else ""
        m = re.search(r'tvg-id="([^"]+)"', line)
        result.append((m.group(1) if m else "",line,uri))
    return result


def check():
    free = entries("freewifi")
    tv = entries("tv/playlist.m3u")
    yovi = entries("yovi")
    rch = entries("rakuten/playlist.m3u")
    for label, rows in (("freewifi",free),("tv",tv),("rakuten",rch)):
        leaked = [cid for cid,tag,url in rows if ("（newblog系）" in tag
                  or 'tvg-id="newblog.vod.' in tag
                  or "0i4neux01.charandom.blog/stream/jp/" in url
                       or "haru-clip?src=" in url or 'tvg-id="haru.vod.' in tag)]
        if leaked:
            raise SystemExit(f"{label}: newblog sources returned: {len(leaked)}")
    for label, rows in (("freewifi",free),("tv",tv),("yovi",yovi),("rakuten",rch)):
        retired = [(cid,url) for cid,tag,url in rows
                   if ("（newblog系）" in tag or 'tvg-id="newblog.vod.' in tag
                       or "haru.charandom.blog/stream/jp/" in url
                       or "0i4neux01.charandom.blog/stream/jp/" in url)]
        if retired:
            raise SystemExit(f"{label}: retired blog returned: {len(retired)}")
    yovi_text = (ROOT / "yovi").read_text(encoding="utf-8-sig")
    if ":9394/stream/" in yovi_text:
        raise SystemExit("yovi: obsolete HARUKA URLs reappeared")
    if any("haru.charandom.blog" in x for x in yovi_text.splitlines() if x.startswith("#EXTM3U")):
        raise SystemExit("yovi: stale HARU EPG playlist header returned")
    if "# === NEWBLOG_VOD_START ===" in yovi_text or "# === NEWBLOG_VOD_END ===" in yovi_text:
        raise SystemExit("yovi: retired newblog VOD markers returned")
    if any("ri.shinori.my.id/" in url for _,_,url in yovi):
        raise SystemExit("yovi: Shinori backup moved back")
    for label,rows in (("freewifi",free),("tv",tv)):
        ids = [cid for cid,_,url in rows if "ri.shinori.my.id/" in url]
        if len(ids) != REQUIRED_SHINORI or len(ids) != len(set(ids)):
            raise SystemExit(f"{label}: Shinori 66 unique sources required")
        yoitv_rows = [(cid, tag, url) for cid,tag,url in rows
                      if "/tv/yoitv.php" in url.casefold() or "yoitv" in tag.casefold()]
        if len(yoitv_rows) != REQUIRED_FREEWIFI_YOITV:
            raise SystemExit(f"{label}: retired YoiTV sources reappeared: {len(yoitv_rows)}")
    if sum("/tv/yoitv.php" in url for _,_,url in yovi) < REQUIRED_YOVI_YOITV:
        raise SystemExit("yovi: YoiTV minimum 75 violated")
    for label, rows,minimum in (("freewifi",free,49),("tv",tv,48),("yovi",yovi,18)):
        urls = [url for _,_,url in rows if ":5002/" in url]
        if len(set(urls)) < minimum:
            raise SystemExit(f"{label}: protected 5002 URLs missing")
    for name in ("グリーンチャンネル MAIN HQ","グリーンチャンネル MAIN LQ","グリーンチャンネル (5002直)"):
        if not any(tag.rsplit(",",1)[-1]==name for _,tag,_ in free):
            raise SystemExit(f"freewifi: required GCH source missing: {name}")
    print("Source partition OK: retired HARU/newblog/YoiTV absent from FreeWiFi; 5002 and sinori preserved; yovi unchanged")


if __name__ == "__main__":
    check()
