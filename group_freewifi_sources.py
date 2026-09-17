from pathlib import Path
import re

FREEWIFI = Path("freewifi")

OLD_HARUKA_BASE = "http://118.68.167.114:9394/stream"
HARUKA_BASE = "http://42.113.96.247:9394/stream"
BLOG_BASE = "https://haru.charandom.blog/stream/jp"
PRIME_BASE = "http://cdns.jp-primehome.com:8000/zhongying/live/playlist.m3u8"
PRIME_QUERY = (
    "isp=5&bind=0&uin=159413&playseek=0&timestamp=1732380893&"
    "sign=ca849dc6608a1dc0afb2559343d13bf779f7a6542b2ec260d8e8887f8c2e03cf"
)
NAORI_BASE = "https://naori-test.netgenx.site/pxx.php?shk_cid="

MAIN_TVER = {
    "Tver TBS系",
    "Tver テレ朝系",
    "Tver テレ東系",
    "Tver フジ系",
    "Tver 日テレ系",
}

LOGOS = {
    "nhk": "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/contrast/NHK__jp_49d60275.png",
    "nhke": "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/contrast/NHK__jp_afb07355.png",
    "tbs": "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/contrast/TBS_jp_dc5a51d6.png",
    "ex": "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/contrast/jp_10d2382c.png",
    "tx": "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/contrast/jp_a5cec3a0.png",
    "cx": "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/contrast/jp_8d726001.png",
    "ntv": "https://i.imgur.com/oIfp5K3.jpeg",
    "mx": "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/contrast/TOKYO_MX_jp_8c4572b1.png",
    "mx2": "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/contrast/TOKYO_MX2_jp_b68495fb.png",
    "mbs": "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/contrast/jp_ddd090aa.png",
    "abc": "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/contrast/ABC__jp_cc34568c.png",
    "tvo": "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/contrast/jp_eaec50e9.png",
    "ktv": "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/contrast/jp_0322bb7f.png",
    "ytv": "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/contrast/jp_81408653.png",
    "sun": "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/contrast/jp_bdba388c.png",
    "kbs": "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/contrast/KBS__jp_a61c39e5.png",
}


def parse_entries(text: str):
    """Return every well-formed EXTINF + URL pair, preserving current URLs."""
    lines = text.splitlines()
    result = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith("#EXTINF:"):
            i += 1
            continue
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j >= len(lines) or lines[j].startswith("#"):
            i += 1
            continue
        name = line.rsplit(",", 1)[-1].strip()
        result.append((name, line, lines[j].strip()))
        i = j + 1
    return result


def set_group(inf: str, group: str) -> str:
    if re.search(r'group-title="[^"]*"', inf):
        return re.sub(r'group-title="[^"]*"', f'group-title="{group}"', inf, count=1)
    return inf


def add_entry(out, tvg_id, logo, name, source, url):
    out.extend([
        f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-logo="{logo}" group-title="地上波",{name} ({source})',
        url,
        "",
    ])


def add_four(out, tvg_id, logo, name, stream_no, blog_slug, cid, naori_cid=None):
    add_entry(out, tvg_id, logo, name, "haruka(9394)", f"{HARUKA_BASE}/{stream_no}.m3u8")
    add_entry(out, tvg_id, logo, name, "blog", f"{BLOG_BASE}/{blog_slug}/stream-output.m3u8?mode=hls")
    add_entry(out, tvg_id, logo, name, "primehome", f"{PRIME_BASE}?cid={cid}&{PRIME_QUERY}")
    add_entry(out, tvg_id, logo, name, "naori", f"{NAORI_BASE}{naori_cid or cid}")


def remove_entry(text: str, inf: str, url: str) -> str:
    # Remove exact current pair, including surrounding blank lines when possible.
    patterns = [
        f"{inf}\n{url}\n\n",
        f"{inf}\n{url}\n",
    ]
    for pat in patterns:
        if pat in text:
            return text.replace(pat, "", 1)
    return text


