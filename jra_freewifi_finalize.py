from pathlib import Path
import json, re, subprocess

FREEWIFI = Path('freewifi')
GENERAL = Path('general_youtube.m3u')
START = '# === JRA_OFFICIAL_YOUTUBE_START ==='
END = '# === JRA_OFFICIAL_YOUTUBE_END ==='
JRA_ID = 'jra.official'
SEARCH_TITLE = '中央競馬全レース中継'


def find_jra_live_by_title():
    """YouTubeでタイトルを検索し、JRA公式の放送中LIVEだけを採用する。"""
    try:
        p = subprocess.run(
            ['yt-dlp', '--flat-playlist', '--dump-json', '--playlist-end', '10',
             f'ytsearch10:{SEARCH_TITLE} JRA公式'],
            capture_output=True, text=True, timeout=90
        )
        candidates = []
        for line in p.stdout.splitlines():
            try:
                item = json.loads(line)
            except Exception:
                continue
            title = item.get('title') or ''
            channel = item.get('channel') or item.get('uploader') or ''
            vid = item.get('id')
            if vid and SEARCH_TITLE in title and ('JRA' in channel.upper() or 'JRA公式' in title):
                candidates.append('https://www.youtube.com/watch?v=' + vid)

        from general_youtube_update import direct_url
        for page in candidates:
            url, _ = direct_url(page, 'JRA公式（YouTube）無料版')
            if url:
                return url
    except Exception as e:
        print('JRA title search failed:', e)
    return None


def extract_jra_entry(text):
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith('#EXTINF:') and f'tvg-id="{JRA_ID}"' in line:
            if i + 1 < len(lines) and lines[i + 1].strip().startswith(('http://', 'https://')):
                return line.strip(), lines[i + 1].strip()
    return None


def remove_jra_from_managed(text):
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('#EXTINF:') and f'tvg-id="{JRA_ID}"' in line:
            i += 2
            if i < len(lines) and not lines[i].strip():
                i += 1
            continue
        out.append(line)
        i += 1
    return '\n'.join(out).rstrip() + '\n'


def main():
    if not FREEWIFI.exists():
        raise SystemExit('freewifi not found')

    base = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    general = GENERAL.read_text(encoding='utf-8-sig', errors='replace') if GENERAL.exists() else ''

    # 固定URLや検索順位ではなく「中央競馬全レース中継」をYouTube内検索して
    # JRA公式かつ現在LIVEの動画を優先する。
    title_url = find_jra_live_by_title()
    entry = extract_jra_entry(general)
    if title_url:
        if entry:
            extinf, _ = entry
        else:
            extinf = '#EXTINF:-1 tvg-id="jra.official" tvg-name="JRA公式（YouTube）無料版" group-title="競馬",JRA公式（YouTube）無料版'
        entry = (extinf, title_url)

    managed_pat = re.compile(re.escape(START) + r'.*?' + re.escape(END) + r'\n?', re.S)
    had_managed = bool(managed_pat.search(base))
    base = managed_pat.sub('', base)
    base = remove_jra_from_managed(base)

    if entry:
        extinf, url = entry
        legacy = re.compile(
            r'#EXTINF:[^\n]*グリーンチャンネル\(無料版\)[^\n]*\n[^\n]*\n?', re.M
        )
        block = f'{START}\n{extinf}\n{url}\n{END}\n'
        if legacy.search(base):
            base = legacy.sub(block, base, count=1)
        else:
            race_header = '## 競馬\n'
            if race_header in base:
                base = base.replace(race_header, race_header + '\n' + block, 1)
            else:
                base = base.rstrip() + '\n\n' + block
        print('JRA official YouTube LIVE installed by title search:', SEARCH_TITLE)
    elif had_managed:
        print('JRA official YouTube is not LIVE; expired managed entry removed')
    else:
        print('JRA official YouTube is not LIVE yet; legacy free-version entry kept until first successful LIVE')

    FREEWIFI.write_text(base.rstrip() + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
