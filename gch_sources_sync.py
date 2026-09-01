from pathlib import Path
import re

FREEWIFI = Path('freewifi')
START = '# === GREEN_CHANNEL_PERSISTENT_START ==='
END = '# === GREEN_CHANNEL_PERSISTENT_END ==='
GROUP = 'グリーンCh'
LOGO = 'https://www.skyperfectv.co.jp/library/common/img/channel/icon/basic/bs234.gif'
TVG_ID = 'グリーンチャンネル_jp'

SOURCES = [
    ('グリーンチャンネル (5002)', 'http://58.82.168.138:5002/bs14.m3u8?token=guoziyun&gid=bs14&channel=zhongying'),
    ('グリーンチャンネル (primehome)', 'http://cdns.jp-primehome.com:8000/zhongying/live/playlist.m3u8?cid=bs14&isp=5&bind=0&uin=159413&playseek=0&timestamp=1732380893&sign=ca849dc6608a1dc0afb2559343d13bf779f7a6542b2ec260d8e8887f8c2e03cf'),
    ('グリーンチャンネル (naori)', 'https://naori-test.netgenx.site/pxx.php?shk_cid=bs14'),
    ('グリーンチャンネル (ハルカ1)', 'http://haruka-ip.f5.si:9394/stream/60.m3u8'),
    ('グリーンチャンネル (ハルカ2)', 'http://42.118.247.37:9394/stream/60.m3u8'),
    ('グリーンチャンネル (ハルカ3)', 'http://ha-ipip.f5.si:9394/stream/60.m3u8'),
    ('グリーンチャンネル (kaitekitv)', 'http://cdns.kaitekitv.com:8000/zhongying/live/playlist.m3u8?cid=bs14&isp=5-15'),
]


def remove_managed(text: str) -> str:
    pat = re.compile(re.escape(START) + r'.*?' + re.escape(END) + r'\n?', re.S)
    return pat.sub('', text)


def remove_old_main_gch_entries(text: str) -> str:
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('#EXTINF:') and f'tvg-id="{TVG_ID}"' in line:
            i += 1
            while i < len(lines):
                cur = lines[i]
                if cur.startswith('#EXTINF:') or cur.startswith('## ') or cur.startswith('# ==='):
                    break
                i += 1
            continue
        out.append(line)
        i += 1
    return '\n'.join(out).rstrip() + '\n'


def build_block() -> str:
    rows = [START, '## グリーンCh']
    for name, url in SOURCES:
        rows.append(f'#EXTINF:-1 tvg-id="{TVG_ID}" tvg-logo="{LOGO}" group-title="{GROUP}",{name}')
        rows.append(url)
        rows.append('')
    rows.append(END)
    return '\n'.join(rows).rstrip() + '\n'


def insert_before_cs(text: str, block: str) -> str:
    anchor = '\n## CS\n'
    if anchor in text:
        return text.replace(anchor, '\n' + block + '\n## CS\n', 1)
    return text.rstrip() + '\n\n' + block


def main() -> None:
    if not FREEWIFI.exists():
        raise SystemExit('freewifi not found')

    text = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    text = remove_managed(text)
    text = remove_old_main_gch_entries(text)
    text = insert_before_cs(text, build_block())
    FREEWIFI.write_text(text.rstrip() + '\n', encoding='utf-8')
    print(f'Persistent Green Channel sources synced: {len(SOURCES)} routes -> {GROUP}')


if __name__ == '__main__':
    main()
