#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
import base64
import json
import re
import urllib.parse
import urllib.request

JST = timezone(timedelta(hours=9))
OUT = Path('boat_stream_seed.m3u')
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36'
HEADERS = {
    'Origin': 'https://front.player.boatrace-cdn.jp',
    'Referer': 'https://front.player.boatrace-cdn.jp/',
    'User-Agent': UA,
    'Accept': '*/*',
}
VENUES = {
    '01': ('01kiryu', 'boat.kiryu', '桐生'), '02': ('02toda', 'boat.toda', '戸田'),
    '03': ('03edogawa', 'boat.edogawa', '江戸川'), '04': ('04heiwajima', 'boat.heiwajima', '平和島'),
    '05': ('05tamagawa', 'boat.tamagawa', '多摩川'), '06': ('06hamanako', 'boat.hamanako', '浜名湖'),
    '07': ('07gamagori', 'boat.gamagori', '蒲郡'), '08': ('08tokoname', 'boat.tokoname', '常滑'),
    '09': ('09tsu', 'boat.tsu', '津'), '10': ('10mikuni', 'boat.mikuni', '三国'),
    '11': ('11biwako', 'boat.biwako', 'びわこ'), '12': ('12suminoe', 'boat.suminoe', '住之江'),
    '13': ('13amagasaki', 'boat.amagasaki', '尼崎'), '14': ('14naruto', 'boat.naruto', '鳴門'),
    '15': ('15marugame', 'boat.marugame', '丸亀'), '16': ('16kojima', 'boat.kojima', '児島'),
    '17': ('17miyajima', 'boat.miyajima', '宮島'), '18': ('18tokuyama', 'boat.tokuyama', '徳山'),
    '19': ('19shimonoseki', 'boat.shimonoseki', '下関'), '20': ('20wakamatsu', 'boat.wakamatsu', '若松'),
    '21': ('21ashiya', 'boat.ashiya', '芦屋'), '22': ('22fukuoka', 'boat.fukuoka', '福岡'),
    '23': ('23karatsu', 'boat.karatsu', '唐津'), '24': ('24omura', 'boat.omura', '大村'),
}


def get_json(url: str, timeout: int = 12):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8', 'replace'))


def parse_existing():
    if not OUT.exists():
        return {}
    lines = OUT.read_text(encoding='utf-8-sig', errors='replace').splitlines()
    out = {}
    for i, line in enumerate(lines):
        if not line.startswith('#EXTINF:'):
            continue
        m = re.search(r'tvg-id="([^"]+)"', line)
        if not m:
            continue
        for j in range(i + 1, min(i + 5, len(lines))):
            u = lines[j].strip()
            if u.startswith(('http://', 'https://')):
                out[m.group(1)] = (line, u)
                break
            if u.startswith('#EXTINF:'):
                break
    return out


def token_start_day(url: str):
    """Return the JWT stream start date in JST, or None if it cannot be verified."""
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


def is_today_seed(url: str, today) -> bool:
    return (
        url.startswith('https://manifest.streaks.jp/')
        and '.m3u8' in url
        and token_start_day(url) == today
    )


def resolve(code: str, ymd: str):
    setting_url = f'https://front.player.boatrace-cdn.jp/setting/live/{code}/setting.json?t={int(datetime.now().timestamp())}'
    try:
        get_json(setting_url)
    except Exception:
        pass

    playback = (
        'https://playback.api.streaks.jp/v1/projects/cp-boatrace-prod/'
        f'medias/ref:lm-br-{code}-tokyo-{ymd}?audio_only=false'
    )
    data = get_json(playback)
    for item in data.get('sources') or []:
        if isinstance(item, dict):
            src = str(item.get('src') or '').strip()
            if src.startswith('https://manifest.streaks.jp/') and '.m3u8' in src:
                return src
    return ''


def main():
    today = datetime.now(JST).date()
    ymd = today.strftime('%Y%m%d')
    existing = parse_existing()
    merged = {}
    kept = 0
    refreshed = 0
    missing = []

    print(f'BOAT current-day resolver: date={ymd} existing={len(existing)}')

    # iPhone seed remains authoritative, but only for the current JST date.
    # A previous-day Streaks URL must never survive simply because its JWT has
    # not expired yet: it can point at yesterday's VTR/manifest and be unusable.
    for _jcd, (code, tvg_id, name) in VENUES.items():
        old = existing.get(tvg_id)
        if old and is_today_seed(old[1], today):
            merged[tvg_id] = old
            kept += 1
            print(f'BOAT {name}: keep current-day seed')
            continue

        if old:
            old_day = token_start_day(old[1])
            print(f'BOAT {name}: stale/unverified seed ({old_day}) -> refresh {ymd}')
        else:
            print(f'BOAT {name}: seed missing -> resolve {ymd}')

        hit = ''
        try:
            hit = resolve(code, ymd)
        except Exception as e:
            print(f'BOAT {name} {ymd}: {type(e).__name__}: {e}')

        if hit and is_today_seed(hit, today):
            line = old[0] if old else f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="BOATRACE{name}" group-title="ボートレース",BOATRACE{name}'
            merged[tvg_id] = (line, hit)
            refreshed += 1
            print(f'BOAT {name}: REFRESHED current-day seed')
        else:
            if hit:
                print(f'BOAT {name}: rejected non-current seed start={token_start_day(hit)}')
            print(f'BOAT {name}: current-day stream unavailable; stale seed removed')
            missing.append(tvg_id)

    lines = ['#EXTM3U', '']
    for _jcd, (_code, tvg_id, _name) in VENUES.items():
        block = merged.get(tvg_id)
        if not block:
            continue
        lines.extend([block[0], block[1], ''])
    OUT.write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8')

    print(f'BOAT current-day result: kept={kept} refreshed={refreshed} total={len(merged)}/24 missing={len(missing)}')
    if missing:
        print('Missing current-day:', ', '.join(missing))


if __name__ == '__main__':
    main()
