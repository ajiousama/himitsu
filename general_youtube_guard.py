from pathlib import Path
import json
import re
import subprocess

PLAYLIST = Path('general_youtube.m3u')
FREEWIFI = Path('freewifi')
COOKIES = Path('youtube_cookies.txt')
START = '# === GENERAL_YOUTUBE_MANAGED_START ==='
END = '# === GENERAL_YOUTUBE_MANAGED_END ==='

TOKYO_ID = 'youtube.tokyo_dome_city'
TOKYO_PAGE = 'https://www.youtube.com/watch?v=7XzfKy8CzdY'
OMOGO_ID = 'youtube.ehime_omogo_ishizuchi'
OMOGO_CHANNEL = 'https://www.youtube.com/channel/UCOgv-XV9OOR_3E99aNMokHw'


def base_cmd():
    cmd = ['yt-dlp', '--js-runtimes', 'node', '--no-warnings', '--no-cache-dir', '--socket-timeout', '10', '--retries', '1']
    if COOKIES.exists() and COOKIES.stat().st_size > 20:
        cmd += ['--cookies', str(COOKIES)]
    return cmd


def direct_hls(page):
    cmd = base_cmd() + ['--no-playlist', '--match-filter', 'is_live', '-f', 'best[protocol^=m3u8]/best', '-g', page]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return None
    urls = [x.strip() for x in p.stdout.splitlines() if x.strip().startswith(('http://', 'https://'))]
    return urls[0] if p.returncode == 0 and len(urls) == 1 else None


def official_channel_live(channel):
    for listing in (channel.rstrip('/') + '/streams', channel.rstrip('/') + '/videos'):
        cmd = base_cmd() + ['--flat-playlist', '--dump-json', '--playlist-end', '30', listing]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
        except subprocess.TimeoutExpired:
            continue
        if p.returncode != 0:
            continue
        for line in p.stdout.splitlines():
            try:
                item = json.loads(line)
            except Exception:
                continue
            if (item.get('live_status') or '').lower() != 'is_live':
                continue
            vid = item.get('id')
            if not vid:
                continue
            hls = direct_hls('https://www.youtube.com/watch?v=' + vid)
            if hls:
                return hls
    return None


def parse_entries(text):
    lines = text.splitlines()
    header = lines[0] if lines and lines[0].startswith('#EXTM3U') else '#EXTM3U'
    entries = []
    i = 1 if lines and lines[0].startswith('#EXTM3U') else 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith('#EXTINF:'):
            i += 1
            continue
        ext = line
        i += 1
        while i < len(lines) and not lines[i].strip():
            i += 1
        url = lines[i].strip() if i < len(lines) else ''
        i += 1
        m = re.search(r'tvg-id="([^"]+)"', ext)
        cid = m.group(1) if m else ''
        entries.append([cid, ext, url])
    return header, entries


def set_group(ext, group):
    if 'group-title="' in ext:
        return re.sub(r'group-title="[^"]*"', f'group-title="{group}"', ext, count=1)
    return ext.replace(',', f' group-title="{group}",', 1)


def render(header, entries):
    out = [header, '']
    for _, ext, url in entries:
        out += [ext, url, '']
    return '\n'.join(out).rstrip() + '\n'


def sync_freewifi(general):
    if not FREEWIFI.exists():
        return
    base = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    body = '\n'.join(general.splitlines()[1:]).strip()
    block = START + '\n' + body + '\n' + END if body else START + '\n' + END
    pat = re.compile(re.escape(START) + r'.*?' + re.escape(END), re.S)
    if pat.search(base):
        base = pat.sub(block, base)
    else:
        base = base.rstrip() + '\n\n' + block + '\n'
    FREEWIFI.write_text(base, encoding='utf-8')


def main():
    if not PLAYLIST.exists():
        raise SystemExit('general_youtube.m3u not found')

    text = PLAYLIST.read_text(encoding='utf-8-sig', errors='replace')
    header, entries = parse_entries(text)

    # 空港名を含む一般YouTubeチャンネルは「交通」ではなく「空港」に統一。
    for entry in entries:
        if '空港' in entry[1]:
            entry[1] = set_group(entry[1], '空港')

    # 東京ドームシティは公式固定配信だけを採用。検索ヒットへの置換は禁止。
    tokyo = direct_hls(TOKYO_PAGE)
    # 面河・石鎚山系は久万高原町役場ふるさと創生課の公式チャンネル内LIVEだけを採用。
    omogo = official_channel_live(OMOGO_CHANNEL)

    strict = {TOKYO_ID: tokyo, OMOGO_ID: omogo}
    found = set()
    kept = []
    for cid, ext, url in entries:
        if cid in strict:
            found.add(cid)
            good = strict[cid]
            if not good:
                print(f'STRICT REMOVE: {cid} (official LIVE unavailable)')
                continue
            url = good
            print(f'STRICT OK: {cid}')
        kept.append([cid, ext, url])

    # 元プレイリストに無かった場合も、勝手に別候補を追加しない。
    general = render(header, kept)
    PLAYLIST.write_text(general, encoding='utf-8')
    sync_freewifi(general)
    print('Airport groups normalized:', sum(1 for _, ext, _ in kept if 'group-title="空港"' in ext))


if __name__ == '__main__':
    main()
