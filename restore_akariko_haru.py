from pathlib import Path
import re
import unicodedata
from normalize_haruka_akariko import normalize_layout

FREEWIFI = Path("freewifi")
BASE = "https://haru.charandom.blog/stream/jp/"
START = "# === AKARIKO_HARU_MANAGED_START ==="
END = "# === AKARIKO_HARU_MANAGED_END ==="

# Restore the same managed Akariko channel set that FreeWiFi used before the
# 2026-09-04 cleanup, but point it at the currently confirmed HARU/blog host.
# Do not invent new slugs here; only previously managed FreeWiFi slugs are used.
CHANNELS = [
    # 関西
    ("NHK大阪・総合_jp", "関西", "NHK G Osaka (akariko)", "nhk_g_osaka", "https://tvguide.myjcom.jp/monomedia/ch_logo/otd/logo-7FE0-011-400x400.png?"),
    ("読売テレビ_jp", "関西", "読売テレビ (akariko)", "ytv", "https://xuanzi-storage.netgenx.site/icons/icon_12.png"),
    ("毎日テレビ_jp", "関西", "毎日放送 (akariko)", "mbs", "https://xuanzi-storage.netgenx.site/icons/icon_9.png"),
    ("関西テレビ_jp", "関西", "関西テレビ (akariko)", "kansai_tv", "https://xuanzi-storage.netgenx.site/icons/icon_11.png"),
    ("ABCテレビ_jp", "関西", "朝日放送 (akariko)", "abc", "https://xuanzi-storage.netgenx.site/icons/icon_10.png"),
    ("テレビ大阪_jp", "関西", "テレビ大阪 (akariko)", "tv_osaka", "https://xuanzi-storage.netgenx.site/icons/icon_13.png"),
    ("KBS京都_jp", "関西", "KBS京都 (akariko)", "kbs", "https://xuanzi-storage.netgenx.site/icons/icon_14.png"),
    ("サンテレビ_jp", "関西", "サンテレビ (akariko)", "sun", "https://xuanzi-storage.netgenx.site/icons/icon_14.png"),

    # 関東
    ("NHK東京・総合_jp", "関東", "NHK G (akariko)", "nhk_g", "https://tvguide.myjcom.jp/monomedia/ch_logo/otd/logo-7FE0-011-400x400.png?"),
    ("NHK東京・教育_jp", "関東", "NHK E (akariko)", "nhk_e", "https://tvguide.myjcom.jp/monomedia/ch_logo/otd/logo-7FE1-021-400x400.png?"),
    ("日本テレビ_jp", "関東", "日本テレビ (akariko)", "ntv", "https://i.imgur.com/oIfp5K3.jpeg"),
    ("テレビ朝日_jp", "関東", "テレビ朝日 (akariko)", "tv_asahi", "https://tvguide.myjcom.jp/monomedia/ch_logo/otd/logo-7FE5-051-400x400.png?"),
    ("TBS_jp", "関東", "TBS (akariko)", "tbs", "https://tvguide.myjcom.jp/monomedia/ch_logo/otd/logo-7FE3-061-400x400.png?"),
    ("テレビ東京_jp", "関東", "テレビ東京 (akariko)", "tv_tokyo", "https://tvguide.myjcom.jp/monomedia/ch_logo/otd/logo-7FE6-071-400x400.png?"),
    ("フジテレビ_jp", "関東", "フジテレビ (akariko)", "fuji_tv", "https://tvguide.myjcom.jp/monomedia/ch_logo/otd/logo-7FE4-081-400x400.png?"),
    ("TOKYO・MX_jp", "関東", "TOKYO MX1 (akariko)", "tokyo_mx1", "https://tvguide.myjcom.jp/monomedia/ch_logo/otd/logo-7E87-091-400x400.png"),
    ("TOKYO・MX2_jp", "関東", "TOKYO MX2 (akariko)", "tokyo_mx2", "https://tvguide.myjcom.jp/monomedia/ch_logo/otd/logo-7E87-093-400x400.png"),

    # BS
    ("BS10_jp", "BS", "BS10 (akariko)", "bs10", "https://tvguide.myjcom.jp/monomedia/ch_logo/bsd/logo-0004-200-400x400.png"),
    ("BS11_jp", "BS", "BS11 (akariko)", "bs11", "https://tvguide.myjcom.jp/monomedia/ch_logo/bsd/logo-0004-211-400x400.png"),
    ("BS12トゥエルビ_jp", "BS", "BS12 トゥエルビ (akariko)", "bs_12", "https://tvguide.myjcom.jp/monomedia/ch_logo/bsd/logo-0004-222-400x400.png"),
    ("WOWOWプラス_jp", "BS", "WOWOWプラス (akariko)", "wowow_plus", "https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/bs252.gif"),
    ("BSよしもと_jp", "BS", "BSよしもと (akariko)", "bs_yoshimoto", "https://tvguide.myjcom.jp/monomedia/ch_logo/bsd/logo-0004-265-400x400.png"),

    # CS
    ("AT-X_jp", "CS", "AT-X (akariko)", "at-x", "https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs333.gif"),
    ("Mnet_jp", "CS", "Mnet (akariko)", "mnet", "https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs318.gif"),
    ("V☆パラダイス_jp", "CS", "V☆パラダイス (akariko)", "v_paradise_nsfw", "https://www.skyperfectv.co.jp/library/common/img/channel/icon/premium/635.gif"),
    ("ザ・シネマ_jp", "CS", "ザ・シネマ (akariko)", "the_cinema", "https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs227.gif"),
    ("カートゥーン-ネットワーク_jp", "CS", "カートゥーン ネットワーク (akariko)", "cartoon_network_japan", "https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs331.gif"),
    ("日テレジータス_jp", "CS", "日テレG+ (akariko)", "nittele_g+", "https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs257.gif"),
    ("日テレプラス_jp", "CS", "日テレプラス (akariko)", "nittele_plus", "https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs300.gif"),
    ("TBSチャンネル1_jp", "CS", "TBSチャンネル1 (akariko)", "tbs_channel_1", "https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs296.gif"),
    ("TBSチャンネル2_jp", "CS", "TBSチャンネル2 (akariko)", "tbs_channel_2", "https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs297.gif"),
    ("テレ朝チャンネル1_jp", "CS", "テレ朝チャンネル1 (akariko)", "tv_asahi_channel_1", "https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs298.gif"),
    ("テレ朝チャンネル2_jp", "CS", "テレ朝チャンネル2 (akariko)", "tv_asahi_channel_2", "https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs299.gif"),
    ("フジテレビONE_jp", "CS", "フジテレビONE (akariko)", "fuji_tv_one", "https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs307.gif"),
    ("フジテレビTWO_jp", "CS", "フジテレビTWO (akariko)", "fuji_tv_two", "https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs308.gif"),
    ("フジテレビNEXT_jp", "CS", "フジテレビNEXT (akariko)", "fuji_tv_next", "https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs309.gif"),
    ("チャンネルNECO_jp", "CS", "チャンネルNECO (akariko)", "neco_ch", "https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs223.gif"),
    ("Dlife_jp", "CS", "Dlife (akariko)", "dlife", "https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs312.gif"),
    ("FIGHTING-TV-サムライ_jp", "CS", "FIGHTING TV サムライ (akariko)", "fighting_tv_samurai", "https://www.skyperfectv.co.jp/library/common/img/channel/icon/premium/600.gif"),
    ("メ～テレNEXT_jp", "CS", "メ～テレNEXT (akariko)", "me-tele_next", "https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs301.gif"),
    ("スポーツライブ＋_jp", "CS", "スポーツライブ＋ (akariko)", "sport_live_plus", "https://www.skyperfectv.co.jp/library/common/img/channel/icon/premium/580.gif"),
    ("囲碁将棋チャンネル_jp", "CS", "囲碁将棋チャンネル (akariko)", "shogi_channel", "https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs363.gif"),
    ("鉄道チャンネル_jp", "CS", "鉄道チャンネル (akariko)", "tetsudo_channel", "https://www.skyperfectv.co.jp/library/common/img/channel/icon/premium/546.gif"),
    ("MUSIC-ON-TV_jp", "CS", "MUSIC ON! TV (akariko)", "music_on_tv", "https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs325.gif"),
    ("ミュージック・エア_jp", "CS", "ミュージック・エア (akariko)", "music_air", "https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs324.gif"),
    ("アクションチャンネル_jp", "CS", "アクションチャンネル (akariko)", "action_channel", "https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs311.gif"),
    ("ミステリーチャンネル_jp", "CS", "ミステリーチャンネル (akariko)", "mystery_channel", "https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs316.gif"),
    ("KNTV_jp", "CS", "KNTV (akariko)", "kntv", "https://www.skyperfectv.co.jp/library/common/img/channel/icon/premium/657.gif"),
    ("日テレNEWS24_jp", "CS", "日テレNEWS24 (akariko)", "ntv_news24", "https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs349.gif"),
]


