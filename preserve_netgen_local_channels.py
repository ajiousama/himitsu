#!/usr/bin/env python3
from pathlib import Path
import re

FREEWIFI = Path("freewifi")
START = "# === NETGEN_LOCAL_KEEP_START ==="
END = "# === NETGEN_LOCAL_KEEP_END ==="

# netgen 廃止後も freewifi に残すローカル系バックアップ。
# 愛媛系は freewifi の既存エントリを一切削除しない。
ENTRIES = [
    ('ABCテレビ_jp', 'https://xuanzi-storage.netgenx.site/icons/icon_10.png', '朝日放送 (akariko backup)', 'https://akariko-bck1.sankuria.sbs/stream/jp/abc/stream-output.m3u8?mode=hls'),
    ('毎日テレビ_jp', 'https://xuanzi-storage.netgenx.site/icons/icon_9.png', '毎日放送 (akariko backup)', 'https://akariko-bck1.sankuria.sbs/stream/jp/mbs/stream-output.m3u8?mode=hls'),
    ('関西テレビ_jp', 'https://xuanzi-storage.netgenx.site/icons/icon_11.png', '関西テレビ (akariko backup)', 'https://akariko-bck1.sankuria.sbs/stream/jp/kansai_tv/stream-output.m3u8?mode=hls'),
    ('読売テレビ_jp', 'https://xuanzi-storage.netgenx.site/icons/icon_12.png', '読売テレビ (akariko backup)', 'https://akariko-bck1.sankuria.sbs/stream/jp/ytv/stream-output.m3u8?mode=hls'),
    ('テレビ大阪_jp', 'https://xuanzi-storage.netgenx.site/icons/icon_13.png', 'テレビ大阪 (akariko backup)', 'https://akariko-bck1.sankuria.sbs/stream/jp/tv_osaka/stream-output.m3u8?mode=hls'),
    ('NHK大阪・総合_jp', 'https://tvguide.myjcom.jp/monomedia/ch_logo/otd/logo-7FE0-011-400x400.png?', 'NHK G Osaka (akariko backup)', 'https://akariko-bck1.sankuria.sbs/stream/jp/nhk_g_osaka/stream-output.m3u8?mode=hls'),
    ('サンテレビ_jp', 'https://xuanzi-storage.netgenx.site/icons/icon_14.png', 'サンテレビ (akariko backup)', 'https://akariko-bck1.sankuria.sbs/stream/jp/sun/stream-output.m3u8?mode=hls'),
    ('KBS京都_jp', 'https://xuanzi-storage.netgenx.site/icons/icon_14.png', 'KBS京都 (akariko backup)', 'https://akariko-bck1.sankuria.sbs/stream/jp/kbs/stream-output.m3u8?mode=hls'),
]


def build_block():
    out = [START, '## netgen廃止後ローカル局バックアップ（在阪＋KBS京都）']
    for tvgid, logo, name, url in ENTRIES:
        out.append(f'#EXTINF:-1 tvg-id="{tvgid}" tvg-logo="{logo}" group-title="関西",{name}')
        out.append(url)
    out.append(END)
    return "\n".join(out)


def main():
    text = FREEWIFI.read_text(encoding='utf-8')
    pat = re.compile(rf'\n?{re.escape(START)}.*?{re.escape(END)}\n?', re.S)
    text = pat.sub('\n', text)
    block = build_block()
    marker = '# === NHK_RADIO_MANAGED_START ==='
    if marker in text:
        text = text.replace(marker, block + '\n\n' + marker, 1)
    else:
        text = text.rstrip() + '\n\n' + block + '\n'
    FREEWIFI.write_text(text, encoding='utf-8')
    print(f'kept {len(ENTRIES)} netgen local backup entries in freewifi; Ehime entries untouched')


if __name__ == '__main__':
    main()
