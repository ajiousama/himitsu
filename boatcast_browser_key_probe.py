#!/usr/bin/env python3
import base64
import datetime as dt
import json
import re
import subprocess
import xml.etree.ElementTree as ET
from pathlib import Path

EPG = Path('public_sports_epg_local.xml')
FREEWIFI = Path('freewifi')
SEED = Path('boat_stream_seed.m3u')
STREAM_OUT = Path('.boatcast_browser_streams.json')
STATUS_OUT = Path('.boatcast_browser_status.json')
NOW = dt.datetime.now(dt.timezone.utc)
JST = dt.timezone(dt.timedelta(hours=9))

VENUES = {
    'boat.kiryu':'01kiryu','boat.toda':'02toda','boat.edogawa':'03edogawa','boat.heiwajima':'04heiwajima',
    'boat.tamagawa':'05tamagawa','boat.hamanako':'06hamanako','boat.gamagori':'07gamagori','boat.tokoname':'08tokoname',
    'boat.tsu':'09tsu','boat.mikuni':'10mikuni','boat.biwako':'11biwako','boat.suminoe':'12suminoe',
    'boat.amagasaki':'13amagasaki','boat.naruto':'14naruto','boat.marugame':'15marugame','boat.kojima':'16kojima',
    'boat.miyajima':'17miyajima','boat.tokuyama':'18tokuyama','boat.shimonoseki':'19shimonoseki','boat.wakamatsu':'20wakamatsu',
    'boat.ashiya':'21ashiya','boat.fukuoka':'22fukuoka','boat.karatsu':'23karatsu','boat.omura':'24omura',
}


def git(*args):
    p = subprocess.run(['git', *args], text=True, capture_output=True)
    return p.stdout if p.returncode == 0 else ''


def jwt_exp(url):
    m = re.search(r'[?&]token=([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]+)\.([A-Za-z0-9_-]+)', url or '')
    if not m:
        return None
    try:
        payload = m.group(2) + '=' * (-len(m.group(2)) % 4)
        obj = json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
        exp = obj.get('exp')
        return dt.datetime.fromtimestamp(int(exp), dt.timezone.utc) if exp else None
    except Exception:
        return None


def valid_url(url):
    if 'manifest.streaks.jp' not in (url or ''):
        return False
    exp = jwt_exp(url)
    return bool(exp and exp > NOW + dt.timedelta(minutes=10))


def parse_entries(text):
    lines = (text or '').replace('\r\n','\n').split('\n')
    out = {}
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('#EXTINF:'):
            m = re.search(r'tvg-id="([^"]+)"', line)
            tvg = m.group(1) if m else None
            j = i + 1
            while j < len(lines) and (not lines[j].strip() or lines[j].lstrip().startswith('#')):
                j += 1
            if tvg and j < len(lines):
                url = lines[j].strip()
                if url.startswith(('http://','https://')):
                    out[tvg] = url
            i = j
        i += 1
    return out


def held_today():
    today = dt.datetime.now(JST).strftime('%Y%m%d')
    held = []
    seen = set()
    if not EPG.exists():
        return held
    try:
        root = ET.parse(EPG).getroot()
        for p in root.findall('programme'):
            ch = (p.get('channel') or '').strip()
            start = (p.get('start') or '').strip()
            if ch in VENUES and start.startswith(today) and ch not in seen:
                held.append(ch); seen.add(ch)
    except Exception as e:
        print(f'BOAT history held detection error: {type(e).__name__}')
    return held


def recent_freewifi_versions(limit=80):
    shas = git('log', f'-n{limit}', '--format=%H', '--', 'freewifi').splitlines()
    for sha in shas:
        text = git('show', f'{sha}:freewifi')
        if text:
            yield sha, parse_entries(text)


def main():
    held = held_today()
    chosen = {}
    source = {}

    # 1) Current ajiousama/freewifi.
    if FREEWIFI.exists():
        for tvg, url in parse_entries(FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')).items():
            if tvg in held and valid_url(url):
                chosen[tvg] = url; source[tvg] = 'current freewifi'

    # 2) Current seed copied once from known-valid history. Runtime does not depend on another repo.
    if SEED.exists():
        for tvg, url in parse_entries(SEED.read_text(encoding='utf-8-sig', errors='replace')).items():
            if tvg in held and tvg not in chosen and valid_url(url):
                chosen[tvg] = url; source[tvg] = 'local seed'

    # 3) Same-repository Git history, identical idea to the old public-sports implementation.
    missing = set(held) - set(chosen)
    if missing:
        for sha, entries in recent_freewifi_versions():
            if not missing:
                break
            for tvg in list(missing):
                url = entries.get(tvg)
                if url and valid_url(url):
                    chosen[tvg] = url; source[tvg] = f'git:{sha[:8]}'
                    missing.remove(tvg)

    streams = {VENUES[tvg]: url for tvg, url in chosen.items()}
    for tvg in held:
        if tvg in chosen:
            exp = jwt_exp(chosen[tvg])
            print(f'BOAT HISTORY OK {tvg} source={source[tvg]} exp={exp.isoformat() if exp else "?"}')
        else:
            print(f'BOAT HISTORY WAIT {tvg}: no unexpired URL in ajiousama history/seed')

    status = {
        'source': 'ajiousama local current/seed/git history',
        'active_count': len(held),
        'active_stadiums': [VENUES[x] for x in held],
        'resolved_count': len(streams),
        'resolved_stadiums': list(streams),
        'sources': {VENUES[tvg]: source[tvg] for tvg in chosen},
    }
    STREAM_OUT.write_text(json.dumps(streams, ensure_ascii=False, indent=2), encoding='utf-8')
    STATUS_OUT.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'BOAT history streams: active={len(held)} resolved={len(streams)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