def stream_url(slug: str) -> str:
    return f"{BASE}{slug}/stream-output.m3u8?mode=hls"


def group_title(group: str) -> str:
    return f"akariko{group}"


def strip_previous_managed_entries(lines: list[str]) -> tuple[list[str], int]:
    out = []
    i = 0
    removed = 0
    in_block = False

    while i < len(lines):
        line = lines[i]

        if line == START:
            in_block = True
            i += 1
            continue
        if line == END:
            in_block = False
            i += 1
            continue
        if in_block:
            i += 1
            continue

        # Also clean older Akariko-labelled pairs so rerunning is idempotent.
        if line.startswith("#EXTINF:") and "(akariko)" in line.lower():
            removed += 1
            i += 1
            if i < len(lines) and not lines[i].lstrip().startswith("#"):
                i += 1
            continue

        out.append(line)
        i += 1

    return out, removed


def _tvg_id(block: str):
    m = re.search(r'tvg-id="([^"]+)"', block)
    return m.group(1) if m else None


def _display_name(block: str) -> str:
    if ',' not in block:
        return ''
    name = block.split(',', 1)[1].splitlines()[0]
    name = re.sub(r'\s*\((?:haruka|akariko)\)\s*$', '', name, flags=re.I)
    name = unicodedata.normalize('NFKC', name)
    return re.sub(r'\s+', '', name).lower()


