from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
import base64
import json
import os
import re
import time
import urllib.parse
import urllib.request

JST = timezone(timedelta(hours=9))
UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1'
SEED = Path('boat_stream_seed.m3u')
FALLBACK = Path('public_sports_youtube_fallback.m3u')

VENUES = {
    '01': ('01kiryu', 'boat.kiryu', 'kiryu'),
    '02': ('02toda', 'boat.toda', 'toda'),
    '03': ('03edogawa', 'boat.edogawa', 'edogawa'),
    '04': ('04heiwajima', 'boat.heiwajima', 'heiwajima'),
    '05': ('05tamagawa', 'boat.tamagawa', 'tamagawa'),
    '06': ('06hamanako', 'boat.hamanako', 'hamanako'),
    '07': ('07gamagori', 'boat.gamagori', 'gamagori'),
    '08': ('08tokoname', 'boat.tokoname', 'tokoname'),
    '09': ('09tsu', 'boat.tsu', 'tsu'),
    '10': ('10mikuni', 'boat.mikuni', 'mikuni'),
    '11': ('11biwako', 'boat.biwako', 'biwako'),
    '12': ('12suminoe', 'boat.suminoe', 'suminoe'),
    '13': ('13amagasaki', 'boat.amagasaki', 'amagasaki'),
    '14': ('14naruto', 'boat.naruto', 'naruto'),
    '15': ('15marugame', 'boat.marugame', 'marugame'),
    '16': ('16kojima', 'boat.kojima', 'kojima'),
    '17': ('17miyajima', 'boat.miyajima', 'miyajima'),
    '18': ('18tokuyama', 'boat.tokuyama', 'tokuyama'),
    '19': ('19shimonoseki', 'boat.shimonoseki', 'shimonoseki'),
    '20': ('20wakamatsu', 'boat.wakamatsu', 'wakamatsu'),
    '21': ('21ashiya', 'boat.ashiya', 'ashiya'),
    '22': ('22fukuoka', 'boat.fukuoka', 'fukuoka'),
    '23': ('23karatsu', 'boat.karatsu', 'karatsu'),
    '24': ('24omura', 'boat.omura', 'omura'),
}

# Keep /boat-fetch from becoming an unrestricted public proxy.
ALLOWED_HOSTS = {
    'playback.api.streaks.jp',
    'manifest.streaks.jp',
    'front.player.boatrace-cdn.jp',
    'livebb.jlc.ne.jp',
    'boatrace.sakura.tv',
}
ALLOWED_SUFFIXES = (
    '.streaks.jp',
    '.boatrace-cdn.jp',
    '.jlc.ne.jp',
    '.uliza.jp',
    '.uliza.net',
    '.uliza.com',
)


def allowed_upstream(url):
    try:
        p = urllib.parse.urlsplit(url)
        host = (p.hostname or '').lower()
        return (
            p.scheme in ('http', 'https')
            and bool(host)
            and (host in ALLOWED_HOSTS or any(host.endswith(x) for x in ALLOWED_SUFFIXES))
        )
    except Exception:
        return False


def upstream_headers(url, extra=None):
    host = (urllib.parse.urlsplit(url).hostname or '').lower()
    headers = {'User-Agent': UA, 'Accept': '*/*'}
    if host.endswith('.streaks.jp') or 'boatrace-cdn.jp' in host:
        headers.update({
            'Origin': 'https://front.player.boatrace-cdn.jp',
            'Referer': 'https://front.player.boatrace-cdn.jp/',
        })
    else:
        headers['Referer'] = 'https://boatrace.sakura.tv/'
    if extra:
        headers.update(extra)
    return headers


def fetch_response(url, headers=None, timeout=15):
    req = urllib.request.Request(url, headers=headers or upstream_headers(url))
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return (
            r.read(),
            r.geturl(),
            int(getattr(r, 'status', 200)),
            {str(k).lower(): str(v) for k, v in r.headers.items()},
        )


def fetch_text(url, headers=None, timeout=12):
    data, final_url, status, _ = fetch_response(url, headers=headers, timeout=timeout)
    return data.decode('utf-8', 'replace'), final_url, status


