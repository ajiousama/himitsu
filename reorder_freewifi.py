#!/usr/bin/env python3
import re
from collections import OrderedDict
from pathlib import Path

PATH = Path("freewifi")

KANSAI_IDS = (
    "NHK大阪", "読売テレビ", "毎日放送", "朝日放送", "関西テレビ", "テレビ大阪",
    "サンテレビ", "KBS京都", "びわ湖放送", "奈良テレビ", "テレビ和歌山",
)
KANSAI_WORDS = (
    "大阪", "京都", "神戸", "兵庫", "奈良", "滋賀", "和歌山",
    "読売テレビ", "毎日放送", "MBS", "朝日放送", "ABCテレビ", "ABC TV",
    "関西テレビ", "カンテレ", "テレビ大阪", "サンテレビ", "KBS京都",
    "びわ湖放送", "奈良テレビ", "テレビ和歌山",
)
KANTO_IDS = (
    "NHK東京", "日本テレビ", "TBS", "テレビ朝日", "フジテレビ", "テレビ東京",
    "TOKYO MX", "東京MX", "tvk", "テレビ神奈川", "テレ玉", "千葉テレビ",
)
KANTO_WORDS = (
    "東京", "日本テレビ", "日テレ", "TBS", "テレビ朝日", "テレ朝",
    "フジテレビ", "フジ系", "テレビ東京", "テレ東", "TOKYO MX", "東京MX",
    "tvk", "テレビ神奈川", "テレ玉", "千葉テレビ",
)

TVER_MAP = {
    "ntv": "日本テレビ_jp",
    "tbs": "TBS_jp",
    "ex": "テレビ朝日_jp",
    "tv-asahi": "テレビ朝日_jp",
    "fuji": "フジテレビ_jp",
    "cx": "フジテレビ_jp",
    "tx": "テレビ東京_jp",
    "tvtokyo": "テレビ東京_jp",
}

GROUP_RE = re.compile(r'group-title="([^"]*)"')
ID_RE = re.compile(r'tvg-id="([^"]*)"')


def parse_entries(text: str):
    lines = text.splitlines()
    header = lines[0] if lines and lines[0].startswith("#EXTM3U") else "#EXTM3U"
    entries = []
    i = 1
    while i < len(lines):
        if lines[i].startswith("#EXTINF:"):
            meta = lines[i]
            url = lines[i + 1] if i + 1 < len(lines) else ""
            entries.append([meta, url])
            i += 2
        else:
            i += 1
    return header, entries


def fields(meta: str):
    gid = ID_RE.search(meta)
    grp = GROUP_RE.search(meta)
    tvg_id = gid.group(1) if gid else ""
    group = grp.group(1) if grp else ""
    name = meta.split(",", 1)[1].strip() if "," in meta else ""
    return tvg_id, group, name


def is_youtube(meta: str, url: str, group: str, name: str):
    s = f"{meta} {url} {group} {name}".lower()
    return (
        "youtube" in group.lower()
        or "youtube.com" in s
        or "youtu.be" in s
        or "googlevideo.com" in s
        or "general_youtube" in s
    )


def classify(meta: str, url: str):
    tvg_id, group, name = fields(meta)
    joined = f"{tvg_id} {name}"
    group_norm = group.replace("（", "(").replace("）", ")").replace("ＮＡＯＲＩ", "NAORI")
    group_lower = group_norm.lower()

    if is_youtube(meta, url, group, name):
        return "YouTube"
    if "予備" in group or "予備" in name:
        return "予備"

    # Satellite NAORI groups are intentionally kept separate.
    if group_lower in ("bs(naori)", "ｂｓ(naori)"):
        return "BS(NAORI)"
    if group_lower in ("cs(naori)", "ｃｓ(naori)"):
        return "CS(NAORI)"

    if group in ("BS", "ＢＳ") or re.search(r'(^|[^A-Za-z])BS(?:\d|\b)', joined, re.I):
        return "BS"
    if group in ("CS", "ＣＳ") or re.search(r'(^|[^A-Za-z])CS(?:\d|\b)', joined, re.I):
        return "CS"

    # Only terrestrial NAORI is absorbed into the existing regional groups.
    if any(x in tvg_id for x in KANSAI_IDS) or any(x in joined for x in KANSAI_WORDS):
        return "関西"
    if any(x in tvg_id for x in KANTO_IDS) or any(x in joined for x in KANTO_WORDS):
        return "関東"

    if group == "関西":
        return "関西"
    if group == "関東":
        return "関東"

    # TVer real-time channels belong with their corresponding terrestrial station.
    if group == "TVerﾘｱﾙﾀｲﾑ" or tvg_id.startswith("tver_") or name.lower().startswith("tver"):
        return "関東"

    if group and group.upper() != "NAORI":
        return group
    return "その他"


