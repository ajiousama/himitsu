#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess

STATUS = Path('today_boat_status.json')
SEED = Path('boat_stream_seed.m3u')

# Official race-live channels. Start with Omura, the active venue that currently
# needs a resilient fallback. Additional official venue channels can be added
# here without changing the resolver.
CHANNELS = {
    'boat.omura': ('大村', 'https://www.youtube.com/@omurainterview/live'),
}


def active_ids():
    try:
        d = json.loads(STATUS.read_text(encoding='utf-8'))
    except Exception:
        return set()
    active_names = set(d.get('active_window') or [])
    out = set()
    for tvg_id, (name, _url) in CHANNELS.items():
        if name in active_names:
            out.add(tvg_id)
    return out


def extract_hls(page):
    cmd = [
        'yt-dlp', '--no-warnings', '--no-playlist', '--get-url',
        '-f', 'best[protocol^=m3u8]/best', page,
    ]
    p = subprocess.run(cmd, text=True, capture_output=True, timeout=60)
    if p.returncode != 0:
        raise RuntimeError((p.stderr or p.stdout or 'yt-dlp failed').strip()[-800:])
    urls = [x.strip() for x in p.stdout.splitlines() if x.strip().startswith(('http://','https://'))]
    for u in urls:
        if '.m3u8' in u or 'manifest.googlevideo.com' in u:
            return u
    raise RuntimeError('yt-dlp returned no HLS URL')


def parse_existing(text):
    blocks = {}
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not line.startswith('#EXTINF:'):
            continue
        m = re.search(r'tvg-id="([^"]+)"', line)
        if not m:
            continue
        url = ''
        for j in range(i+1, min(i+5, len(lines))):
            s = lines[j].strip()
            if s.startswith(('http://','https://')):
                url = s
                break
            if s.startswith('#EXTINF:'):
                break
        if url:
            blocks[m.group(1)] = (line, url)
    return blocks


def main():
    active = active_ids()
    old = SEED.read_text(encoding='utf-8-sig', errors='replace') if SEED.exists() else '#EXTM3U\n'
    entries = parse_existing(old)

    for tvg_id in active:
        name, page = CHANNELS[tvg_id]
        try:
            hls = extract_hls(page)
        except Exception as e:
            print(f'BOAT YouTube {name}: refresh failed: {type(e).__name__}: {e}')
            continue
        entries[tvg_id] = (f'#EXTINF:-1 tvg-id="{tvg_id}",BOATRACE{name}', hls)
        print(f'BOAT YouTube {name}: refreshed HLS')

    lines = ['#EXTM3U', '']
    for tvg_id, (extinf, url) in entries.items():
        lines.extend([extinf, url, ''])
    SEED.write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
