from pathlib import Path
import re

FREEWIFI = Path('freewifi')
START = '# === NAORI_MANAGED_START ==='
END = '# === NAORI_MANAGED_END ==='
BASE = 'https://naori-test.netgenx.site/pxx.php?shk_cid='

# Publicly observed NAORI channel mapping.  Keep this block independent so it can
# be refreshed/replaced without touching HARUKA, Primehome, YouTube or sports.
CHANNELS = [
    # Terrestrial Tokyo
    ('NHK東京・総合_jp', '関東(naori)', 'NHK G (naori HD)', 'hdgd01', 'https://tvguide.myjcom.jp/monomedia/ch_logo/otd/logo-7FE0-011-400x400.png?'),
    ('NHK東京・教育_jp', '関東(naori)', 'NHK E (naori HD)', 'hdgd02', 'https://tvguide.myjcom.jp/monomedia/ch_logo/otd/logo-7FE1-021-400x400.png?'),
    ('日本テレビ_jp', '関東(naori)', '日本テレビ (naori HD)', 'hdgd03', 'https://i.imgur.com/oIfp5K3.jpeg'),
    ('TBS_jp', '関東(naori)', 'TBS (naori HD)', 'hdgd04', 'https://tvguide.myjcom.jp/monomedia/ch_logo/otd/logo-7FE3-061-400x400.png?'),
    ('フジテレビ_jp', '関東(naori)', 'フジテレビ (naori HD)', 'hdgd05', 'https://tvguide.myjcom.jp/monomedia/ch_logo/otd/logo-7FE4-081-400x400.png?'),
    ('テレビ朝日_jp', '関東(naori)', 'テレビ朝日 (naori HD)', 'hdgd06', 'https://tvguide.myjcom.jp/monomedia/ch_logo/otd/logo-7FE5-051-400x400.png?'),
    ('テレビ東京_jp', '関東(naori)', 'テレビ東京 (naori HD)', 'hdgd07', 'https://tvguide.myjcom.jp/monomedia/ch_logo/otd/logo-7FE6-071-400x400.png?'),
    ('TOKYO MX1_jp', '関東(naori)', 'TOKYO MX1 (naori HD)', 'hdgd08', 'https://tvguide.myjcom.jp/monomedia/ch_logo/otd/logo-7E87-091-400x400.png'),

    # BS
    ('NHKBS_jp', 'BS(naori)', 'NHK BS (naori)', 'bs11', 'https://tvguide.myjcom.jp/monomedia/ch_logo/bsd/logo-0004-101-400x400.png'),
    ('NHKBSプレミアム4K_jp', 'BS(naori)', 'NHK BSP4K (naori)', 'bs01', 'https://tvguide.myjcom.jp/monomedia/ch_logo/bsd/logo-000B-101-400x400.png'),
    ('BS日テレ_jp', 'BS(naori)', 'BS日テレ (naori)', 'bs02', 'https://tvguide.myjcom.jp/monomedia/ch_logo/bsd/logo-0004-141-400x400.png'),
    ('BS朝日_jp', 'BS(naori)', 'BS朝日 (naori)', 'bs03', 'https://tvguide.myjcom.jp/monomedia/ch_logo/bsd/logo-0004-151-400x400.png'),
    ('BS-TBS_jp', 'BS(naori)', 'BS-TBS (naori)', 'bs04', 'https://tvguide.myjcom.jp/monomedia/ch_logo/bsd/logo-0004-161-400x400.png'),
    ('BSテレ東_jp', 'BS(naori)', 'BSテレ東 (naori)', 'bs05', 'https://tvguide.myjcom.jp/monomedia/ch_logo/bsd/logo-0004-171-400x400.png'),
    ('BSフジ_jp', 'BS(naori)', 'BSフジ (naori)', 'bs06', 'https://tvguide.myjcom.jp/monomedia/ch_logo/bsd/logo-0004-181-400x400.png'),
    ('WOWOWプライム_jp', 'BS(naori)', 'WOWOWプライム (naori)', 'bs12', 'https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/bs191.gif'),
    ('WOWOWライブ_jp', 'BS(naori)', 'WOWOWライブ (naori)', 'bs07', 'https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/bs192.gif'),
    ('WOWOWシネマ_jp', 'BS(naori)', 'WOWOWシネマ (naori)', 'bs20', 'https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/bs193.gif'),
    ('BS10プレミアム_jp', 'BS(naori)', 'BS10プレミアム (naori)', 'bs08', 'https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/bs201.gif'),
    ('グリーンチャンネル_jp', 'BS(naori)', 'グリーンチャンネル (naori)', 'bs14', 'https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/bs234.gif'),
    ('アニマックス_jp', 'BS(naori)', 'アニマックス (naori)', 'bs15', 'https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/bs236.gif'),
    ('J SPORTS 1_jp', 'BS(naori)', 'J SPORTS 1 (naori)', 'bs18', 'https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/bs242.gif'),
    ('J SPORTS 2_jp', 'BS(naori)', 'J SPORTS 2 (naori)', 'bs19', 'https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/bs243.gif'),
    ('J SPORTS 3_jp', 'BS(naori)', 'J SPORTS 3 (naori)', 'bs21', 'https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/bs244.gif'),
    ('J SPORTS 4_jp', 'BS(naori)', 'J SPORTS 4 (naori)', 'bs22', 'https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/bs245.gif'),
    ('日本映画専門チャンネル_jp', 'BS(naori)', '日本映画専門チャンネル (naori)', 'bs23', 'https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/bs255.gif'),
    ('ディズニー・チャンネル_jp', 'BS(naori)', 'ディズニー・チャンネル (naori)', 'bs24', 'https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/bs256.gif'),
    ('釣りビジョン_jp', 'BS(naori)', '釣りビジョン (naori)', 'bs25', 'https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/bs251.gif'),
    ('スペースシャワーTV_jp', 'CS(naori)', 'スペースシャワーTV (naori)', 'bs26', 'https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs322.gif'),
    ('J:COM BS_jp', 'BS(naori)', 'J:COM BS (naori)', 'bs31', 'https://tvguide.myjcom.jp/monomedia/ch_logo/bsd/logo-0004-260-400x400.png'),

    # CS
    ('スカイA_jp', 'CS(naori)', 'スカイA (naori)', 'cs01', 'https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs250.gif'),
    ('ホームドラマチャンネル_jp', 'CS(naori)', 'ホームドラマチャンネル (naori)', 'cs05', 'https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs294.gif'),
    ('キッズステーション_jp', 'CS(naori)', 'キッズステーション (naori)', 'cs07', 'https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs330.gif'),
    ('旅チャンネル_jp', 'CS(naori)', '旅チャンネル (naori)', 'cs12', 'https://www.skyperfectv.co.jp/library/common/img/channel/icon/premium/544.gif'),
    ('歌謡ポップスチャンネル_jp', 'CS(naori)', '歌謡ポップスチャンネル (naori)', 'cs13', 'https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs329.gif'),
    ('GAORA SPORTS_jp', 'CS(naori)', 'GAORA SPORTS (naori)', 'cs17', 'https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs254.gif'),
    ('MTV_jp', 'CS(naori)', 'MTV (naori)', 'cs18', 'https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs323.gif'),
    ('ファミリー劇場_jp', 'CS(naori)', 'ファミリー劇場 (naori)', 'cs20', 'https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs293.gif'),
    ('MONDO TV_jp', 'CS(naori)', 'MONDO TV (naori)', 'cs21', 'https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs295.gif'),
    ('フジテレビNEXT_jp', 'CS(naori)', 'フジテレビNEXT (naori)', 'cs26', 'https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs309.gif'),
    ('東映チャンネル_jp', 'CS(naori)', '東映チャンネル (naori)', 'cs27', 'https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs218.gif'),
    ('チャンネル銀河_jp', 'CS(naori)', 'チャンネル銀河 (naori)', 'cs29', 'https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/cs305.gif'),
]


