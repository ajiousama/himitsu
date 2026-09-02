#!/usr/bin/env python3
import base64
import datetime as dt
import html
import json
import re
import subprocess
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urljoin, urlsplit

EPG = Path('public_sports_epg_local.xml')
FREEWIFI = Path('freewifi')
SEED = Path('boat_stream_seed.m3u')
STREAM_OUT = Path('.boatcast_browser_streams.json')
STATUS_OUT = Path('.boatcast_browser_status.json')
NOW = dt.datetime.now(dt.timezone.utc)
JST = dt.timezone(dt.timedelta(hours=9))
UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1'

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
    held, seen = [], set()
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
        print(f'BOAT held detection error: {type(e).__name__}')
    return held


def fetch_text(url, timeout=10):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': 'text/html,application/xhtml+xml,application/javascript,text/javascript,*/*;q=0.8',
        'Referer': 'https://live.kyotei.fun/',
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        ctype = (r.headers.get('Content-Type') or '').lower()
        m = re.search(r'charset=([\w-]+)', ctype)
        charset = m.group(1) if m else 'utf-8'
        try:
            return raw.decode(charset, errors='replace')
        except LookupError:
            return raw.decode('utf-8', errors='replace')


def normalize(s):
    return html.unescape(s or '').replace('\\/','/').replace('\\u0026','&').replace('\\x26','&')


def extract_urls(text, base):
    s = normalize(text)
    out = []
    for m in re.finditer(r'https?://[^\s\"\'<>\\]+', s, re.I):
        u = m.group(0).rstrip(');,]}')
        if u not in out:
            out.append(u)
    for m in re.finditer(r'(?:src|href)\s*=\s*[\"\']([^\"\']+)[\"\']', s, re.I):
        u = urljoin(base, m.group(1).strip())
        if u.startswith(('http://','https://')) and u not in out:
            out.append(u)
    return out


def streamer_probe(jcd):
    jo = str(int(jcd))
    root = f'https://livebb.jlc.ne.jp/bb_top/new_bb/streamer/streamer.php?jo={jo}&md=L'
    queue = [root]
    seen = set()
    candidates = []
    clues = []
    while queue and len(seen) < 12:
        url = queue.pop(0)
        if url in seen:
            continue
        seen.add(url)
        try:
            text = fetch_text(url)
        except Exception as e:
            clues.append(f'{urlsplit(url).path}:{type(e).__name__}')
            continue
        norm = normalize(text)
        urls = extract_urls(norm, url)
        for u in urls:
            if '.m3u8' in u.lower() or 'manifest.streaks.jp' in u.lower():
                candidates.append(u)
        for line in norm.splitlines():
            low = line.lower()
            if any(k in low for k in ('m3u8','manifest','playlist','uliza','streaks','hls','stream')):
                clean = re.sub(r'\s+', ' ', line).strip()
                if clean and len(clues) < 16:
                    clues.append(clean[:420])
        for u in urls:
            p = urlsplit(u)
            path = p.path.lower()
            if u in seen:
                continue
            if p.netloc.lower() == 'livebb.jlc.ne.jp' and (path.endswith('.js') or path.endswith('.php') or 'streamer' in path):
                queue.append(u)
    for u in candidates:
        if valid_url(u):
            return u, clues
    return '', clues


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
    details = {}

    # 1) Actual JLC streamer URL used by Sakura/live.kyotei.fun.
    for tvg in held:
        code = VENUES[tvg]
        src, clues = streamer_probe(code[:2])
        details[code] = {'streamer': f'https://livebb.jlc.ne.jp/bb_top/new_bb/streamer/streamer.php?jo={int(code[:2])}&md=L', 'clues': clues[:12]}
        if src:
            chosen[tvg] = src
            source[tvg] = 'JLC streamer'
            print(f'BOAT JLC OK {tvg} exp={jwt_exp(src)}')
        else:
            print(f'BOAT JLC WAIT {tvg}: no valid literal stream clues={len(clues)}')
            if clues:
                print('BOAT JLC CLUES ' + tvg + ': ' + ' | '.join(clues[:4]))

    # 2) Current ajiousama/freewifi.
    if FREEWIFI.exists():
        for tvg, url in parse_entries(FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')).items():
            if tvg in held and tvg not in chosen and valid_url(url):
                chosen[tvg] = url; source[tvg] = 'current freewifi'

    # 3) Local seed, copied once; no runtime dependency on another repository.
    if SEED.exists():
        for tvg, url in parse_entries(SEED.read_text(encoding='utf-8-sig', errors='replace')).items():
            if tvg in held and tvg not in chosen and valid_url(url):
                chosen[tvg] = url; source[tvg] = 'local seed'

    # 4) Same-repository Git history (old earphone strategy, now self-contained).
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
            print(f'BOAT RECOVERED {tvg} source={source[tvg]} exp={exp.isoformat() if exp else "?"}')
        else:
            print(f'BOAT RECOVERY WAIT {tvg}: unresolved')

    status = {
        'source': 'JLC streamer -> ajiousama current/seed/git history',
        'active_count': len(held),
        'active_stadiums': [VENUES[x] for x in held],
        'resolved_count': len(streams),
        'resolved_stadiums': list(streams),
        'sources': {VENUES[tvg]: source[tvg] for tvg in chosen},
        'details': details,
    }
    STREAM_OUT.write_text(json.dumps(streams, ensure_ascii=False, indent=2), encoding='utf-8')
    STATUS_OUT.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'BOAT recovered streams: active={len(held)} resolved={len(streams)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
