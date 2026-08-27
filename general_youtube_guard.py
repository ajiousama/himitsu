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


def group_title(ext):
    m = re.search(r'group-title="([^"]+)"', ext)
    return m.group(1).strip() if m else ''


def youtube_video_id(url):
    """Extract stable YouTube video id from googlevideo HLS or YouTube URL."""
    if not url:
        return None
    m = re.search(r'/id/([A-Za-z0-9_-]{11})(?:\.|/|$)', url)
    if m:
        return m.group(1)
    m = re.search(r'[?&]v=([A-Za-z0-9_-]{11})(?:&|$)', url)
    if m:
        return m.group(1)
    m = re.search(r'youtu\.be/([A-Za-z0-9_-]{11})(?:\?|/|$)', url)
    return m.group(1) if m else None


def entry_name(ext):
    if ',' in ext:
        return ext.rsplit(',', 1)[-1].strip()
    m = re.search(r'tvg-name="([^"]+)"', ext)
    return m.group(1) if m else ext


def logo_url(ext):
    m = re.search(r'tvg-logo="([^"]+)"', ext)
    return m.group(1).strip() if m else ''


def logo_sort_number(ext):
    """Return a stable number from the logo basename, or None if it has no number.

    Existing YouTube logos often use names such as yt43_02_natsu_shiba.png.
    For the animal group, non-numbered logos stay first; numbered logos are
    placed afterwards and ordered by the last numeric token in the basename.
    """
    logo = logo_url(ext)
    if not logo:
        return None
    base = logo.rsplit('/', 1)[-1].split('?', 1)[0]
    nums = re.findall(r'(?<![A-Za-z])\d+(?![A-Za-z])', base)
    return int(nums[-1]) if nums else None


def sort_animals(entries):
    animal_positions = [i for i, (_, ext, _) in enumerate(entries) if group_title(ext) == '動物']
    if len(animal_positions) < 2:
        return entries

    animals = [entries[i] for i in animal_positions]
    original_order = {id(entry): n for n, entry in enumerate(animals)}

    def key(entry):
        _, ext, _ = entry
        n = logo_sort_number(ext)
        # ロゴ番号なしを先、番号ありは後ろ。番号あり同士は数字順。
        if n is None:
            return (0, original_order[id(entry)])
        return (1, n, original_order[id(entry)])

    animals.sort(key=key)
    out = list(entries)
    for pos, entry in zip(animal_positions, animals):
        out[pos] = entry
    return out


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
    strict_kept = []
    for cid, ext, url in entries:
        if cid in strict:
            good = strict[cid]
            if not good:
                print(f'STRICT REMOVE: {cid} (official LIVE unavailable)')
                continue
            url = good
            print(f'STRICT OK: {cid}')
        strict_kept.append([cid, ext, url])

    # 最終出力で同じYouTube動画IDを複数チャンネル名に使わない。
    # 品質ゲートで旧M3Uが戻った場合もここで必ず重複を落とす。
    seen_video = {}
    kept = []
    duplicate_count = 0
    for cid, ext, url in strict_kept:
        vid = youtube_video_id(url)
        if vid and vid in seen_video:
            first_cid, first_name = seen_video[vid]
            print(f'DUPLICATE REMOVE: {cid} ({entry_name(ext)}) -> same video {vid} as {first_cid} ({first_name})')
            duplicate_count += 1
            continue
        if vid:
            seen_video[vid] = (cid, entry_name(ext))
        kept.append([cid, ext, url])

    # 動物グループだけを、そのグループ内で並べ替える。
    # ロゴに番号がないものを先、番号入りロゴは後回しにし、番号順を優先する。
    before_animals = [entry_name(ext) for _, ext, _ in kept if group_title(ext) == '動物']
    kept = sort_animals(kept)
    after_animals = [entry_name(ext) for _, ext, _ in kept if group_title(ext) == '動物']
    if before_animals != after_animals:
        print('Animal order:', ' -> '.join(after_animals))

    # ロゴ指定を最終検査。欠落はログで明示し、Actions検証で見落とさない。
    missing_logos = []
    default_logos = []
    for cid, ext, _ in kept:
        logo = logo_url(ext)
        if not logo:
            missing_logos.append((cid, entry_name(ext)))
        elif 'youtube_live_camera_default' in logo:
            default_logos.append((cid, entry_name(ext)))

    general = render(header, kept)
    PLAYLIST.write_text(general, encoding='utf-8')
    sync_freewifi(general)

    print('Airport groups normalized:', sum(1 for _, ext, _ in kept if 'group-title="空港"' in ext))
    print('Duplicate YouTube videos removed:', duplicate_count)
    print('Entries with logo:', len(kept) - len(missing_logos), '/', len(kept))
    if missing_logos:
        for cid, name in missing_logos:
            print(f'LOGO MISSING: {cid} ({name})')
        raise SystemExit(f'Logo validation failed: {len(missing_logos)} entries have no tvg-logo')
    if default_logos:
        print('Default-logo entries:', len(default_logos))
        for cid, name in default_logos:
            print(f'LOGO DEFAULT: {cid} ({name})')


if __name__ == '__main__':
    main()
