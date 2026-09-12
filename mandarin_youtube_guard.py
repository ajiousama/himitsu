#!/usr/bin/env python3
from pathlib import Path
import json
import re
import subprocess

CHANNEL_ID = 'youtube.ehime_mandarin'
CHANNEL_NAME = '愛媛マンダリンパイレーツ'
CHANNEL_PAGE = 'https://www.youtube.com/@EhimeMandarinPirates/live'
CHANNEL_STREAMS = 'https://www.youtube.com/@EhimeMandarinPirates/streams'
LOGO = 'https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/youtube/yt43_32_ehime_mandarin.png'
GROUP = '愛媛県内ライブカメラ'
GENERAL = Path('general_youtube.m3u')
FREEWIFI = Path('freewifi')
COOKIES = Path('youtube_cookies.txt')
START = '# === GENERAL_YOUTUBE_MANAGED_START ==='
END = '# === GENERAL_YOUTUBE_MANAGED_END ==='


def base_cmd():
    cmd = ['yt-dlp', '--js-runtimes', 'node', '--no-warnings', '--no-cache-dir', '--socket-timeout', '10', '--retries', '1']
    if COOKIES.exists() and COOKIES.stat().st_size > 20:
        cmd += ['--cookies', str(COOKIES)]
    return cmd


def run(args, timeout=35):
    return subprocess.run(base_cmd() + args, capture_output=True, text=True, timeout=timeout)


def restricted(stderr: str) -> bool:
    s = (stderr or '').lower()
    return any(x in s for x in ['429', 'too many requests', 'rate limit', 'sign in to confirm you', 'not a bot', 'cookies are no longer valid'])


def extract_live_url(video_url: str):
    p = run(['--no-playlist', '--match-filter', 'is_live', '-f', 'best[protocol^=m3u8]/best', '-g', video_url])
    urls = [x.strip() for x in p.stdout.splitlines() if x.strip().startswith(('http://', 'https://'))]
    if p.returncode == 0 and urls:
        return urls[0], 'LIVE'
    if restricted(p.stderr):
        return None, 'UNKNOWN'
    s = (p.stderr or '').lower()
    if 'not currently live' in s or 'is not live' in s or 'this live event will begin' in s:
        return None, 'OFFLINE'
    return None, 'UNKNOWN'


def probe_official_channel():
    # First try the official channel /live endpoint.
    url, state = extract_live_url(CHANNEL_PAGE)
    if url:
        return url, 'LIVE'
    if state == 'UNKNOWN':
        return None, 'UNKNOWN'

    # Confirm against the official streams listing so search results can never keep a stale/wrong stream alive.
    p = run(['--flat-playlist', '--dump-json', '--playlist-end', '20', CHANNEL_STREAMS])
    if p.returncode != 0:
        return (None, 'UNKNOWN') if restricted(p.stderr) else (None, 'OFFLINE')

    live_ids = []
    for line in p.stdout.splitlines():
        try:
            item = json.loads(line)
        except Exception:
            continue
        if (item.get('live_status') or '').lower() == 'is_live' and item.get('id'):
            live_ids.append(item['id'])

    if not live_ids:
        return None, 'OFFLINE'

    for vid in live_ids:
        url, state = extract_live_url('https://www.youtube.com/watch?v=' + vid)
        if url:
            return url, 'LIVE'
        if state == 'UNKNOWN':
            return None, 'UNKNOWN'
    return None, 'OFFLINE'


def strip_entry(text: str) -> str:
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('#EXTINF:') and f'tvg-id="{CHANNEL_ID}"' in line:
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i < len(lines) and lines[i].strip().startswith(('http://', 'https://')):
                i += 1
            continue
        out.append(line)
        i += 1
    return '\n'.join(out).rstrip() + '\n'


def entry(url: str) -> str:
    return (
        f'#EXTINF:-1 tvg-id="{CHANNEL_ID}" tvg-name="{CHANNEL_NAME}" '
        f'tvg-logo="{LOGO}" group-title="{GROUP}",{CHANNEL_NAME}\n{url}\n'
    )


def update_general(url: str | None):
    text = GENERAL.read_text(encoding='utf-8-sig', errors='replace') if GENERAL.exists() else '#EXTM3U\n'
    text = strip_entry(text)
    if url:
        lines = text.splitlines()
        if lines and lines[0].startswith('#EXTM3U'):
            text = lines[0] + '\n\n' + entry(url) + '\n'.join(lines[1:]).lstrip('\n')
        else:
            text = '#EXTM3U\n\n' + entry(url) + text
    GENERAL.write_text(text.rstrip() + '\n', encoding='utf-8')


def update_freewifi(url: str | None):
    if not FREEWIFI.exists():
        return
    text = strip_entry(FREEWIFI.read_text(encoding='utf-8-sig', errors='replace'))
    if url:
        block_entry = entry(url).rstrip() + '\n'
        if END in text:
            text = text.replace(END, block_entry + END, 1)
        else:
            text = text.rstrip() + '\n' + START + '\n' + block_entry + END + '\n'
    FREEWIFI.write_text(text.rstrip() + '\n', encoding='utf-8')


def main():
    url, state = probe_official_channel()
    print(f'Mandarin official YouTube state: {state}')
    if state == 'UNKNOWN':
        print('Probe inconclusive; preserving current entries to avoid a false removal.')
        return
    if state == 'LIVE' and url:
        update_general(url)
        update_freewifi(url)
        print('Mandarin LIVE present; official URL applied to general_youtube.m3u and freewifi.')
    else:
        update_general(None)
        update_freewifi(None)
        print('Mandarin YouTube LIVE ended/offline; stale entries removed from general_youtube.m3u and freewifi.')


if __name__ == '__main__':
    main()
