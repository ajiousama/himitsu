#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
import json
import re
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


def get_json(url: str, timeout: int = 20):
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


def resolve(code: str, ymd: str):
    # Match the proven earphone1981 sequence: touch official setting first,
    # then request the Streaks playback source using official Origin/Referer.
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
    ymd = datetime.now(JST).strftime('%Y%m%d')
    existing = parse_existing()
    refreshed = {}
    success = 0

    for jcd, (code, tvg_id, name) in VENUES.items():
        try:
            url = resolve(code, ymd)
        except Exception as e:
            print(f'BOAT Streaks {name}: failed: {type(e).__name__}: {e}')
            continue
        if url:
            refreshed[tvg_id] = (f'#EXTINF:-1 tvg-id="{tvg_id}",BOATRACE{name}', url)
            success += 1
            print(f'BOAT Streaks {name}: refreshed')

    # Keep only current Streaks successes plus an existing YouTube-derived boat.*
    # fallback when that venue did not refresh. The next YouTube refresh may replace it.
    merged = dict(refreshed)
    for tvg_id, block in existing.items():
        if tvg_id in merged or not tvg_id.startswith('boat.'):
            continue
        url = block[1]
        if 'googlevideo.com' in url:
            merged[tvg_id] = block

    lines = ['#EXTM3U', '']
    for _jcd, (_code, tvg_id, _name) in VENUES.items():
        block = merged.get(tvg_id)
        if not block:
            continue
        lines.extend([block[0], block[1], ''])
    OUT.write_text('\n'.join(lines).rstrip() + '\n', encoding='utf-8')
    print(f'BOAT Streaks refresh successes={success}')


if __name__ == '__main__':
    main()