def fetch_json(url, headers=None, timeout=12):
    text, _, _ = fetch_text(url, headers=headers, timeout=timeout)
    return json.loads(text)


def url_expired(url):
    try:
        token = (urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get('token') or [None])[0]
        if not token or token.count('.') < 2:
            return False
        payload = token.split('.')[1]
        payload += '=' * (-len(payload) % 4)
        obj = json.loads(base64.urlsafe_b64decode(payload.encode()).decode('utf-8'))
        exp = int(obj.get('exp') or 0)
        return bool(exp and exp <= int(time.time()) + 300)
    except Exception:
        return False


def parse_m3u(text):
    out = {}
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not line.startswith('#EXTINF:'):
            continue
        m = re.search(r'tvg-id="([^"]+)"', line)
        if not m:
            continue
        for j in range(i + 1, min(i + 6, len(lines))):
            u = lines[j].strip()
            if u.startswith(('http://', 'https://')):
                out[m.group(1)] = u
                break
            if u.startswith('#EXTINF:'):
                break
    return out


def file_fallback(tvg_id, slug):
    for path, key in ((SEED, tvg_id), (FALLBACK, f'youtube.boat_{slug}')):
        if not path.exists():
            continue
        try:
            entries = parse_m3u(path.read_text(encoding='utf-8-sig', errors='replace'))
            url = entries.get(key, '')
            if url and not url_expired(url):
                return url, path.name
        except Exception:
            pass
    return '', ''


def streaks_url(code, ymd):
    endpoint = (
        'https://playback.api.streaks.jp/v1/projects/cp-boatrace-prod/'
        f'medias/ref:lm-br-{code}-tokyo-{ymd}?audio_only=false'
    )
    variants = [
        {'Origin': 'https://players.streaks.jp', 'Referer': 'https://front.player.boatrace-cdn.jp/'},
        {'Origin': 'https://front.player.boatrace-cdn.jp', 'Referer': 'https://front.player.boatrace-cdn.jp/'},
        {'Referer': 'https://front.player.boatrace-cdn.jp/'},
    ]
    api_key = os.getenv('BOATRACE_STREAKS_API_KEY', '').strip()
    errors = []
    for variant in variants:
        headers = {'User-Agent': UA, 'Accept': 'application/json', **variant}
        if api_key:
            headers['X-Streaks-Api-Key'] = api_key
        try:
            data = fetch_json(endpoint, headers=headers)
            sources = data.get('sources') or []
            for item in sources:
                if isinstance(item, dict):
                    src = str(item.get('src') or '').strip()
                    if src.startswith(('http://', 'https://')):
                        return src, 'streaks-playback', errors
        except Exception as e:
            errors.append(f'{type(e).__name__}:{getattr(e, "code", "") or e}')
    return '', '', errors


def decode_html(raw):
    return raw.replace('\\u0026', '&').replace('\\x26', '&').replace('\\/', '/').replace('&amp;', '&')


def m3u8_candidates(raw, base):
    raw = decode_html(raw)
    out = []
    patterns = [
        r'https?://[^\s"\'<>]+?\.m3u8(?:\?[^\s"\'<>]*)?',
        r'["\']([^"\']+?\.m3u8(?:\?[^"\']*)?)["\']',
    ]
    for idx, pattern in enumerate(patterns):
        for m in re.finditer(pattern, raw, re.I):
            value = m.group(0) if idx == 0 else m.group(1)
            try:
                url = urllib.parse.urljoin(base, value)
            except Exception:
                continue
            if allowed_upstream(url) and url not in out:
                out.append(url)
    return out


