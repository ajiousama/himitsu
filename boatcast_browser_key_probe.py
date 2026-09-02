#!/usr/bin/env python3
import html
import json
import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

STREAM_OUT = Path('.boatcast_browser_streams.json')
STATUS_OUT = Path('.boatcast_browser_status.json')
EPG = Path('public_sports_epg_local.xml')
JST = timezone(timedelta(hours=9))
UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1'

VENUES = {
    'boat.kiryu': ('01kiryu', 'kiryu'), 'boat.toda': ('02toda', 'toda'),
    'boat.edogawa': ('03edogawa', 'edogawa'), 'boat.heiwajima': ('04heiwajima', 'heiwajima'),
    'boat.tamagawa': ('05tamagawa', 'tamagawa'), 'boat.hamanako': ('06hamanako', 'hamanako'),
    'boat.gamagori': ('07gamagori', 'gamagori'), 'boat.tokoname': ('08tokoname', 'tokoname'),
    'boat.tsu': ('09tsu', 'tsu'), 'boat.mikuni': ('10mikuni', 'mikuni'),
    'boat.biwako': ('11biwako', 'biwako'), 'boat.suminoe': ('12suminoe', 'suminoe'),
    'boat.amagasaki': ('13amagasaki', 'amagasaki'), 'boat.naruto': ('14naruto', 'naruto'),
    'boat.marugame': ('15marugame', 'marugame'), 'boat.kojima': ('16kojima', 'kojima'),
    'boat.miyajima': ('17miyajima', 'miyajima'), 'boat.tokuyama': ('18tokuyama', 'tokuyama'),
    'boat.shimonoseki': ('19shimonoseki', 'shimonoseki'), 'boat.wakamatsu': ('20wakamatsu', 'wakamatsu'),
    'boat.ashiya': ('21ashiya', 'ashiya'), 'boat.fukuoka': ('22fukuoka', 'fukuoka'),
    'boat.karatsu': ('23karatsu', 'karatsu'), 'boat.omura': ('24omura', 'omura'),
}


def held_today():
    today = datetime.now(JST).strftime('%Y%m%d')
    found, seen = [], set()
    if not EPG.exists():
        return found
    try:
        root = ET.parse(EPG).getroot()
        for p in root.findall('programme'):
            ch = (p.get('channel') or '').strip()
            start = (p.get('start') or '').strip()
            if ch in VENUES and start.startswith(today) and ch not in seen:
                found.append(ch); seen.add(ch)
    except Exception as e:
        print(f'JLC held detection EPG error: {type(e).__name__}')
    return found


