from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen

from yt_dlp import YoutubeDL

try:
    from curl_cffi import requests as cffi_requests
except Exception:
    cffi_requests = None

FREEWIFI = Path('freewifi')
CONFIG = Path('kick_channels.json')
START = '# === KICK_MANAGED_START ==='
END = '# === KICK_MANAGED_END ==='
YT_ANCHOR = '# === GENERAL_YOUTUBE_MANAGED_START ==='
MIN_TOKEN_LIFETIME = 120

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151 Safari/537.36',
    'Accept': 'application/json,text/plain,*/*',
    'Referer': 'https://kick.com/',
    'Origin': 'https://kick.com',
    'Cache-Control': 'no-cache',
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


def hls_works(url: str, slug: str) -> tuple[bool, str]:
    headers = {
        'User-Agent': HEADERS['User-Agent'],
        'Accept': 'application/vnd.apple.mpegurl, application/x-mpegURL, */*',
        'Referer': f'https://kick.com/{slug}',
        'Origin': 'https://kick.com',
        'Cache-Control': 'no-cache',
    }
    try:
        if cffi_requests is not None:
            r = cffi_requests.get(url, headers=headers, timeout=20, impersonate='chrome', allow_redirects=True)
            body = r.text[:8192]
            if r.status_code != 200:
                return False, f'HTTP {r.status_code}'
            return ('#EXTM3U' in body, 'OK' if '#EXTM3U' in body else 'not HLS')
        req = Request(url, headers=headers)
        with urlopen(req, timeout=20) as r:
            status = getattr(r, 'status', 200)
            body = r.read(8192).decode('utf-8', errors='replace')
        if status != 200:
            return False, f'HTTP {status}'
        return ('#EXTM3U' in body, 'OK' if '#EXTM3U' in body else 'not HLS')
    except Exception as exc:
        return False, f'{type(exc).__name__}: {exc}'


def recursive_m3u8(obj) -> list[str]:
    out: list[str] = []
    if isinstance(obj, dict):
        for v in obj.values():
            out.extend(recursive_m3u8(v))
    elif isinstance(obj, list):
        for v in obj:
            out.extend(recursive_m3u8(v))
    elif isinstance(obj, str):
        s = obj.replace('\\/', '/')
        if s.startswith('https://') and '.m3u8' in s:
            out.append(s)
    return out


def api_candidates(slug: str) -> list[tuple[str, str]]:
    if cffi_requests is None:
        return []
    stamp = int(time.time() * 1000)
    endpoints = [
        f'https://kick.com/api/v2/channels/{slug}?_={stamp}',
        f'https://kick.com/api/v2/channels/{slug}/livestream?_={stamp}',
        f'https://kick.com/api/v1/channels/{slug}?_={stamp}',
    ]
    found: list[tuple[str, str]] = []
    for endpoint in endpoints:
        try:
            r = cffi_requests.get(endpoint, headers=HEADERS, timeout=20, impersonate='chrome', allow_redirects=True)
            print(f'KICK API {slug}: {endpoint.split("/api/")[-1].split("?")[0]} -> HTTP {r.status_code}')
            if r.status_code != 200:
                continue
            data = r.json()
            for u in recursive_m3u8(data):
                found.append((u, endpoint))
        except Exception as exc:
            print(f'KICK API {slug}: {type(exc).__name__}: {exc}')
    return found


def ytdlp_candidates(slug: str) -> list[tuple[str, str]]:
    opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'noplaylist': True,
        'http_headers': {
            'User-Agent': HEADERS['User-Agent'],
            'Referer': f'https://kick.com/{slug}',
        },
    }
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f'https://kick.com/{slug}', download=False)
    if not isinstance(info, dict):
        return []
    urls: list[str] = []
    for key in ('url', 'manifest_url'):
        v = info.get(key)
        if isinstance(v, str):
            urls.append(v)
    for f in info.get('formats') or []:
        if isinstance(f, dict):
            for key in ('manifest_url', 'url'):
                v = f.get(key)
                if isinstance(v, str):
                    urls.append(v)
    seen = set()
    out = []
    for u in urls:
        u = u.replace('\\/', '/')
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
        return False, f'{source}: JWT too short ({life}s)'
    ok, status = hls_works(url, slug)
    if not ok:
        return False, f'{source}: HLS {status}'
    return True, f'{source} OK; JWT remaining {life if life is not None else "unknown"}s; HLS OK'


def resolve(item: dict, previous: str | None) -> tuple[str | None, str]:
    slug = str(item.get('slug') or '').strip()
    if not slug:
        return None, 'no fixed slug'
    expected_id = str(item.get('channel_id') or '').strip()

    errors: list[str] = []
    candidates: list[tuple[str, str]] = []

    # First use KICK's channel JSON directly with Chrome TLS/browser impersonation.
    candidates.extend(api_candidates(slug))

    # Then use yt-dlp's maintained KICK extractor, which also uses impersonated requests.
    try:
        candidates.extend(ytdlp_candidates(slug))
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
            return url, status
        errors.append(status)

    if previous:
        ok, status = validate_candidate(previous, slug, expected_id, 'previous')
        if ok:
            return previous, status
        errors.append(status)

    return None, '; '.join(errors[-6:]) or 'no playable HLS candidate'


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
