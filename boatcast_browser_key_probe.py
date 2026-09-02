#!/usr/bin/env python3
import base64
import datetime as dt
import html
import json
import re
import subprocess
import time
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
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36'

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
    return bool(exp and exp > dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=10))


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


def jlc_player(jcd):
    jo = str(int(jcd))
    root = f'https://livebb.jlc.ne.jp/bb_top/new_bb/streamer/streamer.php?jo={jo}&md=L'
    try:
        text = fetch_text(root)
    except Exception as e:
        return '', [f'streamer:{type(e).__name__}']
    norm = normalize(text)
    clues = []
    player = ''
    for u in extract_urls(norm, root):
        if 'front.player.boatrace-cdn.jp/player/live' in u:
            player = u
            break
    for line in norm.splitlines():
        low = line.lower()
        if any(k in low for k in ('front.player','m3u8','manifest','streaks','stream')):
            clean = re.sub(r'\s+', ' ', line).strip()
            if clean and len(clues) < 8:
                clues.append(clean[:500])
    return player, clues


def recent_freewifi_versions(limit=80):
    shas = git('log', f'-n{limit}', '--format=%H', '--', 'freewifi').splitlines()
    for sha in shas:
        text = git('show', f'{sha}:freewifi')
        if text:
            yield sha, parse_entries(text)


def preload_history(held):
    chosen, source = {}, {}
    if FREEWIFI.exists():
        for tvg, url in parse_entries(FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')).items():
            if tvg in held and valid_url(url):
                chosen[tvg] = url; source[tvg] = 'current freewifi'
    if SEED.exists():
        for tvg, url in parse_entries(SEED.read_text(encoding='utf-8-sig', errors='replace')).items():
            if tvg in held and tvg not in chosen and valid_url(url):
                chosen[tvg] = url; source[tvg] = 'local seed'
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
    return chosen, source


def extract_playback_src(driver, request_id):
    try:
        body = driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': request_id}) or {}
        payload = json.loads(body.get('body') or '{}')
        sources = payload.get('sources') or []
        if sources and isinstance(sources[0], dict):
            src = str(sources[0].get('src') or '').strip()
            if valid_url(src):
                return src
    except Exception:
        pass
    return ''


def drain_browser(driver):
    candidates = []
    try:
        logs = driver.get_log('performance')
    except Exception:
        return candidates
    for entry in logs:
        try:
            msg = json.loads(entry['message'])['message']
            method = msg.get('method')
            params = msg.get('params') or {}
            if method == 'Network.requestWillBeSent':
                url = str((params.get('request') or {}).get('url') or '')
                if valid_url(url):
                    candidates.append(url)
            elif method == 'Network.responseReceived':
                resp = params.get('response') or {}
                url = str(resp.get('url') or '')
                if valid_url(url):
                    candidates.append(url)
                if 'playback.api.streaks.jp/' in url:
                    src = extract_playback_src(driver, str(params.get('requestId') or ''))
                    if src:
                        candidates.append(src)
        except Exception:
            continue
    try:
        resources = driver.execute_script("return performance.getEntriesByType('resource').map(x=>x.name)") or []
        for u in resources:
            if valid_url(str(u)):
                candidates.append(str(u))
    except Exception:
        pass
    return candidates


def browser_recover(held, chosen, source, details):
    missing = [tvg for tvg in held if tvg not in chosen]
    if not missing:
        return
    try:
        from selenium import webdriver
        from selenium.common.exceptions import TimeoutException
        from selenium.webdriver.chrome.options import Options
    except Exception as e:
        print(f'BOAT PLAYER browser unavailable: {type(e).__name__}')
        return
    opts = Options()
    opts.page_load_strategy = 'eager'
    opts.add_argument('--headless=new')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--autoplay-policy=no-user-gesture-required')
    opts.add_argument('--window-size=1280,720')
    opts.add_argument('--user-agent=' + UA)
    opts.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    driver = None
    try:
        driver = webdriver.Chrome(options=opts)
        driver.set_page_load_timeout(12)
        driver.execute_cdp_cmd('Network.enable', {})
        for tvg in missing:
            code = VENUES[tvg]
            player, clues = jlc_player(code[:2])
            # Deterministic fallback from the exact JLC iframe shape.
            if not player:
                player = (
                    'https://front.player.boatrace-cdn.jp/player/live?'
                    f'service=jyobb&stadium={code}&sourceType=br&dvr=1&autoplay=1&volume=50&bitrate=low'
                )
            details[code] = {'player': player, 'jlc_clues': clues}
            candidates = []
            try:
                try:
                    driver.get(player)
                except TimeoutException:
                    try: driver.execute_script('window.stop()')
                    except Exception: pass
                deadline = time.time() + 8
                while time.time() < deadline:
                    time.sleep(0.4)
                    candidates.extend(drain_browser(driver))
                    if candidates:
                        break
                if candidates:
                    chosen[tvg] = candidates[0]
                    source[tvg] = 'official jyobb player browser'
                    details[code]['browser'] = 'captured'
                    print(f'BOAT PLAYER OK {tvg} exp={jwt_exp(candidates[0])}')
                else:
                    details[code]['browser'] = 'no stream yet'
                    print(f'BOAT PLAYER WAIT {tvg}: no playable manifest observed')
            except Exception as e:
                details[code]['browser_error'] = type(e).__name__
                print(f'BOAT PLAYER WAIT {tvg}: {type(e).__name__}')
    finally:
        if driver is not None:
            try: driver.quit()
            except Exception: pass


def main():
    held = held_today()
    chosen, source = preload_history(held)
    details = {}
    for tvg in held:
        if tvg in chosen:
            print(f'BOAT PRELOAD OK {tvg} source={source[tvg]} exp={jwt_exp(chosen[tvg])}')
    browser_recover(held, chosen, source, details)

    streams = {VENUES[tvg]: url for tvg, url in chosen.items()}
    for tvg in held:
        if tvg in chosen:
            exp = jwt_exp(chosen[tvg])
            print(f'BOAT RECOVERED {tvg} source={source[tvg]} exp={exp.isoformat() if exp else "?"}')
        else:
            print(f'BOAT RECOVERY WAIT {tvg}: unresolved')

    status = {
        'source': 'ajiousama history -> actual JLC jyobb player',
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
