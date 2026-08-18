from __future__ import annotations

import gzip
import io
import re
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

FREEWIFI = Path("freewifi")
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

# FreeWiFi のIDと外部EPGのIDが明確に違うもの。
# 局名自動照合で拾えないものをここで優先的に合わせる。
EXPLICIT = {
    "tver_ntv": ["ntv"],
    "tver_ex": ["ex"],
    "tver_tbs": ["tbs"],
    "tver_tx": ["tx"],
    "tver_cx": ["cx"],
    "日本テレビ_jp": ["JOAXDTV.jp", "jcom_2_1040_32738"],
    "TBS_jp": ["JORXDTV.jp", "jcom_2_1048_32739"],
    "フジテレビ_jp": ["JOCXDTV.jp", "jcom_2_1056_32740"],
    "テレビ朝日_jp": ["JOEXDTV.jp", "jcom_2_1064_32741"],
    "テレビ東京_jp": ["JOTXDTV.jp", "jcom_2_1072_32742"],
    "TBS-NEWS_jp": ["CS351", "Ch.572", "TBSNews.jp"],
    "グリーンチャンネル_jp": ["BS234", "Ch.688", "GreenChannel.jp"],
    "グリーンチャンネル2_jp": ["Ch.689", "GreenChannel2.jp"],
}

SOURCE_PRIORITY = {
    "japanterebi": 0,
    "jcom": 1,
    "sky": 2,
    "tver": 3,
    "abema": 4,
    "epgshare_jp1": 5,
    "epgshare_jp2": 6,
}


def fetch_bytes(url: str) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "FreeWiFi-EPG/1.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


def fetch_xml(url: str) -> ET.Element:
    data = fetch_bytes(url)
    if url.endswith(".gz"):
        data = gzip.decompress(data)
    return ET.fromstring(data)


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = s.replace("_jp", "").replace(".jp", "")
    s = re.sub(r"\([^)]*\)", "", s)
    s = re.sub(r"（[^）]*）", "", s)
    s = s.replace("テレビジョン", "テレビ")
    s = s.replace("放送", "")
    s = s.replace("hd", "")
    s = s.replace("４ｋ", "").replace("4k", "")
    s = re.sub(r"[\s\-‐‑‒–—―・･:：/／!！?？☆★♪#＃]+", "", s)
    return s


def parse_freewifi():
    text = FREEWIFI.read_text(encoding="utf-8-sig", errors="replace")
    entries = []
    for line in text.splitlines():
        if not line.startswith("#EXTINF:"):
            continue
        m_id = re.search(r'tvg-id="([^"]+)"', line)
        if not m_id:
            continue
        tvg_id = m_id.group(1).strip()
        name = line.rsplit(",", 1)[-1].strip() if "," in line else tvg_id
        # ソース名などの括弧を除去した表示名も保持
        clean_name = re.sub(r"\([^)]*\)$", "", name).strip()
        entries.append((tvg_id, clean_name))
    # 同じ tvg-id は1回だけ
    out = {}
    for tvg_id, name in entries:
        out.setdefault(tvg_id, name)
    return out


def source_channels(root: ET.Element):
    by_id = {}
    by_name = defaultdict(list)
    for ch in root.findall("channel"):
        cid = ch.get("id")
        if not cid:
            continue
        names = [x.text.strip() for x in ch.findall("display-name") if x.text and x.text.strip()]
        by_id[cid] = ch
        for name in names:
            by_name[norm(name)].append(cid)
    return by_id, by_name


def clone(el: ET.Element) -> ET.Element:
    return ET.fromstring(ET.tostring(el, encoding="utf-8"))


def main():
    wanted = parse_freewifi()
    print(f"FreeWiFi tvg-id: {len(wanted)}")

    loaded = []
    errors = []
    for source_name, url in SOURCES:
        try:
            root = fetch_xml(url)
            by_id, by_name = source_channels(root)
            programmes = defaultdict(list)
            for p in root.findall("programme"):
                cid = p.get("channel")
                if cid:
                    programmes[cid].append(p)
            loaded.append((source_name, by_id, by_name, programmes))
            print(f"{source_name}: {len(by_id)} channels")
        except Exception as e:
            errors.append(f"{source_name}: {type(e).__name__}: {e}")
            print(f"WARN {errors[-1]}")

    # 全ソースID索引
    id_index = defaultdict(list)
    name_index = defaultdict(list)
    for source_name, by_id, by_name, programmes in loaded:
        for cid in by_id:
            id_index[cid].append((SOURCE_PRIORITY[source_name], source_name, cid))
        for n, ids in by_name.items():
            for cid in ids:
                name_index[n].append((SOURCE_PRIORITY[source_name], source_name, cid))

    out_root = ET.Element("tv", {
        "generator-info-name": "FreeWiFi merged EPG",
        "generator-info-url": "https://github.com/ajiousama/himitsu",
    })

    coverage = []
    missing = []
    matched_count = 0

    for target_id, target_name in wanted.items():
        candidates = []

        # 1) 明示ID
        for source_id in EXPLICIT.get(target_id, []):
            candidates.extend(id_index.get(source_id, []))

        # 2) target_id 自体が外部IDと一致
        candidates.extend(id_index.get(target_id, []))

        # 3) FreeWiFiの表示名で自動照合
        n = norm(target_name)
        candidates.extend(name_index.get(n, []))

        # 4) tvg-id自体を名称扱いして照合
        candidates.extend(name_index.get(norm(target_id), []))

        # 重複排除して優先順位順
        uniq = []
        seen = set()
        for item in sorted(candidates):
            key = (item[1], item[2])
            if key not in seen:
                seen.add(key)
                uniq.append(item)

        if not uniq:
            missing.append((target_id, target_name))
            coverage.append(f"MISS\t{target_id}\t{target_name}")
            continue

        _, source_name, source_id = uniq[0]
        source_tuple = next(x for x in loaded if x[0] == source_name)
        _, by_id, _, programmes = source_tuple

        src_ch = by_id[source_id]
        ch = clone(src_ch)
        ch.set("id", target_id)
        out_root.append(ch)

        # 同一局は最優先ソースの番組のみ採用。重複を避ける。
        plist = programmes.get(source_id, [])
        seen_programmes = set()
        added = 0
        for p in plist:
            q = clone(p)
            q.set("channel", target_id)
            key = (q.get("start"), q.get("stop"), (q.findtext("title") or "").strip())
            if key in seen_programmes:
                continue
            seen_programmes.add(key)
            out_root.append(q)
            added += 1

        matched_count += 1
        coverage.append(f"OK\t{target_id}\t{target_name}\t{source_name}\t{source_id}\t{added} programmes")

    ET.indent(out_root, space="  ")
    xml_body = ET.tostring(out_root, encoding="utf-8", xml_declaration=True)
    OUT_XML.write_bytes(xml_body)

    report = [
        "FreeWiFi merged EPG coverage",
        f"wanted={len(wanted)}",
        f"matched={matched_count}",
        f"missing={len(missing)}",
        f"output_bytes={OUT_XML.stat().st_size}",
        "",
        "[source errors]",
        *(errors or ["none"]),
        "",
        "[coverage]",
        *coverage,
    ]
    REPORT.write_text("\n".join(report) + "\n", encoding="utf-8")

    print(f"matched: {matched_count}/{len(wanted)}")
    print(f"guides.xml: {OUT_XML.stat().st_size:,} bytes")
    if missing:
        print("missing IDs:")
        for tvg_id, name in missing:
            print(f"  {tvg_id} | {name}")


if __name__ == "__main__":
    main()