def main() -> None:
    text = FREEWIFI.read_text(encoding="utf-8-sig", errors="strict")
    if not text.startswith("#EXTM3U"):
        raise RuntimeError("freewifi header missing")
    if "## 地上波" not in text or "## BS" not in text:
        raise RuntimeError("required freewifi section markers missing")

    all_entries = parse_entries(text)
    by_name = {name: (inf, url) for name, inf, url in all_entries}

    # Preserve current main TVer simulcast URLs exactly as they exist today.
    missing = sorted(MAIN_TVER - by_name.keys())
    if missing:
        raise RuntimeError(f"missing main TVer entries: {missing}")

    specials = [
        (name, inf, url)
        for name, inf, url in all_entries
        if name.startswith("Tver ") and name not in MAIN_TVER
    ]

    start = text.index("## 地上波")
    end = text.index("## BS", start)
    prefix = text[:start]
    rest = text[end:]

    # Make reruns idempotent: remove previously managed special TVer pairs/headings.
    for _name, inf, url in specials:
        rest = remove_entry(rest, inf, url)
    rest = re.sub(r'(?m)^### TVerﾘｱﾙﾀｲﾑ\s*\n+', "", rest)

    out = ["## 地上波", ""]

    def add_tver(name: str):
        inf, url = by_name[name]
        out.extend([set_group(inf, "地上波"), url, ""])

    # 1) NHK: Tokyo x4 -> Osaka x4 -> Kyoto -> E x4
    add_four(out, "NHK東京・総合_jp", LOGOS["nhk"], "NHK東京・総合", 14, "nhk_g", "gd01")
    add_four(out, "NHK大阪・総合_jp", LOGOS["nhk"], "NHK大阪・総合", 25, "nhk_g_osaka", "gx06")
    add_entry(out, "NHK京都・総合_jp", LOGOS["nhk"], "NHK京都・総合", "haruka(9394)", f"{HARUKA_BASE}/321.m3u8")
    add_four(out, "NHK東京・教育_jp", LOGOS["nhke"], "NHK教育", 3, "nhk_e", "gd02")

    # 2) TBS -> TVer -> MBS
    add_four(out, "TBS_jp", LOGOS["tbs"], "TBS", 5, "tbs", "gd04")
    add_tver("Tver TBS系")
    add_four(out, "毎日テレビ_jp", LOGOS["mbs"], "MBS毎日放送", 18, "mbs", "gx01")

    # 3) TV Asahi -> TVer -> ABC
    add_four(out, "テレビ朝日_jp", LOGOS["ex"], "テレビ朝日", 7, "tv_asahi", "gd06", "hdgd06")
    add_tver("Tver テレ朝系")
    add_four(out, "ABCテレビ_jp", LOGOS["abc"], "ABCテレビ", 28, "abc", "gx02")

    # 4) TV Tokyo -> TVer -> TV Osaka
    add_four(out, "テレ東_jp", LOGOS["tx"], "テレビ東京", 8, "tv_tokyo", "gd07")
    add_tver("Tver テレ東系")
    add_four(out, "テレビ大阪_jp", LOGOS["tvo"], "テレビ大阪", 22, "tv_osaka", "gx05")

    # 5) Fuji -> TVer -> Kansai TV
    add_four(out, "フジテレビ_jp", LOGOS["cx"], "フジテレビ", 12, "fuji_tv", "gd05")
    add_tver("Tver フジ系")
    add_four(out, "関西テレビ_jp", LOGOS["ktv"], "関西テレビ", 20, "kansai_tv", "gx03")

    # 6) NTV -> TVer -> YTV
    add_four(out, "日本テレビ_jp", LOGOS["ntv"], "日本テレビ", 4, "ntv", "gd03")
    add_tver("Tver 日テレ系")
    add_four(out, "読売テレビ_jp", LOGOS["ytv"], "読売テレビ", 21, "ytv", "gx04")

    # 7) MX1 x4 -> MX2 -> SUN x4 -> KBS Kyoto
    add_four(out, "TOKYO・MX_jp", LOGOS["mx"], "TOKYO MX1", 17, "tokyo_mx1", "gd08")
    add_entry(out, "TOKYO・MX2_jp", LOGOS["mx2"], "TOKYO MX2", "blog", f"{BLOG_BASE}/tokyo_mx2/stream-output.m3u8?mode=hls")
    add_four(out, "サンテレビ_jp", LOGOS["sun"], "サンテレビ", 23, "sun", "gx07")
    add_entry(out, "KBS京都_jp", LOGOS["kbs"], "KBS京都", "haruka(9394)", f"{HARUKA_BASE}/116.m3u8")

    terrestrial = "\n".join(out).rstrip() + "\n\n"

    # Put all non-network-main TVer real-time/FAST streams into その他.
    if specials:
        marker = "## その他"
        if marker not in rest:
            raise RuntimeError("その他 section missing")
        pos = rest.index(marker) + len(marker)
        special_lines = ["", "", "### TVerﾘｱﾙﾀｲﾑ", ""]
        for _name, inf, url in specials:
            special_lines.extend([set_group(inf, "TVerﾘｱﾙﾀｲﾑ"), url, ""])
        block = "\n".join(special_lines).rstrip() + "\n"
        rest = rest[:pos] + block + rest[pos:]

    new_text = prefix + terrestrial + rest.lstrip("\n")
    # Keep every HARUKA 9394 entry (including BS/CS blocks outside the rebuilt terrestrial section)
    # on the currently confirmed host so later normalization cannot roll it back.
    new_text = new_text.replace(OLD_HARUKA_BASE, HARUKA_BASE)
    FREEWIFI.write_text(new_text.rstrip() + "\n", encoding="utf-8")
    print(f"Rebuilt terrestrial block; moved {len(specials)} special TVer entries")


if __name__ == "__main__":
    main()