def replace_group(meta: str, new_group: str):
    if GROUP_RE.search(meta):
        return GROUP_RE.sub(f'group-title="{new_group}"', meta, count=1)
    comma = meta.find(",")
    if comma >= 0:
        return meta[:comma] + f' group-title="{new_group}"' + meta[comma:]
    return meta


def station_key(meta: str):
    tvg_id, group, name = fields(meta)
    low_id = tvg_id.lower()
    low_name = name.lower()

    if low_id.startswith("tver_"):
        suffix = low_id[5:]
        for k, v in TVER_MAP.items():
            if suffix == k or k in suffix:
                return v
    if "tver" in low_name:
        if "日テレ" in name or "日本テレビ" in name:
            return "日本テレビ_jp"
        if "tbs" in low_name:
            return "TBS_jp"
        if "テレ朝" in name or "テレビ朝日" in name:
            return "テレビ朝日_jp"
        if "フジ" in name:
            return "フジテレビ_jp"
        if "テレ東" in name or "テレビ東京" in name:
            return "テレビ東京_jp"

    if tvg_id:
        return tvg_id

    n = re.sub(r'\s*\([^)]*(?:ハルカ|NAORI|naori|kaiteki|primehome|予備)[^)]*\)\s*$', '', name, flags=re.I)
    return n or name


def is_tver(meta: str):
    tvg_id, group, name = fields(meta)
    return tvg_id.lower().startswith("tver_") or "tver" in name.lower() or group == "TVerﾘｱﾙﾀｲﾑ"


def order_region(entries):
    stations = OrderedDict()
    for e in entries:
        stations.setdefault(station_key(e[0]), []).append(e)
    out = []
    for items in stations.values():
        normal = [e for e in items if not is_tver(e[0])]
        tver = [e for e in items if is_tver(e[0])]
        out.extend(normal)
        out.extend(tver)
    return out


def main():
    text = PATH.read_text(encoding="utf-8-sig")
    header, entries = parse_entries(text)

    buckets = OrderedDict()
    for meta, url in entries:
        group = classify(meta, url)
        meta = replace_group(meta, group)
        buckets.setdefault(group, []).append([meta, url])

    # Requested order: terrestrial, BS, BS(NAORI), CS, CS(NAORI), reserve,
    # other existing groups, and YouTube last.
    priority = ["関西", "関東", "BS", "BS(NAORI)", "CS", "CS(NAORI)", "予備"]
    remaining = [g for g in buckets if g not in priority and g != "YouTube"]
    final_groups = [g for g in priority if g in buckets] + remaining
    if "YouTube" in buckets:
        final_groups.append("YouTube")

    out = [header, ""]
    for g in final_groups:
        if g in ("関西", "関東"):
            section = order_region(buckets[g])
        else:
            section = buckets[g]
        if g in ("関西", "関東"):
            if not any(x.startswith("## 地上波") for x in out):
                out += ["## 地上波", ""]
            out += [f"### {g}", ""]
        else:
            out += [f"## {g}", ""]
        for meta, url in section:
            out += [meta, url, ""]

    # Compatibility markers for the existing GitHub Actions validator.
    out += ["# === NAORI_MANAGED_START ===", "# === NAORI_MANAGED_END ==="]

    PATH.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")

    result = PATH.read_text(encoding="utf-8")
    if 'group-title="NAORI"' in result or 'group-title="naori"' in result:
        raise SystemExit("standalone terrestrial NAORI group still remains")
    groups = GROUP_RE.findall(result)
    if "YouTube" in groups and groups[-1] != "YouTube":
        raise SystemExit("YouTube is not the final group")
    print("FreeWiFi reordered:", ", ".join(final_groups))


if __name__ == "__main__":
    main()