def build_block():
    lines = [START, '## NAORI（自動管理）']
    for tvg_id, group, name, cid, logo in CHANNELS:
        lines.append(f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-logo="{logo}" group-title="{group}",{name}')
        lines.append(BASE + cid)
    lines.append(END)
    return '\n'.join(lines)


def main():
    text = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    if not text.startswith('#EXTM3U'):
        raise RuntimeError('freewifi header missing')

    # Remove old managed block. Also drop pre-existing NAORI/netgenx entries so each
    # CID appears once and the user-facing label is consistently (naori).
    text = re.sub(re.escape(START) + r'.*?' + re.escape(END) + r'\n?', '', text, flags=re.S)
    lines = text.splitlines()
    out = []
    i = 0
    removed = 0
    while i < len(lines):
        if lines[i].startswith('#EXTINF:') and i + 1 < len(lines) and 'naori-test.netgenx.site/pxx.php?shk_cid=' in lines[i + 1]:
            removed += 1
            i += 2
            continue
        out.append(lines[i])
        i += 1

    text = '\n'.join(out).rstrip() + '\n\n' + build_block() + '\n'
    if text.count('#EXTINF:') < 50:
        raise RuntimeError('channel count collapsed')
    FREEWIFI.write_text(text, encoding='utf-8')
    print(f'NAORI managed channels: {len(CHANNELS)}; old NAORI entries removed: {removed}')


if __name__ == '__main__':
    main()
