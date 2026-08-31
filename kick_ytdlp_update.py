from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from yt_dlp import YoutubeDL

FREEWIFI = Path('freewifi')
CONFIG = Path('kick_channels.json')
START = '# === KICK_MANAGED_START ==='
END = '# === KICK_MANAGED_END ==='
YT_ANCHOR = '# === GENERAL_YOUTUBE_MANAGED_START ==='
MIN_TOKEN_LIFETIME = 180

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151 Safari/537.36',
    'Accept': 'application/vnd.apple.mpegurl, application/x-mpegURL, */*',
    'Referer': 'https://kick.com/',
    'Origin': 'https://kick.com',
    'Cache-Control': 'no-cache',
}


def jwt_exp(url: str) -> int | None:
    try:
        token = (parse_qs(urlparse(url).query).get('token') or [None])[0]
        if not token or token.count('.') < 2:
            return None
        payload = token.split('.')[1]
        payload += '=' * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode()).decode('utf-8'))
        return int(data['exp']) if 'exp' in data else None
    except Exception:
        return None


def token_lifetime(url: str) -> int | None:
    exp = jwt_exp(url)
    return exp - int(time.time()) if exp is not None else None


def hls_works(url: str, slug: str) -> tuple[bool, str]:
    headers = dict(HEADERS)
    headers['Referer'] = f'https://kick.com/{slug}'
    req = Request(url, headers=headers)
    try:
        with urlopen(req, timeout=20) as r:
            status = getattr(r, 'status', 200)
            body = r.read(4096).decode('utf-8', errors='replace')
        if status != 200:
            return False, f'HTTP {status}'
        return ('#EXTM3U' in body, 'OK' if '#EXTM3U' in body else 'not HLS')
    except Exception as exc:
        return False, type(exc).__name__


def ytdlp_info(slug: str) -> dict:
    opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'noplaylist': True,
        'http_headers': {
            'User-Agent': HEADERS['User-Agent'],
            'Referer': f'https://kick.com/{slug}',
        },
        'extractor_args': {'kick': {'client': ['web']}},
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f'https://kick.com/{slug}', download=False)
    if not isinstance(info, dict):
        raise RuntimeError('yt-dlp returned unexpected result')
    return info


def pick_hls(info: dict) -> str | None:
    urls: list[str] = []
    for key in ('url', 'manifest_url'):
        value = info.get(key)
        if isinstance(value, str):
            urls.append(value)
    formats = info.get('formats') or []
    if isinstance(formats, list):
        for f in formats:
            if not isinstance(f, dict):
                continue
            for key in ('manifest_url', 'url'):
                value = f.get(key)
                if isinstance(value, str):
                    urls.append(value)
    seen = set()
    for u in urls:
        u = u.replace('\\/', '/')
        if u in seen:
            continue
        seen.add(u)
        if u.startswith('https://') and '.m3u8' in u:
            return u
    return None


def existing_kick_urls(text: str, names: set[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    lines = text.splitlines()
    for i, line in enumerate(lines[:-1]):
        if not line.startswith('#EXTINF:') or ',' not in line:
            continue
        name = line.rsplit(',', 1)[-1].strip()
        if name not in names:
            continue
        url = lines[i + 1].strip()
        if url.startswith('https://') and '.m3u8' in url:
            found[name] = url
    return found


def strip_old_kick(text: str, names: set[str]) -> str:
    text = re.sub(re.escape(START) + r'.*?' + re.escape(END) + r'\n?', '', text, flags=re.S)
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('#EXTINF:') and i + 1 < len(lines):
            name = line.rsplit(',', 1)[-1].strip() if ',' in line else ''
            if name in names:
                i += 2
                continue
        out.append(line)
        i += 1
    return '\n'.join(out).rstrip() + '\n'


def resolve(item: dict, previous: str | None) -> tuple[str | None, str]:
    slug = str(item.get('slug') or '').strip()
    if not slug:
        return None, 'no fixed slug'
    expected_id = str(item.get('channel_id') or '').strip()
    try:
        info = ytdlp_info(slug)
        url = pick_hls(info)
        if not url:
            return None, 'yt-dlp: offline or no HLS URL'
        if expected_id and expected_id not in url:
            return None, f'channel ID mismatch: expected {expected_id}'
        life = token_lifetime(url)
        if life is not None and life < MIN_TOKEN_LIFETIME:
            return None, f'fresh URL token too short: {life}s'
        ok, status = hls_works(url, slug)
        if not ok:
            return None, f'HLS check failed: {status}'
        return url, f'yt-dlp OK; JWT remaining {life if life is not None else "unknown"}s; HLS OK'
    except Exception as exc:
        if previous:
            life = token_lifetime(previous)
            ok, _ = hls_works(previous, slug) if (life is None or life > 0) else (False, 'expired')
            if ok:
                return previous, f'yt-dlp failed ({type(exc).__name__}); valid previous URL kept'
        return None, f'yt-dlp failed: {type(exc).__name__}: {exc}'


def render_block(config: list[dict], existing: dict[str, str]) -> tuple[str, int]:
    lines = [START, '## KICK']
    live_count = 0
    for item in config:
        name = str(item['name'])
        url, status = resolve(item, existing.get(name))
        print(f'KICK {name}: {status}')
        if not url:
            continue
        meta = '#EXTINF:-1 group-title="その他"'
        tvg_id = str(item.get('tvg_id') or '').strip()
        logo = str(item.get('logo') or '').strip()
        if tvg_id:
            meta += f' tvg-id="{tvg_id}"'
        if logo:
            meta += f' tvg-logo="{logo}"'
        lines.extend([f'{meta},{name}', url])
        live_count += 1
    lines.append(END)
    return '\n'.join(lines) + '\n', live_count


def insert_block(text: str, block: str) -> str:
    if YT_ANCHOR in text:
        return text.replace(YT_ANCHOR, block + '\n' + YT_ANCHOR, 1)
    return text.rstrip() + '\n\n' + block


def main() -> int:
    original = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    if not original.startswith('#EXTM3U'):
        raise RuntimeError('freewifi lost #EXTM3U header')
    if not isinstance(config, list) or not config:
        raise RuntimeError('kick_channels.json must contain a non-empty list')
    names = {str(x['name']) for x in config}
    existing = existing_kick_urls(original, names)
    cleaned = strip_old_kick(original, names)
    block, live_count = render_block(config, existing)
    updated = insert_block(cleaned, block)
    if updated.count('#EXTINF:') < max(50, int(original.count('#EXTINF:') * 0.70)):
        raise RuntimeError('playlist channel count collapsed')
    FREEWIFI.write_text(updated, encoding='utf-8')
    print(f'KICK managed block updated: {live_count}/{len(config)} entries')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
