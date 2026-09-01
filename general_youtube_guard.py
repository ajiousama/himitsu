from pathlib import Path
import json
import re
import subprocess

PLAYLIST = Path('general_youtube.m3u')
FREEWIFI = Path('freewifi')
SOURCE = Path('general_youtube_sources.json')
COOKIES = Path('youtube_cookies.txt')
START = '# === GENERAL_YOUTUBE_MANAGED_START ==='
END = '# === GENERAL_YOUTUBE_MANAGED_END ==='

# These IDs remain in the master list for reference but must never be emitted.
DENY_IDS = {'youtube.kobe_waterfront2', 'youtube.narita_t1'}

# Reported feeds that must never fall back to a broad YouTube search result.
# Fixed-video sources are long-running official/verified camera pages.
STRICT_DIRECT_PAGES = {
    'youtube.tokyo_dome_city': 'https://www.youtube.com/watch?v=7XzfKy8CzdY',
    'youtube.uwajima': 'https://www.youtube.com/watch?v=aJcTvBuj5AA',
    'youtube.tokyo_haneda': 'https://www.youtube.com/watch?v=LZlHg3vzwe0',
}

# Rotating LIVE URLs are resolved only inside the intended broadcaster channel.
STRICT_CHANNELS = {
    'youtube.ehime_omogo_ishizuchi': 'https://www.youtube.com/channel/UCOgv-XV9OOR_3E99aNMokHw',
    'youtube.kyoto_rail': 'https://www.youtube.com/@Radio171',
}


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
        if not lines[i].startswith('#EXTINF:'):
            i += 1
            continue
        ext = lines[i]
        i += 1
        while i < len(lines) and not lines[i].strip():
            i += 1
        url = lines[i].strip() if i < len(lines) else ''
        i += 1
        m = re.search(r'tvg-id="([^"]+)"', ext)
        entries.append([m.group(1) if m else '', ext, url])
    return header, entries


def allowed_source_ids():
    if not SOURCE.exists():
        raise SystemExit('general_youtube_sources.json not found')
    items = json.loads(SOURCE.read_text(encoding='utf-8'))
    return {
        (item.get('id') or '').strip()
        for item in items
        if (item.get('id') or '').strip()
        and item.get('enabled', True)
        and (item.get('id') or '').strip() not in DENY_IDS
    }


def set_group(ext, group):
    if 'group-title="' in ext:
        return re.sub(r'group-title="[^"]*"', f'group-title="{group}"', ext, count=1)
    return ext.replace(',', f' group-title="{group}",', 1)


def group_title(ext):
    m = re.search(r'group-title="([^"]+)"', ext)
    return m.group(1).strip() if m else ''


def youtube_video_id(url):
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
    logo = logo_url(ext)
    if not logo:
        return None
    base = logo.rsplit('/', 1)[-1].split('?', 1)[0]
    nums = re.findall(r'(?<![A-Za-z])\d+(?![A-Za-z])', base)
    return int(nums[-1]) if nums else None


def sort_group_by_logo_number(entries, group):
    positions = [i for i, (_, ext, _) in enumerate(entries) if group_title(ext) == group]
    if len(positions) < 2:
        return entries
    selected = [entries[i] for i in positions]
    original_order = {id(entry): n for n, entry in enumerate(selected)}

    def key(entry):
        _, ext, _ = entry
        n = logo_sort_number(ext)
        return (0, original_order[id(entry)]) if n is None else (1, n, original_order[id(entry)])

    selected.sort(key=key)
    out = list(entries)
    for pos, entry in zip(positions, selected):
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
    allowed = allowed_source_ids()

    # Critical: a quality-gate rollback may restore an older M3U. Never keep IDs
    # that have since been deleted/disabled from the current source list.
    source_kept = []
    source_pruned = 0
    for cid, ext, url in entries:
        if not cid or cid not in allowed:
            print(f'SOURCE REMOVE: {cid or "(no tvg-id)"} ({entry_name(ext)})')
            source_pruned += 1
            continue
        source_kept.append([cid, ext, url])
    entries = source_kept

    # Airport feeds always live in the dedicated airport group.
    for entry in entries:
        if '空港' in entry[1]:
            entry[1] = set_group(entry[1], '空港')

    # Reported feeds are allowed only from the intended fixed video/channel.
    strict = {cid: direct_hls(page) for cid, page in STRICT_DIRECT_PAGES.items()}
    strict.update({cid: official_channel_live(channel) for cid, channel in STRICT_CHANNELS.items()})
    strict_kept = []
    for cid, ext, url in entries:
        if cid in strict:
            good = strict[cid]
            if not good:
                print(f'STRICT REMOVE: {cid} (intended LIVE unavailable)')
                continue
            url = good
            print(f'STRICT OK: {cid}')
        strict_kept.append([cid, ext, url])

    # Remove duplicate tvg-id, exact URL and YouTube video ID.
    seen_cid = set()
    seen_url = set()
    seen_video = {}
    kept = []
    duplicate_count = 0
    for cid, ext, url in strict_kept:
        url_key = url.split('?', 1)[0] if url else ''
        if cid in seen_cid:
            print(f'DUPLICATE ID REMOVE: {cid} ({entry_name(ext)})')
            duplicate_count += 1
            continue
        if url_key and url_key in seen_url:
            print(f'DUPLICATE URL REMOVE: {cid} ({entry_name(ext)})')
            duplicate_count += 1
            continue
        vid = youtube_video_id(url)
        if vid and vid in seen_video:
            first_cid, first_name = seen_video[vid]
            print(f'DUPLICATE VIDEO REMOVE: {cid} ({entry_name(ext)}) -> {first_cid} ({first_name})')
            duplicate_count += 1
            continue
        seen_cid.add(cid)
        if url_key:
            seen_url.add(url_key)
        if vid:
            seen_video[vid] = (cid, entry_name(ext))
        kept.append([cid, ext, url])

    for group, label in [('動物', 'Animal'), ('空港', 'Airport')]:
        before = [entry_name(ext) for _, ext, _ in kept if group_title(ext) == group]
        kept = sort_group_by_logo_number(kept, group)
        after = [entry_name(ext) for _, ext, _ in kept if group_title(ext) == group]
        if before != after:
            print(f'{label} order:', ' -> '.join(after))

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

    print('Source-deleted/disabled entries removed:', source_pruned)
    print('Airport groups normalized:', sum(1 for _, ext, _ in kept if 'group-title="空港"' in ext))
    print('Duplicate YouTube entries removed:', duplicate_count)
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
