from __future__ import annotations

import base64
import html
import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from yt_dlp import YoutubeDL
from curl_cffi import requests as cffi_requests

FREEWIFI = Path('freewifi')
CONFIG = Path('kick_channels.json')
START = '# === KICK_MANAGED_START ==='
END = '# === KICK_MANAGED_END ==='
YT_ANCHOR = '# === GENERAL_YOUTUBE_MANAGED_START ==='
MIN_TOKEN_LIFETIME = 180

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151 Safari/537.36'
BASE_HEADERS = {
    'User-Agent': UA,
    'Accept': 'application/json,text/plain,*/*',
    'Origin': 'https://kick.com',
    'Cache-Control': 'no-cache, no-store, max-age=0',
    'Pragma': 'no-cache',
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


def normalize_url(value: str) -> str:
    value = html.unescape(value)
    value = value.replace('\\/', '/')
    value = value.replace('\\u0026', '&').replace('\\u002F', '/')
    return value


def recursive_m3u8(obj) -> list[str]:
    out: list[str] = []
    if isinstance(obj, dict):
        for v in obj.values():
            out.extend(recursive_m3u8(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(recursive_m3u8(v))
    elif isinstance(obj, str):
        s = normalize_url(obj)
        if s.startswith('https://') and '.m3u8' in s:
            out.append(s)
    return out


def hls_works(url: str, slug: str) -> tuple[bool, str]:
    headers = {
        'User-Agent': UA,
        'Accept': 'application/vnd.apple.mpegurl, application/x-mpegURL, */*',
        'Referer': f'https://player.kick.com/{slug}',
        'Origin': 'https://kick.com',
        'Cache-Control': 'no-cache',
    }
    try:
        r = cffi_requests.get(url, headers=headers, timeout=20, impersonate='chrome', allow_redirects=True)
        body = r.text[:8192]
        if r.status_code != 200:
            return False, f'HTTP {r.status_code}'
        return ('#EXTM3U' in body, 'OK' if '#EXTM3U' in body else 'not HLS')
    except Exception as exc:
        return False, f'{type(exc).__name__}: {exc}'


def request_json(url: str, slug: str) -> object | None:
    headers = dict(BASE_HEADERS)
    headers['Referer'] = f'https://kick.com/{slug}'
    try:
        r = cffi_requests.get(url, headers=headers, timeout=20, impersonate='chrome', allow_redirects=True)
        print(f'KICK GET {slug}: {url.split("kick.com/")[-1].split("?")[0]} -> HTTP {r.status_code}')
        if r.status_code != 200:
            return None
        return r.json()
    except Exception as exc:
        print(f'KICK GET {slug}: {type(exc).__name__}: {exc}')
        return None


def api_discovery(slug: str) -> tuple[list[tuple[str, str]], bool | None]:
    stamp = int(time.time() * 1000)
    endpoints = [
        f'https://kick.com/api/v2/channels/{slug}/playback-url?_={stamp}',
        f'https://kick.com/api/v2/channels/{slug}?_={stamp + 1}',
        f'https://kick.com/api/v2/channels/{slug}/livestream?_={stamp + 2}',
        f'https://kick.com/api/v1/channels/{slug}?_={stamp + 3}',
    ]
    found: list[tuple[str, str]] = []
    live_signal: bool | None = None
    for endpoint in endpoints:
        data = request_json(endpoint, slug)
        if data is None:
            continue
        source = endpoint.split('/api/')[-1].split('?')[0]
        for u in recursive_m3u8(data):
            found.append((u, source))
        if isinstance(data, dict):
            if data.get('is_live') is True or data.get('isLive') is True:
                live_signal = True
            if 'livestream' in data:
                if isinstance(data.get('livestream'), dict):
                    live_signal = True
                elif data.get('livestream') is None and live_signal is None:
                    live_signal = False
    return found, live_signal


def page_candidates(slug: str) -> list[tuple[str, str]]:
    stamp = int(time.time() * 1000)
    pages = [
        (f'https://player.kick.com/{slug}?_={stamp}', 'player page'),
        (f'https://kick.com/{slug}?_={stamp + 1}', 'channel page'),
    ]
    found: list[tuple[str, str]] = []
    pattern = re.compile(r'https:\\?/\\?/[^"\'<> ]+?\.m3u8[^"\'<> ]*', re.I)
    for url, source in pages:
        headers = dict(BASE_HEADERS)
        headers['Accept'] = 'text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8'
        headers['Referer'] = 'https://kick.com/'
        try:
            r = cffi_requests.get(url, headers=headers, timeout=20, impersonate='chrome', allow_redirects=True)
            print(f'KICK PAGE {slug}: {source} -> HTTP {r.status_code}')
            if r.status_code != 200:
                continue
            text = normalize_url(r.text)
            for m in pattern.findall(text):
                found.append((normalize_url(m), source))
        except Exception as exc:
            print(f'KICK PAGE {slug}: {source}: {type(exc).__name__}: {exc}')
    return found


def ytdlp_candidates(slug: str) -> list[tuple[str, str]]:
    opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'noplaylist': True,
        'extractor_retries': 2,
        'http_headers': {
            'User-Agent': UA,
            'Referer': f'https://kick.com/{slug}',
            'Cache-Control': 'no-cache',
        },
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f'https://kick.com/{slug}?_={int(time.time() * 1000)}', download=False)
    if not isinstance(info, dict):
        return []
    urls: list[str] = []
    for key in ('url', 'manifest_url'):
        value = info.get(key)
        if isinstance(value, str):
            urls.append(value)
    for f in info.get('formats') or []:
        if isinstance(f, dict):
            for key in ('manifest_url', 'url'):
                value = f.get(key)
                if isinstance(value, str):
                    urls.append(value)
    out: list[tuple[str, str]] = []
    seen = set()
    for u in urls:
        u = normalize_url(u)
        if u in seen or not u.startswith('https://') or '.m3u8' not in u:
            continue
        seen.add(u)
        out.append((u, 'yt-dlp'))
    return out


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


def validate_candidate(url: str, slug: str, expected_id: str, source: str) -> tuple[bool, str]:
    if expected_id and expected_id not in url:
        return False, f'{source}: channel ID mismatch'
    life = token_lifetime(url)
    if life is not None and life < MIN_TOKEN_LIFETIME:
        return False, f'{source}: JWT stale/too short ({life}s)'
    ok, status = hls_works(url, slug)
    if not ok:
        return False, f'{source}: HLS {status}'
    return True, f'{source} OK; JWT remaining {life if life is not None else "unknown"}s; HLS OK'


def resolve(item: dict) -> tuple[str | None, str, bool | None]:
    slug = str(item.get('slug') or '').strip()
    if not slug:
        return None, 'no fixed slug', None
    expected_id = str(item.get('channel_id') or '').strip()
    errors: list[str] = []

    api_urls, live_signal = api_discovery(slug)
    candidates: list[tuple[str, str]] = []
    candidates.extend(api_urls)
    candidates.extend(page_candidates(slug))
    try:
        candidates.extend(ytdlp_candidates(slug))
        if candidates and live_signal is None:
            live_signal = True
    except Exception as exc:
        errors.append(f'yt-dlp {type(exc).__name__}: {exc}')

    seen = set()
    for url, source in candidates:
        if url in seen:
            continue
        seen.add(url)
        ok, status = validate_candidate(url, slug, expected_id, source)
        print(f'KICK {slug}: {status}')
        if ok:
            return url, status, True if live_signal is None else live_signal
        errors.append(status)

    return None, '; '.join(errors[-8:]) or 'no fresh playable HLS candidate', live_signal


def render_block(config: list[dict]) -> tuple[str, int, list[str]]:
    lines = [START, '## KICK']
    live_count = 0
    fatal: list[str] = []
    for item in config:
        name = str(item['name'])
        url, status, live_signal = resolve(item)
        print(f'KICK {name}: {status}; live_signal={live_signal}')
        if not url:
            if live_signal is True:
                fatal.append(f'{name}: LIVE but no fresh playable HLS ({status})')
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
    return '\n'.join(lines) + '\n', live_count, fatal


def insert_block(text: str, block: str) -> str:
    if YT_ANCHOR in text:
        return text.replace(YT_ANCHOR, block + '\n' + YT_ANCHOR, 1)
    return text.rstrip() + '\n\n' + block


def validate_written_block(text: str, config: list[dict]) -> None:
    block_match = re.search(re.escape(START) + r'(.*?)' + re.escape(END), text, flags=re.S)
    if not block_match:
        raise RuntimeError('KICK managed block missing')
    block = block_match.group(1)
    for item in config:
        slug = str(item.get('slug') or '').strip()
        expected_id = str(item.get('channel_id') or '').strip()
        if not slug or not expected_id:
            continue
        for url in re.findall(r'https://[^\s]+\.m3u8\?[^\s]+', block):
            if expected_id not in url:
                continue
            life = token_lifetime(url)
            if life is not None and life < MIN_TOKEN_LIFETIME:
                raise RuntimeError(f'{slug}: refusing to publish stale JWT ({life}s)')


def main() -> int:
    original = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    if not original.startswith('#EXTM3U'):
        raise RuntimeError('freewifi lost #EXTM3U header')
    if not isinstance(config, list) or not config:
        raise RuntimeError('kick_channels.json must contain a non-empty list')

    names = {str(x['name']) for x in config}
    cleaned = strip_old_kick(original, names)
    block, live_count, fatal = render_block(config)
    if fatal:
        raise RuntimeError(' | '.join(fatal))

    updated = insert_block(cleaned, block)
    validate_written_block(updated, config)
    if updated.count('#EXTINF:') < max(50, int(original.count('#EXTINF:') * 0.70)):
        raise RuntimeError('playlist channel count collapsed')

    FREEWIFI.write_text(updated, encoding='utf-8')
    print(f'KICK managed block updated: {live_count}/{len(config)} entries')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
