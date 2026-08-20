from pathlib import Path
import json, re, subprocess

SRC = Path('general_youtube_sources.json')
OUT = Path('general_youtube.m3u')
FREEWIFI = Path('freewifi')
COOKIES = Path('youtube_cookies.txt')
LOG = Path('general_youtube_run_latest.txt')
START = '# === GENERAL_YOUTUBE_MANAGED_START ==='
END = '# === GENERAL_YOUTUBE_MANAGED_END ==='


def run(cmd, timeout=120):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def base_cmd():
    cmd = ['yt-dlp', '--js-runtimes', 'node', '--no-warnings']
    if COOKIES.exists() and COOKIES.stat().st_size > 20:
        cmd += ['--cookies', str(COOKIES)]
    return cmd


def direct_url(page):
    selectors = [
        'best[protocol^=m3u8][vcodec!=none][acodec!=none]',
        '96/95/94/93/92/91',
        'best[protocol^=m3u8]',
        'best',
    ]
    errors = []
    for sel in selectors:
        p = run(base_cmd() + [
            '--extractor-args', 'youtube:player_client=default,web_safari',
            '--no-playlist', '--match-filter', 'is_live', '-f', sel, '-g', page
        ])
        urls = [x.strip() for x in p.stdout.splitlines()
                if x.strip().startswith(('http://', 'https://'))]
        if p.returncode == 0 and urls:
            # yt-dlp can return separate video/audio URLs. Prefer an HLS URL;
            # otherwise use the first playable URL instead of rejecting >1 URLs.
            for u in urls:
                if '.m3u8' in u or 'manifest' in u:
                    return u, ''
            return urls[0], ''
        if p.stderr.strip():
            errors.append(p.stderr.strip().splitlines()[-1])
    return None, (errors[-1] if errors else 'no playable URL')


def search_live(query):
    p = run(base_cmd() + [
        '--flat-playlist', '--dump-json', '--playlist-end', '6', f'ytsearch6:{query}'
    ], 120)
    pages = []
    for line in p.stdout.splitlines():
        try:
            item = json.loads(line)
        except Exception:
            continue
        vid = item.get('id')
        if vid:
            pages.append('https://www.youtube.com/watch?v=' + vid)
    last_error = p.stderr.strip().splitlines()[-1] if p.stderr.strip() else 'search returned no LIVE'
    for page in pages:
        try:
            u, err = direct_url(page)
        except Exception as e:
            u, err = None, str(e)
        if u:
            return u, ''
        if err:
            last_error = err
    return None, last_error


def build():
    items = json.loads(SRC.read_text(encoding='utf-8'))
    out = ['#EXTM3U', '']
    got, failed = [], []
    seen = set()
    for item in items:
        url = None
        error = ''
        page = item.get('page')
        if page:
            try:
                url, error = direct_url(page)
            except Exception as e:
                error = str(e)
        if not url:
            q = item.get('query') or item.get('name')
            try:
                url, error = search_live(q)
            except Exception as e:
                error = str(e)
        if not url:
            failed.append((item['name'], error or 'not live / not found'))
            continue
        key = url.split('?')[0]
        if key in seen:
            failed.append((item['name'], 'duplicate URL'))
            continue
        seen.add(key)
        tvg = item['id']
        name = item['name']
        group = item.get('group', '一般YouTube LIVE')
        out.append(f'#EXTINF:-1 tvg-id="{tvg}" tvg-name="{name}" group-title="{group}",{name}')
        out.append(url)
        out.append('')
        got.append(name)
    text = '\n'.join(out).rstrip() + '\n'
    return text, got, failed


def merge_freewifi(general):
    base = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace') if FREEWIFI.exists() else '#EXTM3U\n'
    pattern = re.compile(re.escape(START) + r'.*?' + re.escape(END), re.S)
    body = '\n'.join(general.splitlines()[1:]).strip()
    block = START + '\n' + body + '\n' + END
    if pattern.search(base):
        merged = pattern.sub(block, base)
    else:
        merged = base.rstrip() + '\n\n' + block + '\n'
    FREEWIFI.write_text(merged, encoding='utf-8')


def main():
    previous = OUT.read_text(encoding='utf-8', errors='replace') if OUT.exists() else '#EXTM3U\n'
    text, got, failed = build()
    lines = [f'General YouTube LIVE: {len(got)} / {len(got)+len(failed)}']
    lines += [f' + {n}' for n in got]
    lines += [f' - {n}: {e}' for n, e in failed]
    LOG.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines))

    # Never destroy a previously working playlist/freewifi block on a zero-result run.
    if not got:
        print('ZERO LIVE: keeping previous general_youtube.m3u and freewifi unchanged')
        if not OUT.exists():
            OUT.write_text(previous, encoding='utf-8')
        return 2

    OUT.write_text(text, encoding='utf-8')
    merge_freewifi(text)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
