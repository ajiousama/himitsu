from pathlib import Path
import re

FREEWIFI = Path('freewifi')

JRA_YT_LOGO = 'https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/youtube/jra_youtube_free.jpg'
JRA_GCH_LOGO = 'https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/youtube/jra_gch_free.jpg'
GUINEA_LOGO = 'https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/youtube/guinea_youtube.jpg'
GUINEA_PAGE = 'https://www.youtube.com/watch?v=sYCG1BPYWXk'
GCH_URL = 'https://manifest.streaks.jp/v4/gch-jra/97d99803d82b49bd9fc73cb568b219df/a214b09df7e04c22a15b4feba869b01d/hls/v3/manifest.m3u8?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJwcCI6IjNhZWVhMzU2ZmQ0MzQyMzE4ZjRhNDg2OWUwMzFiMDZiIiwiZGMiOiJjYTlmZDAwYTRiMmU0YTg1OGEyNmM1MTY5ZDIwY2U0ZiIsImVkZ2UiOiIzYjY5ZGJiYjYwMmI0M2NlODFmYjdkNGI3NjE0NjEzMCIsImNvZGVjcyI6ImF1dG8iLCJleHAiOjE3ODc1NDA0MDAsImlvcyI6MTgsInBwdyI6IjRwaiJ9.5EL6z0Gaoaj0haNQ3B1tui-B5vpNbxdb0t3dTHYFySE'

GCH_START = '# === JRA_GCH_FREE_START ==='
GCH_END = '# === JRA_GCH_FREE_END ==='
GUINEA_START = '# === GUINEA_YOUTUBE_START ==='
GUINEA_END = '# === GUINEA_YOUTUBE_END ==='


def replace_managed_block(text, start, end, block, anchor='## 競馬\n'):
    pat = re.compile(re.escape(start) + r'.*?' + re.escape(end) + r'\n?', re.S)
    text = pat.sub('', text)
    if block:
        if anchor in text:
            text = text.replace(anchor, anchor + '\n' + block + '\n', 1)
        else:
            text = text.rstrip() + '\n\n' + block + '\n'
    return text


def patch_jra_youtube(text):
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith('#EXTINF:') and 'tvg-id="jra.official"' in line:
            lines[i] = (
                '#EXTINF:-1 tvg-id="jra.official" '
                'tvg-name="JRA公式（YouTube）無料版" '
                f'tvg-logo="{JRA_YT_LOGO}" group-title="競馬",'
                'JRA公式（YouTube）無料版'
            )
    return '\n'.join(lines).rstrip() + '\n'


def get_guinea_hls():
    try:
        from general_youtube_update import direct_url
        url, _ = direct_url(GUINEA_PAGE)
        return url
    except Exception as e:
        print('Guinea LIVE lookup failed:', e)
        return None


def main():
    text = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    text = patch_jra_youtube(text)

    gch_extinf = (
        '#EXTINF:-1 tvg-id="jra.gch.free" '
        'tvg-name="JRA公式（GCH）無料版【開催中のみ】" '
        f'tvg-logo="{JRA_GCH_LOGO}" group-title="競馬",'
        'JRA公式（GCH）無料版【開催中のみ】'
    )
    gch_block = f'{GCH_START}\n{gch_extinf}\n{GCH_URL}\n{GCH_END}'
    text = replace_managed_block(text, GCH_START, GCH_END, gch_block, '## 競馬\n')

    guinea_url = get_guinea_hls()
    if guinea_url:
        guinea_extinf = (
            '#EXTINF:-1 tvg-id="youtube.guinea" '
            'tvg-name="モルモット配信（YouTube）" '
            f'tvg-logo="{GUINEA_LOGO}" group-title="動物",'
            'モルモット配信（YouTube）'
        )
        guinea_block = f'{GUINEA_START}\n{guinea_extinf}\n{guinea_url}\n{GUINEA_END}'
    else:
        guinea_block = ''
    text = replace_managed_block(text, GUINEA_START, GUINEA_END, guinea_block, '# === GENERAL_YOUTUBE_MANAGED_END ===\n')

    FREEWIFI.write_text(text.rstrip() + '\n', encoding='utf-8')
    print('Custom FreeWiFi channels applied')

    try:
        from freewifi_today_public_sports import main as sync_today_public_sports
        sync_today_public_sports()
    except Exception as e:
        print('Today public sports sync failed:', e)


if __name__ == '__main__':
    main()
