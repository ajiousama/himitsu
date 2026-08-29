from pathlib import Path
import json
import re
import urllib.request

FREEWIFI = Path('freewifi')
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36'

CHANNELS = [
    {
        'tvg_id': 'kick.gccx',
        'name': 'ゲームセンターＣＸ(KICK)',
        # Current KICK channel carrying GameCenter CX, followed by legacy guesses.
        'slugs': ['mirumo-ch', 'gccx', 'gamecentercx', 'gamecenter-cx'],
    },
    {
        'tvg_id': 'kick.nogizaka',
        'name': '乃木坂(KICK)',
        'slugs': ['nogi20110821'],
    },
]


def request_text(url):
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': UA,
            'Accept': 'application/json,text/plain,*/*',
            'Referer': 'https://kick.com/',
            'Cache-Control': 'no-cache',
        },
    )
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode('utf-8', errors='replace')


def find_playback(obj):
    if isinstance(obj, dict):
        for key in ('playback_url', 'playbackUrl', 'source', 'src'):
            value = obj.get(key)
            if isinstance(value, str) and '.m3u8' in value:
                return value.replace('\\/', '/')
        for value in obj.values():
            hit = find_playback(value)
            if hit:
                return hit
    elif isinstance(obj, list):
        for value in obj:
            hit = find_playback(value)
            if hit:
                return hit
    return None


def extract_playback(text):
    try:
        hit = find_playback(json.loads(text))
        if hit:
            return hit
    except Exception:
        pass

    patterns = [
        r'"playback_url"\s*:\s*"([^"]+\.m3u8[^"]*)"',
        r'"playbackUrl"\s*:\s*"([^"]+\.m3u8[^"]*)"',
        r'(https?:\\?/\\?/[A-Za-z0-9._~:/?#\[\]@!$&\'()*+,;=%-]+\.m3u8[A-Za-z0-9._~:/?#\[\]@!$&\'()*+,;=%-]*)',
    ]
    for pattern in patterns:
        m = re.search(pattern, text)
        if m:
            return m.group(1).replace('\\/', '/')
    return None


def resolve_slug(slug):
    # KICK has changed its web API more than once. Try current and legacy read-only endpoints,
    # then the public channel/player pages as a final fallback.
    urls = [
        f'https://kick.com/api/v2/channels/{slug}',
        f'https://kick.com/api/v1/channels/{slug}',
        f'https://api.kick.com/private/v1/channels/{slug}',
        f'https://kick.com/{slug}',
        f'https://player.kick.com/{slug}',
    ]
    errors = []
    for url in urls:
        try:
            text = request_text(url)
            hit = extract_playback(text)
            if hit:
                return hit, url
        except Exception as e:
            errors.append(f'{url}: {type(e).__name__}')
    return None, '; '.join(errors)


def patch_entry(text, tvg_id, new_url):
    lines = text.splitlines()
    changed = False
    found = False
    for i, line in enumerate(lines):
        if line.startswith('#EXTINF:') and f'tvg-id="{tvg_id}"' in line:
            found = True
            if i + 1 >= len(lines):
                raise RuntimeError(f'{tvg_id}: EXTINF has no URL line')
            if lines[i + 1].strip() != new_url:
                lines[i + 1] = new_url
                changed = True
            break
    if not found:
        raise RuntimeError(f'{tvg_id}: entry not found in freewifi')
    return '\n'.join(lines).rstrip() + '\n', changed


def main():
    original = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    text = original
    refreshed = 0
    changed_count = 0

    for ch in CHANNELS:
        resolved = None
        source = None
        for slug in ch['slugs']:
            url, info = resolve_slug(slug)
            if url:
                resolved = url
                source = info
                break
        if not resolved:
            print(f"::warning::{ch['name']}: KICK playback URL not resolved; leaving previous URL in place")
            continue
        text, changed = patch_entry(text, ch['tvg_id'], resolved)
        refreshed += 1
        changed_count += int(changed)
        print(f"{ch['name']}: refreshed via {source} changed={changed}")

    if not text.startswith('#EXTM3U'):
        raise RuntimeError('Refusing to write: #EXTM3U header disappeared')
    if text.count('#EXTINF:') < 50:
        raise RuntimeError('Refusing to write: suspicious channel-count collapse')

    if text != original:
        FREEWIFI.write_text(text, encoding='utf-8')

    print(f'KICK refresh complete: resolved={refreshed}/{len(CHANNELS)}, changed={changed_count}')
    # Do not fail the whole FreeWiFi build if KICK itself blocks GitHub Actions temporarily.
    # The previous entry remains intact and will be retried on the next 15-minute cycle.


if __name__ == '__main__':
    main()