def _parse_akariko_managed(body: str) -> list[str]:
    lines = [x for x in body.splitlines() if x.strip()]
    entries = []
    i = 0
    while i < len(lines):
        if lines[i].startswith('#EXTINF:') and i + 1 < len(lines) and not lines[i + 1].lstrip().startswith('#'):
            entries.append(lines[i] + '\n' + lines[i + 1])
            i += 2
        else:
            i += 1
    return entries


def normalize_layout(text: str) -> str:
    text = text.replace('http://haru.charandom.blog/', 'https://haru.charandom.blog/')
    start_pos = text.find(START)
    end_pos = text.find(END)
    managed_entries = []
    if start_pos >= 0 and end_pos > start_pos:
        managed_body = text[start_pos + len(START):end_pos]
        managed_entries = _parse_akariko_managed(managed_body)
        base = (text[:start_pos] + text[end_pos + len(END):]).strip()
    else:
        base = text.strip()

    by_id = {}
    by_name = {}
    remaining = list(managed_entries)
    for entry in managed_entries:
        tid = _tvg_id(entry)
        if tid:
            by_id.setdefault(tid, []).append(entry)
        nm = _display_name(entry)
        if nm:
            by_name.setdefault(nm, []).append(entry)

    def take_match(block: str):
        candidates = []
        tid = _tvg_id(block)
        if tid:
            candidates.extend(by_id.get(tid, []))
        nm = _display_name(block)
        if nm:
            candidates.extend(by_name.get(nm, []))
        for entry in candidates:
            if entry in remaining:
                remaining.remove(entry)
                return entry
        return None

    blocks = re.split(r'\n\s*\n', base)
    out = []
    for block in blocks:
        if block.startswith('#EXTINF:') and (
            'group-title="haruka1 ' in block or
            'group-title="haruka3 ' in block or
            'ハルカ1' in block or
            'ハルカ3' in block
        ):
            continue
        block = block.replace('group-title="haruka2 ', 'group-title="haruka ')
        block = block.replace('ハルカ2', 'haruka')
        out.append(block)
        if block.startswith('#EXTINF:') and 'group-title="haruka ' in block:
            match = take_match(block)
            if match:
                out.append(match)

    if remaining:
        out.append('\n'.join([START, *remaining, END]))

    result = '\n\n'.join(x for x in out if x.strip()).rstrip() + '\n'
    forbidden = [
        'group-title="haruka1 ', 'group-title="haruka2 ', 'group-title="haruka3 ',
        'ハルカ1', 'ハルカ2', 'ハルカ3', 'http://haru.charandom.blog/'
    ]
    bad = [x for x in forbidden if x in result]
    if bad:
        raise RuntimeError(f'layout validation failed: {bad}')
    return result

def main() -> None:
    text = FREEWIFI.read_text(encoding="utf-8-sig", errors="strict")
    if not text.startswith("#EXTM3U"):
        raise RuntimeError("freewifi header missing")

    lines, removed = strip_previous_managed_entries(text.splitlines())

    lines += ["", START]
    for tvg_id, group, name, slug, logo in CHANNELS:
        lines.append(
            f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-logo="{logo}" '
            f'group-title="{group_title(group)}",{name}'
        )
        lines.append(stream_url(slug))
    lines.append(END)

    out = normalize_layout("\n".join(lines).rstrip() + "\n")

    expected = len(CHANNELS)
    actual_labels = out.lower().count("(akariko)")
    actual_host = out.count(BASE)
    if actual_labels != expected or actual_host != expected:
        raise RuntimeError(
            f"restore validation failed: labels={actual_labels}, host_urls={actual_host}, expected={expected}"
        )

    FREEWIFI.write_text(out, encoding="utf-8")
    print(f"Restored Akariko/HARU entries: {expected}; removed stale managed entries: {removed}")
    print(f"Base: {BASE}")


if __name__ == "__main__":
    main()
