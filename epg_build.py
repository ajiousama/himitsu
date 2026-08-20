from __future__ import annotations

import gzip
import json
import re
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

PLAYLISTS = [
    Path("freewifi"),
    Path("other_live.m3u"),
]
OUT_XML = Path("guides.xml")
REPORT = Path("epg_coverage.txt")

SOURCES = [
    ("japanterebi", "https://animenosekai.github.io/japanterebi-xmltv/guide.xml"),
    ("jcom", "https://raw.githubusercontent.com/dbghelp/JCOM-TV-EPG/refs/heads/main/jcom.xml"),
    ("sky", "https://raw.githubusercontent.com/dbghelp/SKY-PerfecTV-EPG/refs/heads/main/perfectv.xml"),
    ("tver", "https://raw.githubusercontent.com/dbghelp/TVer-EPG/refs/heads/main/tver.xml"),
    ("abema", "https://raw.githubusercontent.com/dbghelp/Abema-TV-EPG/refs/heads/main/abema.xml"),
    ("epgshare_jp1", "https://epgshare01.online/epgshare01/epg_ripper_JP1.xml.gz"),
    ("epgshare_jp2", "https://epgshare01.online/epgshare01/epg_ripper_JP2.xml.gz"),
]

# 愛媛CATV 公式「地域情報チャンネル番組表」JSON。
# 愛南たうんチャンネル(52350)は松山側TS-401で配信URL未確認のため対象外。
# 公式ページの表示順:
#   52344 = たうんプレミアム (111ch)
#   52330 = イベントセレクション (123ch)
#   52329 = イベントプレミアム (122ch)
#   52345 = たうんNews24
#   115   = 防災チャンネル (112ch)
ECATV_CHANNELS = {
    "ecatv.town_premium": ("たうんプレミアム", "52344"),
    "ecatv.event_selection": ("イベントセレクション", "52330"),
    "ecatv.event_premium": ("イベントプレミアム", "52329"),
    "ecatv.town_news24": ("たうんNews24", "52345"),
    "ecatv.bousai": ("えひめ・防災チャンネル", "115"),
}
ECATV_JSON_BASE = "https://www.e-catv.ne.jp/epg/json"

EXPLICIT = {
    "tver_ntv": ["ntv"], "tver_ex": ["ex"], "tver_tbs": ["tbs"], "tver_tx": ["tx"], "tver_cx": ["cx"],
    "日本テレビ_jp": ["JOAXDTV.jp", "jcom_2_1040_32738"],
    "TBS_jp": ["JORXDTV.jp", "jcom_2_1048_32739"],
    "フジテレビ_jp": ["JOCXDTV.jp", "jcom_2_1056_32740"],
    "テレビ朝日_jp": ["JOEXDTV.jp", "jcom_2_1064_32741"],
    "テレビ東京_jp": ["JOTXDTV.jp", "jcom_2_1072_32742"],
    "TBS-NEWS_jp": ["CS351", "Ch.572", "TBSNewsCS.jp", "TBSNews.jp"],
    "グリーンチャンネル_jp": ["BS234", "Ch.688", "GreenChannel.jp"],
    "グリーンチャンネル2_jp": ["Ch.689", "GreenChannel2.jp"],
    "フジテレビONE_jp": ["FujiTVONE.jp", "CS307"],
    "フジテレビTWO_jp": ["FujiTVTWO.jp", "CS308"],
    "フジテレビNEXT_jp": ["FujiTVNEXT.jp", "CS309"],
    "ヒストリーチャンネル_jp": ["HistoryChannel.jp", "History.jp"],
    "rch_102": ["QVC.jp", "CS161", "Ch.525"],

    # 0-programme候補を誤選択していた6局は、実番組を持つIDへ固定。
    "スペースシャワーTV_jp": ["SpaceShowerTV.jp"],
    "WOWOWプラス_jp": ["WOWOWPlus.jp"],
    "カートゥーン-ネットワーク_jp": ["CartoonNetwork.jp"],
    "ホームドラマチャンネル_jp": ["HomeDramaChannel.jp"],
    "チャンネル銀河_jp": ["ChannelGinga.jp"],
    "日テレプラス_jp": ["NipponTVPlus.jp", "NittelePlus.jp"],
}

SOURCE_PRIORITY = {name: i for i, (name, _) in enumerate(SOURCES)}
JST = timezone(timedelta(hours=9))


