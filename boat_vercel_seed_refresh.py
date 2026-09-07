#!/usr/bin/env python3
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

SEED = Path('boat_stream_seed.m3u')
JST = timezone(timedelta(hours=9))
ENDPOINT = 'https://himitsu-six.vercel.app/api/boat-seed?venue={jcd}'
UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1'

VENUES = {
    '01': ('桐生', 'boat.kiryu'), '02': ('戸田', 'boat.toda'),
    '03': ('江戸川', 'boat.edogawa'), '04': ('平和島', 'boat.heiwajima'),
    '05': ('多摩川', 'boat.tamagawa'), '06': ('浜名湖', 'boat.hamanako'),
    '07': ('蒲郡', 'boat.gamagori'), '08': ('常滑', 'boat.tokoname'),
    '09': ('津', 'boat.tsu'), '10': ('三国', 'boat.mikuni'),
    '11': ('びわこ', 'boat.biwako'), '12': ('住之江', 'boat.suminoe'),
    '13': ('尼崎', 'boat.amagasaki'), '14': ('鳴門', 'boat.naruto'),
    '15': ('丸亀', 'boat.marugame'), '16': ('児島', 'boat.kojima'),
    '17': ('宮島', 'boat.miyajima'), '18': ('徳山', 'boat.tokuyama'),
    '19': ('下関', 'boat.shimonoseki'), '20': ('若松', 'boat.wakamatsu'),
    '21': ('芦屋', 'boat.ashiya'), '22': ('福岡', 'boat.fukuoka'),
    '23': ('唐津', 'boat.karatsu'), '24': ('大村', 'boat.omura'),
}


def token_start_day(url: str):
    try:
        token = (urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get('token') or [None])[0]
        if not token or token.count('.') < 2:
            return None
        payload = token.split('.')[1]
        payload += '=' * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode()).decode('utf-8'))
        start = int(data.get('start') or 0)
        if not start:
            return None
        return datetime.fromtimestamp(start, JST).date()
    except Exception:
        return None


def is_today_streaks(url: str, today) -> bool:
    return (
        isinstance(url, str)
        and url.startswith('https://manifest.streaks.jp/')
        and '.m3u8' in url
        and token_start_day(url) == today
    )


def parse_existing():
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
                out[m.group(1)] = (line, url)
                break
            if url.startswith('#EXTINF:'):
                break
    return out


def fetch_one(jcd: str):
    url = ENDPOINT.format(jcd=jcd)
    req = urllib.request.Request(
        url,
        headers={
            'User-Agent': UA,
            'Accept': 'application/json',
            'Cache-Control': 'no-cache, no-store',
            'Pragma': 'no-cache',
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            status = int(getattr(r, 'status', 200))
            raw = r.read().decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return jcd, '', f'HTTP {e.code}'
    except Exception as e:
        return jcd, '', f'{type(e).__name__}:{e}'

    if status != 200:
        return jcd, '', f'HTTP {status}'
    try:
        data = json.loads(raw)
    except Exception as e:
        return jcd, '', f'JSON {type(e).__name__}:{e}'
    hit = str(data.get('url') or '') if data.get('ok') is True else ''
    return jcd, hit, '' if hit else f'no seed region={data.get("region")}'


def main():
    today = datetime.now(JST).date()
    existing = parse_existing()
    merged = {}

    # Keep only already-known current-day direct Streaks entries as fallback.
    for jcd, (name, tvg_id) in VENUES.items():
        old = existing.get(tvg_id)
        if old and is_today_streaks(old[1], today):
            merged[tvg_id] = old

    fetched = 0
    failures = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(fetch_one, jcd): jcd for jcd in VENUES}
        for future in as_completed(futures):
            jcd, hit, error = future.result()
            name, tvg_id = VENUES[jcd]
            if hit and is_today_streaks(hit, today):
                extinf = existing.get(tvg_id, (f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="BOATRACE{name}" group-title="ボートレース",BOATRACE{name}', ''))[0]
                merged[tvg_id] = (extinf, hit)
                fetched += 1
                print(f'VERCEL BOAT {name}: current-day seed OK')
            else:
                if hit:
                    error = f'rejected seed start={token_start_day(hit)}'
                failures.append(f'{name}:{error}')

    # Route may still be undeployed/rate-limited. In that case leave the seed
    # byte-for-byte untouched so the iPhone fallback remains authoritative.
    if fetched == 0:
        print('VERCEL BOAT: no current-day seeds fetched; existing seed left unchanged')
        if failures:
            print('VERCEL BOAT sample failures:', ' | '.join(failures[:6]))
        return 0

    lines = ['#EXTM3U', '']
    for _jcd, (_name, tvg_id) in VENUES.items():
        block = merged.get(tvg_id)
        if block:
            lines.extend([block[0], block[1], ''])
    new_text = '\n'.join(lines).rstrip() + '\n'
    old_text = SEED.read_text(encoding='utf-8-sig', errors='replace') if SEED.exists() else ''
    if new_text != old_text:
        SEED.write_text(new_text, encoding='utf-8')
        print(f'VERCEL BOAT: seed updated fetched={fetched} total_current={len(merged)}/24')
    else:
        print(f'VERCEL BOAT: seed already current fetched={fetched} total_current={len(merged)}/24')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
