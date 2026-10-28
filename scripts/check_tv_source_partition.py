#!/usr/bin/env python3
"""Guard the 2026-10-28 split: newblog only in yovi; FreeWiFi retains proven alternatives."""
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
REQUIRED_SHINORI = 66
REQUIRED_FREEWIFI_YOITV = 49
REQUIRED_YOVI_YOITV = 75
REQUIRED_NEWBLOG = 101
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
                  or "0i4neux01.charandom.blog/stream/jp/" in url)]
        if leaked:
            raise SystemExit(f"{label}: newblog sources returned: {len(leaked)}")
    live = [(cid,tag,url) for cid,tag,url in yovi if "（newblog系）" in tag]
    if len(live) != REQUIRED_NEWBLOG or len({url for _,_,url in live}) != REQUIRED_NEWBLOG:
        raise SystemExit(f"yovi: expected 101 unique newblog channels, found {len(live)}")
    yovi_text = (ROOT / "yovi").read_text(encoding="utf-8-sig")
    if yovi_text.count("# === NEWBLOG_VOD_START ===") != 1 or yovi_text.count("# === NEWBLOG_VOD_END ===") != 1:
        raise SystemExit("yovi: managed newblog VOD block missing")
    # The 14-day VOD shelf may legitimately become empty when recordings expire.
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
    print("Source partition OK: FreeWiFi no newblog; yovi 101 newblog + VOD; 5002, sinori and YoiTV preserved")


if __name__ == "__main__":
    check()