def fetch_bytes(url):
    req = urllib.request.Request(url, headers={"User-Agent": "FreeWiFi-EPG/1.4"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


def fetch_xml(url):
    data = fetch_bytes(url)
    if url.endswith(".gz"):
        data = gzip.decompress(data)
    return ET.fromstring(data)


def fetch_json(url):
    return json.loads(fetch_bytes(url).decode("utf-8-sig"))


def norm(s):
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = s.replace("_jp", "").replace(".jp", "")
    s = re.sub(r"\([^)]*\)|（[^）]*）", "", s)
    for a, b in [("テレビジョン", "テレビ"), ("放送", ""), ("チャンネル", ""), ("channel", ""), ("hd", ""), ("4k", "")]:
        s = s.replace(a, b)
    s = re.sub(r"[\s\-‐‑‒–—―・･:：/／!！?？☆★♪#＃+＋]+", "", s)
    return s


def aliases(s):
    n = norm(s)
    out = {n}
    repl = [("フジテレビ", "フジ"), ("テレビ朝日", "テレ朝"), ("日本テレビ", "日テレ"), ("スペースシャワーtv", "スペシャ"), ("ヒストリー", "history")]
    for a, b in repl:
        if a in n:
            out.add(n.replace(a, b))
        if b in n:
            out.add(n.replace(b, a))
    return {x for x in out if x}


def parse_playlists():
    out = {}
    for path in PLAYLISTS:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        for line in text.splitlines():
            if not line.startswith("#EXTINF:"):
                continue
            m = re.search(r'tvg-id="([^"]+)"', line)
            if not m:
                continue
            tid = m.group(1).strip()
            name = line.rsplit(",", 1)[-1].strip() if "," in line else tid
            name = re.sub(r"\([^)]*\)$", "", name).strip()
            gm = re.search(r'group-title="([^"]*)"', line)
            group = gm.group(1).strip() if gm else ""
            out.setdefault(tid, (name, group))
    return out


def clone(el):
    return ET.fromstring(ET.tostring(el, encoding="utf-8"))


def xmltv_time(dt):
    return dt.strftime("%Y%m%d%H%M%S +0900")


def parse_ecatv_datetime(item):
    sdate = str(item.get("sdate") or "").strip()
    stime = str(item.get("stime") or "").strip()
    if not (re.fullmatch(r"\d{8}", sdate) and re.fullmatch(r"\d{6}", stime)):
        return None
    try:
        return datetime.strptime(sdate + stime, "%Y%m%d%H%M%S").replace(tzinfo=JST)
    except ValueError:
        return None


def load_ecatv_epg():
    """Return {target_id: [(start, stop, title), ...]}, errors."""
    result = {}
    errors = []

    for target_id, (display_name, source_id) in ECATV_CHANNELS.items():
        url = f"{ECATV_JSON_BASE}/{source_id}.json"
        try:
            data = fetch_json(url)
            items = []

            if isinstance(data, dict):
                groups = data.values()
            elif isinstance(data, list):
                groups = [data]
            else:
                raise ValueError(f"unexpected JSON root: {type(data).__name__}")

            for group in groups:
                if not isinstance(group, list):
                    continue
                for item in group:
                    if not isinstance(item, dict):
                        continue
                    start = parse_ecatv_datetime(item)
                    title = str(item.get("title") or "").strip()
                    if start and title:
                        items.append((start, title))

            dedup = {}
            for start, title in items:
                dedup[(start, title)] = (start, title)
            items = sorted(dedup.values(), key=lambda x: x[0])

            programmes = []
            for i, (start, title) in enumerate(items):
                if i + 1 < len(items):
                    stop = items[i + 1][0]
                else:
                    stop = start + timedelta(hours=1)

                if stop <= start or stop - start > timedelta(hours=8):
                    stop = start + timedelta(hours=1)
                programmes.append((start, stop, title))

            if not programmes:
                raise ValueError("no programmes parsed")

            result[target_id] = (display_name, programmes)
        except Exception as e:
            errors.append(f"ecatv/{source_id}: {type(e).__name__}: {e}")

    return result, errors


def add_ecatv_channel(out_root, target_id, display_name, programmes):
    ch = ET.SubElement(out_root, "channel", {"id": target_id})
    ET.SubElement(ch, "display-name").text = display_name

    for start, stop, title in programmes:
        p = ET.SubElement(out_root, "programme", {
            "start": xmltv_time(start),
            "stop": xmltv_time(stop),
            "channel": target_id,
        })
        ET.SubElement(p, "title", {"lang": "ja"}).text = title
        ET.SubElement(p, "category", {"lang": "ja"}).text = "地域情報"


def add_fallback(out_root, target_id, target_name, target_group=""):
    ch = ET.SubElement(out_root, "channel", {"id": target_id})
    ET.SubElement(ch, "display-name").text = target_name

    is_youtube_live = target_id.startswith("youtube.")
    group_norm = unicodedata.normalize("NFKC", target_group or "").upper()
    is_24h_name = ("CATV" in group_norm) or ("ABEMA" in group_norm)

    if is_youtube_live:
        title = "📡✨ ただいまYouTubeよりライブカメラ中継中 ✨📡"
        desc = f"🎥 LIVE CAMERA ON AIR 🎥\n📺 YouTubeからライブ映像を中継しています。\n📍 {target_name}"
        category = "ライブカメラ"
    elif is_24h_name:
        title = f"24H＋{target_name}"
        desc = "実EPG未対応のため、24時間枠でチャンネル名を表示しています。"
        category = "24H"
    else:
        title = target_name
        desc = "番組詳細EPG未取得のため、チャンネル名を表示しています。"
        category = "その他"

    now = datetime.now(JST)
    start_day = datetime(now.year, now.month, now.day, tzinfo=JST)
    for d in range(3):
        day = start_day + timedelta(days=d)
        for h in (0, 6, 12, 18):
            st = day + timedelta(hours=h)
            en = st + timedelta(hours=6)
            p = ET.SubElement(out_root, "programme", {
                "start": xmltv_time(st),
                "stop": xmltv_time(en),
                "channel": target_id,
            })
            ET.SubElement(p, "title", {"lang": "ja"}).text = title
            ET.SubElement(p, "desc", {"lang": "ja"}).text = desc
            ET.SubElement(p, "category", {"lang": "ja"}).text = category


def main():
    wanted = parse_playlists()
    loaded, errors = [], []

    ecatv_epg, ecatv_errors = load_ecatv_epg()
    errors.extend(ecatv_errors)

    for source_name, url in SOURCES:
        try:
            root = fetch_xml(url)
            by_id, by_name, programmes = {}, defaultdict(list), defaultdict(list)
            for ch in root.findall("channel"):
                cid = ch.get("id")
                if not cid:
                    continue
                by_id[cid] = ch
                vals = [cid] + [x.text.strip() for x in ch.findall("display-name") if x.text and x.text.strip()]
                for val in vals:
                    for a in aliases(val):
                        by_name[a].append(cid)
            for p in root.findall("programme"):
                if p.get("channel"):
                    programmes[p.get("channel")].append(p)
            loaded.append((source_name, by_id, by_name, programmes))
        except Exception as e:
            errors.append(f"{source_name}: {type(e).__name__}: {e}")

    id_index, name_index = defaultdict(list), defaultdict(list)
    source_map = {x[0]: x for x in loaded}
    for source_name, by_id, by_name, programmes in loaded:
        for cid in by_id:
            id_index[cid].append((SOURCE_PRIORITY[source_name], source_name, cid))
        for n, ids in by_name.items():
            for cid in ids:
                name_index[n].append((SOURCE_PRIORITY[source_name], source_name, cid))

    out_root = ET.Element("tv", {"generator-info-name": "FreeWiFi merged EPG", "generator-info-url": "https://github.com/ajiousama/himitsu"})
    coverage, missing = [], []
    matched = 0
    fallback = 0

    for target_id, (target_name, target_group) in wanted.items():
        if target_id in ecatv_epg:
            display_name, programmes = ecatv_epg[target_id]
            add_ecatv_channel(out_root, target_id, display_name, programmes)
            matched += 1
            coverage.append(f"OK\t{target_id}\t{target_name}\tecatv\t{ECATV_CHANNELS[target_id][1]}\t{len(programmes)} programmes")
            continue

        candidates = []
        for sid in EXPLICIT.get(target_id, []):
            candidates += id_index.get(sid, [])
        candidates += id_index.get(target_id, [])
        for val in (target_name, target_id):
            for a in aliases(val):
                candidates += name_index.get(a, [])

        uniq, seen = [], set()
        for item in sorted(candidates):
            key = (item[1], item[2])
            if key not in seen:
                seen.add(key)
                uniq.append(item)

        usable = []
        for item in uniq:
            _, sn, sid = item
            pc = len(source_map[sn][3].get(sid, []))
            usable.append((0 if pc else 1, item[0], -pc, sn, sid))
        usable.sort()

        if not usable:
            add_fallback(out_root, target_id, target_name, target_group)
            fallback += 1
            missing.append((target_id, target_name))
            coverage.append(f"FALLBACK\t{target_id}\t{target_name}\t{target_group}\t12 programmes")
            continue

        _, _, _, source_name, source_id = usable[0]
        _, by_id, _, programmes = source_map[source_name]
        src_ch = by_id[source_id]
        ch = clone(src_ch)
        ch.set("id", target_id)
        out_root.append(ch)

        seenp, added = set(), 0
        for p in programmes.get(source_id, []):
            q = clone(p)
            q.set("channel", target_id)
            key = (q.get("start"), q.get("stop"), (q.findtext("title") or "").strip())
            if key in seenp:
                continue
            seenp.add(key)
            out_root.append(q)
            added += 1
        matched += 1
        coverage.append(f"OK\t{target_id}\t{target_name}\t{source_name}\t{source_id}\t{added} programmes")

    ET.indent(out_root, space="  ")
    OUT_XML.write_bytes(ET.tostring(out_root, encoding="utf-8", xml_declaration=True))
    report = [
        "FreeWiFi merged EPG coverage",
        f"wanted={len(wanted)}",
        f"matched_real={matched}",
        f"fallback={fallback}",
        f"unmatched_real={len(missing)}",
        f"covered_total={matched + fallback}",
        f"output_bytes={OUT_XML.stat().st_size}",
        "",
        "[source errors]",
        *(errors or ["none"]),
        "",
        "[coverage]",
        *coverage,
    ]
    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"real={matched}/{len(wanted)} fallback={fallback} covered={matched + fallback}/{len(wanted)} bytes={OUT_XML.stat().st_size:,}")


if __name__ == "__main__":
    main()
