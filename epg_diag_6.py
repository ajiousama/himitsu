import gzip
import re
import unicodedata
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

SOURCES = [
    ("japanterebi", "https://animenosekai.github.io/japanterebi-xmltv/guide.xml"),
    ("jcom", "https://raw.githubusercontent.com/dbghelp/JCOM-TV-EPG/refs/heads/main/jcom.xml"),
    ("sky", "https://raw.githubusercontent.com/dbghelp/SKY-PerfecTV-EPG/refs/heads/main/perfectv.xml"),
    ("epgshare_jp1", "https://epgshare01.online/epgshare01/epg_ripper_JP1.xml.gz"),
    ("epgshare_jp2", "https://epgshare01.online/epgshare01/epg_ripper_JP2.xml.gz"),
]

TARGETS = {
    "スペースシャワーTV_jp": ["スペースシャワーTV", "スペースシャワーＴＶ", "音楽・ライブ！ スペースシャワーＴＶ", "スペシャ"],
    "WOWOWプラス_jp": ["WOWOWプラス", "WOWOW プラス"],
    "カートゥーン-ネットワーク_jp": ["カートゥーンネットワーク", "カートゥーン・ネットワーク", "カートゥーン.ネットワーク", "海外アニメ！カートゥーン.ネットワーク"],
    "ホームドラマチャンネル_jp": ["ホームドラマチャンネル", "ホームドラマ"],
    "チャンネル銀河_jp": ["チャンネル銀河", "銀河"],
    "日テレプラス_jp": ["日テレプラス", "日テレプラス ドラマ・アニメ・音楽ライブ"],
}


def fetch_bytes(url):
    req = urllib.request.Request(url, headers={"User-Agent": "FreeWiFi-EPG-Diag/1.0"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


def fetch_xml(url):
    data = fetch_bytes(url)
    if url.endswith(".gz"):
        data = gzip.decompress(data)
    return ET.fromstring(data)


def norm(s):
    s = unicodedata.normalize("NFKC", s or "").lower()
    s = s.replace("_jp", "").replace(".jp", "")
    s = re.sub(r"\([^)]*\)|（[^）]*）", "", s)
    for a, b in [("テレビジョン", "テレビ"), ("放送", ""), ("チャンネル", ""), ("channel", ""), ("hd", ""), ("4k", "")]:
        s = s.replace(a, b)
    s = re.sub(r"[\s\-‐‑‒–—―・･:：/／!！?？☆★♪#＃+＋]+", "", s)
    return s


def score(target_aliases, cid, names):
    vals = [cid] + names
    best = 0
    for ta in target_aliases:
        nt = norm(ta)
        if not nt:
            continue
        for v in vals:
            nv = norm(v)
            if not nv:
                continue
            if nv == nt:
                best = max(best, 100)
            elif nt in nv or nv in nt:
                best = max(best, 70)
            else:
                common = len(set(nt) & set(nv))
                if common >= max(3, min(len(nt), len(nv)) // 2):
                    best = max(best, 20 + common)
    return best


def main():
    lines = []
    for source_name, url in SOURCES:
        try:
            root = fetch_xml(url)
            pc = defaultdict(int)
            for p in root.findall("programme"):
                ch = p.get("channel")
                if ch:
                    pc[ch] += 1

            channels = []
            for ch in root.findall("channel"):
                cid = ch.get("id") or ""
                names = [x.text.strip() for x in ch.findall("display-name") if x.text and x.text.strip()]
                channels.append((cid, names, pc.get(cid, 0)))

            lines.append(f"\n===== {source_name} =====")
            for target_id, aliases in TARGETS.items():
                ranked = []
                for cid, names, count in channels:
                    s = score(aliases, cid, names)
                    if s:
                        ranked.append((s, count, cid, names))
                ranked.sort(key=lambda x: (-x[0], -x[1], x[2]))
                lines.append(f"\n[{target_id}]")
                if not ranked:
                    lines.append("  NO CANDIDATE")
                    continue
                for s, count, cid, names in ranked[:12]:
                    lines.append(f"  score={s:3d} programmes={count:4d} id={cid} names={' | '.join(names)}")
        except Exception as e:
            lines.append(f"\n===== {source_name} ERROR: {type(e).__name__}: {e} =====")

    Path("epg_diag_6.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
