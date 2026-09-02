from pathlib import Path
import re
import subprocess

OUT = Path('public_sports_youtube_fallback.m3u')
COOKIES = Path('youtube_cookies.txt')
LOCAL_DEFAULT_LOGO = 'https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/youtube/youtube_live_camera_default.png'
SOURCES = [
    {
        'id': 'youtube.boat_kiryu',
        'name': 'BOATRACE桐生（公式LIVE予備）',
        'page': 'https://www.youtube.com/channel/UCT2pRt_me0tOA8B2sakEv7Q/live',
        'logo': LOCAL_DEFAULT_LOGO,
    },
    {
        'id': 'youtube.boat_suminoe',
        'name': 'BOATRACE住之江（公式LIVE予備）',
        'page': 'https://www.youtube.com/channel/UCW3AReETO-oDmEoE-m3i7dQ/live',
        'logo': LOCAL_DEFAULT_LOGO,
    },
]


def command():
    cmd = ['yt-dlp', '--js-runtimes', 'node', '--no-warnings', '--no-cache-dir']
    if COOKIES.exists() and COOKIES.stat().st_size > 20:
        cmd += ['--cookies', str(COOKIES)]
    return cmd


def resolve_live(page):
    for selector in ('best[protocol^=m3u8]', 'best'):
        try:
            proc = subprocess.run(
                command() + [
                    '--extractor-args', 'youtube:player_client=default,web_safari,web',
                    '--no-playlist', '--match-filter', 'is_live',
                    '-f', selector, '-g', page,
                ],
                capture_output=True, text=True, timeout=35,
            )
        except subprocess.TimeoutExpired:
            continue
        urls = [line.strip() for line in proc.stdout.splitlines()
                if line.strip().startswith(('http://', 'https://'))]
        if proc.returncode == 0 and len(urls) == 1:
            return urls[0]
        low = (proc.stderr or '').lower()
        if '429' in low or 'too many requests' in low or 'sign in to confirm' in low:
            break
    return None


def existing_entries():
    if not OUT.exists():
        return {}
    lines = OUT.read_text(encoding='utf-8-sig', errors='replace').splitlines()
    entries = {}
    i = 0
    while i < len(lines):
        if not lines[i].startswith('#EXTINF:'):
            i += 1
            continue
        block = [lines[i]]
        j = i + 1
        while j < len(lines) and not lines[j].startswith('#EXTINF:'):
            if lines[j].strip():
                block.append(lines[j])
            j += 1
        match = re.search(r'tvg-id="([^"]+)"', lines[i])
        if match:
            entries[match.group(1)] = block
        i = j
    return entries


def normalize_preserved_block(block, source):
    """Keep a last-known-good URL but refresh metadata to local-only values."""
    if not block:
        return []
    url = next((line.strip() for line in block[1:]
                if line.strip().startswith(('http://', 'https://'))), None)
    if not url:
        return []
    extinf = (
        f'#EXTINF:-1 tvg-id="{source["id"]}" tvg-name="{source["name"]}" '
        f'tvg-logo="{source["logo"]}" group-title="今日の開催場",{source["name"]}'
    )
    return [extinf, url]


def main():
    previous = existing_entries()
    output = ['#EXTM3U', '']
    successes = 0
    preserved = 0
    for source in SOURCES:
        url = resolve_live(source['page'])
        if url:
            output += [
                f'#EXTINF:-1 tvg-id="{source["id"]}" tvg-name="{source["name"]}" '
                f'tvg-logo="{source["logo"]}" group-title="今日の開催場",{source["name"]}',
                url,
                '',
            ]
            successes += 1
            print(f'Fallback LIVE OK: {source["name"]}')
        elif source['id'] in previous:
            block = normalize_preserved_block(previous[source['id']], source)
            if block:
                output.extend(block)
                output.append('')
                preserved += 1
                print(f'Fallback LIVE preserved: {source["name"]}')
            else:
                print(f'Fallback LIVE unavailable: {source["name"]}')
        else:
            print(f'Fallback LIVE unavailable: {source["name"]}')
    OUT.write_text('\n'.join(output).rstrip() + '\n', encoding='utf-8')
    print(f'Public sports fallback: live={successes}, preserved={preserved}')


if __name__ == '__main__':
    main()
