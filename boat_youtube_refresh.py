#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess

STATUS = Path('today_boat_status.json')
SEED = Path('boat_stream_seed.m3u')
COOKIES = Path('youtube_cookies.txt')

CHANNELS = {
    'boat.omura': ('大村', 'https://www.youtube.com/@omurainterview/live'),
}


def active_ids():
    try:
        d = json.loads(STATUS.read_text(encoding='utf-8'))
    except Exception:
        return set()
    active_names = set(d.get('active_window') or [])
    return {tvg_id for tvg_id, (name, _url) in CHANNELS.items() if name in active_names}


def command():
    cmd = ['yt-dlp', '--js-runtimes', 'node', '--no-warnings', '--no-cache-dir']
    if COOKIES.exists() and COOKIES.stat().st_size > 20:
        cmd += ['--cookies', str(COOKIES)]
    return cmd


def extract_hls(page):
    errors = []
    for selector in ('best[protocol^=m3u8]', 'best'):
        try:
            p = subprocess.run(
                command() + [
                    '--extractor-args', 'youtube:player_client=default,web_safari,web',
                    '--no-playlist', '--match-filter', 'is_live',
                    '-f', selector, '-g', page,
                ],
                text=True, capture_output=True, timeout=40,
            )
        except subprocess.TimeoutExpired:
            errors.append('timeout')
            continue
        urls = [x.strip() for x in p.stdout.splitlines() if x.strip().startswith(('http://', 'https://'))]
        for u in urls:
            if '.m3u8' in u or 'manifest.googlevideo.com' in u:
                return u
        errors.append((p.stderr or p.stdout or f'yt-dlp rc={p.returncode}').strip()[-800:])
        low = (p.stderr or '').lower()
        if '429' in low or 'too many requests' in low or 'sign in to confirm' in low:
            break
    raise RuntimeError(' | '.join(x for x in errors if x)[-1200:] or 'no HLS URL')


def parse_existing(text):
    blocks = {}
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not line.startswith('#EXTINF:'):
            continue
        m = re.search(r'tvg-id="([^"]+)"', line)
        if not m:
            continue
        for j in range(i + 1, min(i + 5, len(lines))):
            s = lines[j].strip()
            if s.startswith(('http://', 'https://')):
                blocks[m.group(1)] = (line, s)
                break
            if s.startswith('#EXTINF:'):
                break
    return blocks


def main():
    active = active_ids()
    old = SEED.read_text(encoding='utf-8-sig', errors='replace') if SEED.exists() else '#EXTM3U\n'
    entries = parse_existing(old)
    successes = 0
    skipped_primary = 0

    for tvg_id in active:
        name, page = CHANNELS[tvg_id]
        current = entries.get(tvg_id)
        if current and 'manifest.streaks.jp' in current[1]:
            skipped_primary += 1
            print(f'BOAT YouTube {name}: skipped; Streaks primary is available')
            continue
        try:
            hls = extract_hls(page)
        except Exception as e:
            print(f'BOAT YouTube {name}: refresh failed: {type(e).__name__}: {e}')
            continue
        entries[tvg_id] = (f'#EXTINF:-1 tvg-id="{tvg_id}",BOATRACE{name}', hls)
        successes += 1
        print(f'BOAT YouTube {name}: refreshed emergency HLS')

    lines = ['#EXTM3U', '']
    for _tvg_id, (extinf, url) in entries.items():
        lines.extend([extinf, url, ''])
    SEED.write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8')
    print(f'BOAT YouTube refresh successes={successes} skipped_streaks={skipped_primary} active_targets={len(active)} cookies={COOKIES.exists()}')


if __name__ == '__main__':
    main()
