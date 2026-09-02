from __future__ import annotations

from pathlib import Path
import base64
import json
import re
import time
from urllib.parse import parse_qs, urlsplit

import boat_v2_build as b

STATUS = Path('today_boat_status.json')
STATE = Path('boat_v2_state.json')
SEED = Path('boat_stream_seed.m3u')
FREEWIFI = Path('freewifi')
HEALTHY_CODES = {200, 503}


def token_expired(url):
    try:
        token = (parse_qs(urlsplit(url).query).get('token') or [None])[0]
        if not token or token.count('.') < 2:
            return False
        payload = token.split('.')[1]
        payload += '=' * (-len(payload) % 4)
        obj = json.loads(base64.urlsafe_b64decode(payload.encode()).decode('utf-8'))
        exp = int(obj.get('exp') or 0)
        return bool(exp and exp <= int(time.time()) + 300)
    except Exception:
        return False


def seed_urls():
    if not SEED.exists():
        return {}
    lines = SEED.read_text(encoding='utf-8-sig', errors='replace').splitlines()
    out = {}
    for i, line in enumerate(lines):
        if not line.startswith('#EXTINF:'):
            continue
        m = re.search(r'tvg-id="([^"]+)"', line)
        if not m:
            continue
        for j in range(i + 1, min(i + 5, len(lines))):
            url = lines[j].strip()
            if url.startswith(('http://', 'https://')):
                if not token_expired(url):
                    out[m.group(1)] = url
                break
            if url.startswith('#EXTINF:'):
                break
    return out


def replace_boat_block(text, payload):
    pat = re.compile(re.escape(b.START) + r'.*?' + re.escape(b.END) + r'\n?', re.S)
    if pat.search(text):
        return pat.sub(payload + '\n', text, count=1)
    return text.rstrip() + '\n\n' + payload + '\n'


def main():
    if not STATUS.exists() or not FREEWIFI.exists():
        raise SystemExit('BOAT V2 status/freewifi missing')

    d = json.loads(STATUS.read_text(encoding='utf-8'))
    code = int(d.get('resolver_probe_status') or 0)
    if code in HEALTHY_CODES:
        print(f'BOAT V2 Render guard: healthy probe={code}')
        return 0

    d['resolver_ready'] = False
    seeds = seed_urls()
    rows = []
    for tvg_id, item in (d.get('venues') or {}).items():
        if item.get('stream_window') != 'live_or_vtr':
            item['visible'] = False
            continue
        url = seeds.get(tvg_id, '')
        if not url:
            item['visible'] = False
            item['source'] = f'Render unhealthy ({code}); no safe fallback'
            item.pop('url', None)
            continue
        item['visible'] = True
        item['url'] = url
        item['source'] = f'valid seed fallback while Render unhealthy ({code})'
        name = item.get('name') or tvg_id
        jcd = item.get('jcd') or ''
        venue = b.VENUES.get(jcd)
        if not venue:
            continue
        _venue_name, _tvg_id, logo = venue
        rows.append((name, tvg_id, logo, url, item.get('next_race')))

    def sort_key(row):
        nr = row[4]
        if nr:
            h, m = map(int, nr['start'].split(':'))
            return (0, h * 60 + m, row[0])
        return (1, 9999, row[0])

    rows.sort(key=sort_key)
    body = []
    for name, tvg_id, logo, url, _nr in rows:
        body.append(f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="BOATRACE{name}" tvg-logo="{logo}" group-title="{b.GROUP}",BOATRACE{name}')
        body.append(url)
        body.append('')
    managed = b.START + '\n## 今日の開催場 / BOAT v2 fallback\n' + '\n'.join(body).rstrip() + ('\n' if body else '') + b.END

    text = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    FREEWIFI.write_text(replace_boat_block(text, managed).rstrip() + '\n', encoding='utf-8')
    d['visible_count'] = len(rows)
    d['resolver_guard'] = f'unhealthy probe={code}; safe fallback only'
    STATUS.write_text(json.dumps(d, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    STATE.write_text(json.dumps(d, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'BOAT V2 Render guard: unhealthy probe={code}; fallback_visible={len(rows)} active={d.get("held_count")}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