def fetch_text(url, timeout=8):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': 'text/html,application/xhtml+xml,application/javascript,text/javascript,*/*;q=0.8',
        'Referer': 'https://boatrace.sakura.tv/',
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        ctype = (r.headers.get('Content-Type') or '').lower()
        charset = 'utf-8'
        m = re.search(r'charset=([\w-]+)', ctype)
        if m: charset = m.group(1)
        try: return raw.decode(charset, errors='replace')
        except LookupError: return raw.decode('utf-8', errors='replace')


def normalize_text(text):
    s = html.unescape(text or '')
    s = s.replace('\\/', '/').replace('\\u0026', '&').replace('\\x26', '&')
    return s


def extract_urls(text, base):
    s = normalize_text(text)
    out = []
    for m in re.finditer(r'https?://[^\s\"\'<>\\]+', s, re.I):
        u = m.group(0).rstrip(');,]}')
        if u not in out: out.append(u)
    for attr in re.finditer(r'(?:src|href)\s*=\s*[\"\']([^\"\']+)[\"\']', s, re.I):
        u = urljoin(base, attr.group(1).strip())
        if u.startswith(('http://','https://')) and u not in out: out.append(u)
    return out


def stream_score(url):
    u = url.lower(); score = 0
    if '.m3u8' not in u: return -9999
    if 'master' in u: score += 80
    if 'playlist' in u: score += 50
    if 'iphoneplaylist' in u: score += 40
    if 'index' in u: score += 30
    if 'chunklist' in u: score -= 30
    return score


def pick_stream(urls):
    vals, seen = [], set()
    for u in urls:
        u = html.unescape(str(u or '')).replace('&amp;', '&')
        if u.startswith(('http://','https://')) and '.m3u8' in u.lower() and u not in seen:
            vals.append(u); seen.add(u)
    if not vals: return ''
    vals.sort(key=stream_score, reverse=True)
    return vals[0]


def static_probe(jcd):
    root = f'https://livebb.jlc.ne.jp/bb_top/sp_bb/live_{jcd}.php'
    queue = [root]
    seen = set()
    candidates = []
    clues = []
    while queue and len(seen) < 12:
        url = queue.pop(0)
        if url in seen: continue
        seen.add(url)
        try:
            text = fetch_text(url)
        except Exception as e:
            clues.append(f'{urlsplit(url).path}:{type(e).__name__}')
            continue
        norm = normalize_text(text)
        candidates.extend(extract_urls(norm, url))
        for line in norm.splitlines():
            low = line.lower()
            if any(k in low for k in ('m3u8','uliza','playlist','hls','movie','stream')):
                clean = re.sub(r'\s+', ' ', line).strip()
                if clean and len(clues) < 12:
                    clues.append(clean[:360])
        for u in extract_urls(norm, url):
            host = urlsplit(u).netloc.lower()
            path = urlsplit(u).path.lower()
            if u in seen: continue
            if host == 'livebb.jlc.ne.jp' and (path.endswith('.js') or 'live_' in path or path.endswith('.php')):
                queue.append(u)
            elif 'uliza' in host and (path.endswith('.js') or '.m3u8' in path):
                queue.append(u)
    return pick_stream(candidates), clues


def drain_network(driver):
    urls = []
    interesting = []
    try: logs = driver.get_log('performance')
    except Exception: return urls, interesting
    for entry in logs:
        try:
            msg = json.loads(entry['message'])['message']
            method = msg.get('method')
            params = msg.get('params') or {}
            if method == 'Network.requestWillBeSent':
                url = str((params.get('request') or {}).get('url') or '')
            elif method == 'Network.responseReceived':
                url = str((params.get('response') or {}).get('url') or '')
            else: continue
            if '.m3u8' in url.lower(): urls.append(url)
            low = url.lower()
            if any(k in low for k in ('uliza','m3u8','playlist','manifest','hls','livebb.jlc.ne.jp')) and url not in interesting:
                interesting.append(url)
        except Exception:
            pass
    return urls, interesting


def browser_probe(active, streams, details):
    missing = [ch for ch in active if VENUES[ch][0] not in streams]
    if not missing: return
    try:
        from selenium import webdriver
        from selenium.common.exceptions import TimeoutException
        from selenium.webdriver.chrome.options import Options
    except Exception as e:
        print(f'JLC browser unavailable: {type(e).__name__}')
        return
    opts = Options(); opts.page_load_strategy = 'eager'
    opts.add_argument('--headless=new'); opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage'); opts.add_argument('--disable-gpu')
    opts.add_argument('--autoplay-policy=no-user-gesture-required'); opts.add_argument('--window-size=390,844')
    opts.add_argument('--user-agent=' + UA)
    opts.set_capability('goog:loggingPrefs', {'performance': 'ALL'})
    driver = None
    try:
        driver = webdriver.Chrome(options=opts)
        driver.set_page_load_timeout(12)
        driver.execute_cdp_cmd('Network.enable', {})
        for ch in missing:
            code, _ = VENUES[ch]; jcd = code[:2]
            url = f'https://livebb.jlc.ne.jp/bb_top/sp_bb/live_{jcd}.php'
            try:
                try: driver.get(url)
                except TimeoutException:
                    try: driver.execute_script('window.stop()')
                    except Exception: pass
                # Old JLC mobile pages require a user gesture. Click the most likely
                # playback anchor/button/image before watching network traffic.
                try:
                    driver.execute_script('''
                      const nodes=[...document.querySelectorAll('a,button,input[type=button],input[type=submit],img')];
                      const n=nodes.find(x => ((x.innerText||x.alt||x.title||x.value||'')+' '+(x.href||'')).match(/再生|ライブ|live|play/i));
                      if(n){ n.click(); return true; } return false;
                    ''')
                except Exception: pass
                observed, interesting = [], []
                deadline = time.time() + 5
                while time.time() < deadline:
                    time.sleep(0.4)
                    a, b = drain_network(driver); observed.extend(a); interesting.extend(b)
                    srcs = driver.execute_script('''return [...document.querySelectorAll('video,source')].map(x=>x.currentSrc||x.src).filter(Boolean)''') or []
                    observed.extend([str(x) for x in srcs if '.m3u8' in str(x).lower()])
                    if observed: break
                src = pick_stream(observed)
                if src:
                    streams[code] = src
                    details[code]['browser'] = 'captured'
                    print(f'JLC STREAM OK {ch} browser={urlsplit(src).netloc}')
                else:
                    uniq=[]
                    for x in interesting:
                        if x not in uniq: uniq.append(x)
                    details[code]['network_clues'] = uniq[:12]
                    print(f'JLC STREAM WAIT {ch}: static/browser no m3u8 clues={len(uniq)}')
                    if uniq:
                        print('JLC NETWORK CLUES ' + ch + ': ' + ' | '.join(uniq[:6]))
            except Exception as e:
                details[code]['browser_error'] = type(e).__name__
                print(f'JLC STREAM WAIT {ch}: browser {type(e).__name__}')
    finally:
        if driver is not None:
            try: driver.quit()
            except Exception: pass


def main():
    for p in (STREAM_OUT, STATUS_OUT): p.unlink(missing_ok=True)
    active = held_today(); streams = {}; details = {}
    for ch in active:
        code, _ = VENUES[ch]; jcd = code[:2]
        src, clues = static_probe(jcd)
        details[code] = {'mobile': f'https://livebb.jlc.ne.jp/bb_top/sp_bb/live_{jcd}.php', 'static_clues': clues[:12]}
        if src:
            streams[code] = src
            details[code]['static'] = 'captured'
            print(f'JLC STREAM OK {ch} static={urlsplit(src).netloc}')
        else:
            print(f'JLC STATIC WAIT {ch}: no literal m3u8 clues={len(clues)}')
            if clues:
                print('JLC STATIC CLUES ' + ch + ': ' + ' | '.join(clues[:4]))
    browser_probe(active, streams, details)
    status = {
        'source': 'boatrace.sakura.tv -> JLC mobile HTML/JS',
        'active_count': len(active), 'active_stadiums': [VENUES[x][0] for x in active],
        'resolved_count': len(streams), 'resolved_stadiums': list(streams), 'details': details,
    }
    STREAM_OUT.write_text(json.dumps(streams, ensure_ascii=False, indent=2), encoding='utf-8')
    STATUS_OUT.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'JLC config streams: active={len(active)} resolved={len(streams)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
