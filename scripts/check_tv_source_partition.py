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
    trial_begin = "# === YOVI_HARUKA_TRIAL_BEGIN ==="
    trial_end = "# === YOVI_HARUKA_TRIAL_END ==="
    if yovi_text.count(trial_begin) != yovi_text.count(trial_end) or yovi_text.count(trial_begin) > 1:
        raise SystemExit("yovi: invalid HARUKA trial markers")
    if trial_begin in yovi_text:
        before, remainder = yovi_text.split(trial_begin, 1)
        trial, after = remainder.split(trial_end, 1)
        if ":9394/stream/" in before or ":9394/stream/" in after:
            raise SystemExit("yovi: HARUKA stream outside dedicated trial block")
        allowed = {4, 5, 7, 8, 12, 17, 18, 20, 21, 22, 28, 116, 35, 36, 37, 38, 39, 40, 41, 44}
        for line in trial.splitlines():
            if line.startswith("#EXTINF:") and 'group-title="HARUKA試験 ' not in line:
                raise SystemExit("yovi: non-trial channel inside HARUKA block")
            if ":9394/stream/" in line:
                match = re.fullmatch(r"http://[A-Za-z0-9.:-]+:9394/stream/(\d+)\.m3u8", line)
                if not match or int(match.group(1)) not in allowed:
                    raise SystemExit("yovi: unapproved HARUKA URL in trial block")
        if 'group-title="HARUKA試験 ' in before or 'group-title="HARUKA試験 ' in after:
            raise SystemExit("yovi: HARUKA trial group outside managed block")
    elif ":9394/stream/" in yovi_text:
        raise SystemExit("yovi: obsolete HARUKA URLs outside trial")
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
