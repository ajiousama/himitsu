#!/usr/bin/env python3
"""Verify retired blogs stay absent while approved YoiTV/5002/Shinori remain."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
REQUIRED_SHINORI = 66
REQUIRED_FREEWIFI_YOITV = 49
REQUIRED_YOVI_YOITV = 75
ALLOWED_FREEWIFI_CS_YOITV = frozenset({
    "Dlife(ディーライフ)_jp","FIGHTING-TV-サムライ_jp",
    "MUSIC-ON!-TV(エムオン!)_jp","TBSチャンネル1_jp","TBSチャンネル2_jp",
    "アニメシアター(AT-X)_jp","ザ・シネマ_jp","スポーツライブ+_jp",
    "テレ朝チャンネル1_jp","テレ朝チャンネル2_jp",
    "フジテレビONE_jp","フジテレビTWO_jp","ミステリーチャンネル_jp",
    "メ～テレNEXT_jp","鉄道チャンネル_jp","日テレNEWS24_jp","日テレプラス_jp",
})


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
        yoitv_rows = [(cid, tag, url) for cid,tag,url in rows if "/tv/yoitv.php" in url]
        if len(yoitv_rows) != REQUIRED_FREEWIFI_YOITV or len({url for _,_,url in yoitv_rows}) != REQUIRED_FREEWIFI_YOITV:
            raise SystemExit(f"{label}: expected 49 unique YoiTV sources, got {len(yoitv_rows)}")
        for group, required in (("地上波 YoiTV", 14), ("BS YoiTV", 18)):
            expected = [(cid, url) for cid,tag,url in yovi if f'group-title="{group}"' in tag]
            actual = [(cid, url) for cid,tag,url in rows if f'group-title="{group}"' in tag]
            if len(expected) != required or len(actual) != required or set(actual) != set(expected):
                raise SystemExit(f"{label}: {group} mismatch (expected {required}, got {len(actual)})")
        cs_rows = [(cid, url) for cid,tag,url in rows if 'group-title="CS YoiTV"' in tag]
        if len(cs_rows) != 17 or {cid for cid,_ in cs_rows} != ALLOWED_FREEWIFI_CS_YOITV:
            raise SystemExit(f"{label}: expected 17 approved YoiTV CS, got {len(cs_rows)}")
    if sum("/tv/yoitv.php" in url for _,_,url in yovi) < REQUIRED_YOVI_YOITV:
        raise SystemExit("yovi: YoiTV minimum 75 violated")
    for label, rows,minimum in (("freewifi",free,49),("tv",tv,48),("yovi",yovi,18)):
        urls = [url for _,_,url in rows if ":5002/" in url]
        if len(set(urls)) < minimum:
            raise SystemExit(f"{label}: protected 5002 URLs missing")
    for name in ("グリーンチャンネル MAIN HQ","グリーンチャンネル MAIN LQ","グリーンチャンネル (5002直)"):
        if not any(tag.rsplit(",",1)[-1]==name for _,tag,_ in free):
            raise SystemExit(f"freewifi: required GCH source missing: {name}")
    print("Source partition OK: retired HARU/newblog absent; 5002, sinori, YoiTV preserved")


if __name__ == "__main__":
    check()