def jlc_url(jcd):
    root = f'https://livebb.jlc.ne.jp/bb_top/sp_bb/live_{jcd}.php'
    headers = {'User-Agent': UA, 'Referer': 'https://boatrace.sakura.tv/'}
    errors = []
    try:
        page, final_url, _ = fetch_text(root, headers=headers)
        direct = m3u8_candidates(page, final_url)
        if direct:
            return direct[0], 'jlc-mobile', errors

        resources = []
        for m in re.finditer(r'(?:src|href)=["\']([^"\']+)["\']', decode_html(page), re.I):
            u = urllib.parse.urljoin(final_url, m.group(1))
            host = (urllib.parse.urlsplit(u).hostname or '').lower()
            if (
                (host == 'livebb.jlc.ne.jp' or 'uliza' in host or 'boatrace-cdn.jp' in host)
                and re.search(r'\.(?:js|php)(?:$|\?)', u, re.I)
                and u not in resources
            ):
                resources.append(u)
        for u in resources[:12]:
            try:
                body, final_resource, _ = fetch_text(u, headers=upstream_headers(u), timeout=8)
                candidates = m3u8_candidates(body, final_resource)
                if candidates:
                    return candidates[0], 'jlc-resource', errors
            except Exception as e:
                errors.append(f'{type(e).__name__}:{getattr(e, "code", "") or e}')
    except Exception as e:
        errors.append(f'{type(e).__name__}:{getattr(e, "code", "") or e}')
    return '', '', errors


def sakura_url(slug):
    root = f'https://boatrace.sakura.tv/{slug}/'
    errors = []
    try:
        page, final_url, _ = fetch_text(root, headers={'User-Agent': UA})
        candidates = m3u8_candidates(page, final_url)
        if candidates:
            return candidates[0], 'sakura', errors
    except Exception as e:
        errors.append(f'{type(e).__name__}:{getattr(e, "code", "") or e}')
    return '', '', errors


def resolve(jcd):
    code, tvg_id, slug = VENUES[jcd]
    ymd = datetime.now(JST).strftime('%Y%m%d')

    url, source, streaks_errors = streaks_url(code, ymd)
    if url:
        return url, source, {'streaks': streaks_errors}

    url, source, jlc_errors = jlc_url(jcd)
    if url:
        return url, source, {'streaks': streaks_errors, 'jlc': jlc_errors}

    url, source, sakura_errors = sakura_url(slug)
    if url:
        return url, source, {
            'streaks': streaks_errors,
            'jlc': jlc_errors,
            'sakura': sakura_errors,
        }

    url, source = file_fallback(tvg_id, slug)
    if url:
        return url, source, {
            'streaks': streaks_errors,
            'jlc': jlc_errors,
            'sakura': sakura_errors,
        }

    return '', '', {
        'streaks': streaks_errors,
        'jlc': jlc_errors,
        'sakura': sakura_errors,
    }


def normalize_jcd(path, query):
    m = re.fullmatch(r'/boat/(\d{1,2})(?:\.m3u8)?/?', path)
    value = m.group(1) if m else (query.get('venue') or query.get('jcd') or [''])[0]
    try:
        jcd = f'{int(value):02d}'
    except Exception:
        return ''
    return jcd if jcd in VENUES else ''


def public_base(handler):
    host = handler.headers.get('Host', 'ajiousama-radiko.onrender.com')
    proto = handler.headers.get('X-Forwarded-Proto', 'https')
    if proto not in ('http', 'https'):
        proto = 'https'
    return f'{proto}://{host}'


def relay_url(handler, upstream):
    return (
        public_base(handler)
        + '/boat-fetch?u='
        + urllib.parse.quote(upstream, safe='')
    )


def rewrite_playlist(text, src, handler):
    def quoted(m):
        raw = m.group(1)
        return 'URI="' + relay_url(handler, urllib.parse.urljoin(src, raw)) + '"'

    def single_quoted(m):
        raw = m.group(1)
        return "URI='" + relay_url(handler, urllib.parse.urljoin(src, raw)) + "'"

    out = []
    for line in text.splitlines():
        line = re.sub(r'URI="([^"]+)"', quoted, line)
        line = re.sub(r"URI='([^']+)'", single_quoted, line)
        stripped = line.strip()
        if stripped and not stripped.startswith('#'):
            absolute = urllib.parse.urljoin(src, stripped)
            line = relay_url(handler, absolute)
        out.append(line)
    return '\n'.join(out) + '\n'


def is_playlist(data, final_url, headers):
    ctype = (headers.get('content-type') or '').lower()
    return (
        data.lstrip().startswith(b'#EXTM3U')
        or 'mpegurl' in ctype
        or urllib.parse.urlsplit(final_url).path.lower().endswith('.m3u8')
    )


def send_raw(handler, status, data, content_type, response_headers=None, cache='no-store'):
    handler.send_response(status)
    handler.send_header('Content-Type', content_type or 'application/octet-stream')
    handler.send_header('Content-Length', str(len(data)))
    handler.send_header('Cache-Control', cache)
    handler.send_header('Access-Control-Allow-Origin', '*')
    if response_headers:
        for key in ('accept-ranges', 'content-range'):
            if response_headers.get(key):
                handler.send_header('-'.join(x.title() for x in key.split('-')), response_headers[key])
    handler.end_headers()
    handler.wfile.write(data)


def relay_upstream(handler, upstream):
    if not allowed_upstream(upstream):
        raise ValueError('upstream host is not allowed')

    extra = {}
    request_range = handler.headers.get('Range')
    if request_range:
        extra['Range'] = request_range

    data, final_url, status, headers = fetch_response(
        upstream,
        headers=upstream_headers(upstream, extra=extra),
        timeout=18,
    )

    if not allowed_upstream(final_url):
        raise ValueError('redirected upstream host is not allowed')

    if is_playlist(data, final_url, headers):
        text = data.decode('utf-8', 'replace')
        body = rewrite_playlist(text, final_url, handler).encode('utf-8')
        send_raw(
            handler,
            200,
            body,
            'application/vnd.apple.mpegurl; charset=utf-8',
            cache='no-store',
        )
        return

    ctype = headers.get('content-type') or 'application/octet-stream'
    send_raw(
        handler,
        status,
        data,
        ctype,
        response_headers=headers,
        cache='public, max-age=5',
    )


def handle_request(handler):
    split = urllib.parse.urlsplit(handler.path)
    query = urllib.parse.parse_qs(split.query)

    if split.path == '/boat-fetch':
        upstream = (query.get('u') or [''])[0]
        if not upstream or not allowed_upstream(upstream):
            handler.send_bytes(400, b'invalid BOAT upstream\n', 'text/plain; charset=utf-8')
            return True
        try:
            relay_upstream(handler, upstream)
        except Exception as e:
            body = f'BOAT relay failed: {type(e).__name__}: {e}\n'.encode()
            handler.send_bytes(502, body, 'text/plain; charset=utf-8')
        return True

    if not (split.path.startswith('/boat/') or split.path == '/boat'):
        return False

    jcd = normalize_jcd(split.path, query)
    if not jcd:
        handler.send_bytes(400, b'invalid BOAT venue\n', 'text/plain; charset=utf-8')
        return True

    url, source, details = resolve(jcd)

    if (query.get('debug') or [''])[0] == '1':
        probe = None
        playable = False
        if url:
            try:
                data, final_url, status, headers = fetch_response(
                    url,
                    headers=upstream_headers(url),
                    timeout=10,
                )
                playable = is_playlist(data, final_url, headers) and status in (200, 206)
                probe = {
                    'status': status,
                    'final_url': final_url,
                    'content_type': headers.get('content-type', ''),
                    'playlist': playable,
                }
            except Exception as e:
                probe = {'error': f'{type(e).__name__}:{getattr(e, "code", "") or e}'}
        body = json.dumps(
            {
                'ok': bool(url),
                'playable': playable,
                'relay': True,
                'venue': jcd,
                'source': source,
                'url': url,
                'probe': probe,
                'details': details,
            },
            ensure_ascii=False,
            indent=2,
        ).encode()
        handler.send_bytes(200 if url and playable else 503, body, 'application/json; charset=utf-8')
        return True

    if not url:
        handler.send_bytes(
            503,
            b'#EXTM3U\n# BOAT stream unavailable\n',
            'application/vnd.apple.mpegurl; charset=utf-8',
        )
        return True

    try:
        relay_upstream(handler, url)
    except Exception as e:
        body = (
            '#EXTM3U\n'
            f'# BOAT relay error: {type(e).__name__}: {e}\n'
        ).encode()
        handler.send_bytes(502, body, 'application/vnd.apple.mpegurl; charset=utf-8')
    return True
