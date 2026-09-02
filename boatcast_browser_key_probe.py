#!/usr/bin/env python3
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

STREAM_OUT = Path('.boatcast_browser_streams.json')
STATUS_OUT = Path('.boatcast_browser_status.json')
EPG = Path('public_sports_epg_local.xml')
JST = timezone(timedelta(hours=9))

VENUES = {
    'boat.kiryu': ('01kiryu', 'kiryu'),
    'boat.toda': ('02toda', 'toda'),
    'boat.edogawa': ('03edogawa', 'edogawa'),
    'boat.heiwajima': ('04heiwajima', 'heiwajima'),
    'boat.tamagawa': ('05tamagawa', 'tamagawa'),
    'boat.hamanako': ('06hamanako', 'hamanako'),
    'boat.gamagori': ('07gamagori', 'gamagori'),
    'boat.tokoname': ('08tokoname', 'tokoname'),
    'boat.tsu': ('09tsu', 'tsu'),
    'boat.mikuni': ('10mikuni', 'mikuni'),
    'boat.biwako': ('11biwako', 'biwako'),
    'boat.suminoe': ('12suminoe', 'suminoe'),
    'boat.amagasaki': ('13amagasaki', 'amagasaki'),
    'boat.naruto': ('14naruto', 'naruto'),
    'boat.marugame': ('15marugame', 'marugame'),
    'boat.kojima': ('16kojima', 'kojima'),
    'boat.miyajima': ('17miyajima', 'miyajima'),
    'boat.tokuyama': ('18tokuyama', 'tokuyama'),
    'boat.shimonoseki': ('19shimonoseki', 'shimonoseki'),
    'boat.wakamatsu': ('20wakamatsu', 'wakamatsu'),
    'boat.ashiya': ('21ashiya', 'ashiya'),
    'boat.fukuoka': ('22fukuoka', 'fukuoka'),
    'boat.karatsu': ('23karatsu', 'karatsu'),
    'boat.omura': ('24omura', 'omura'),
}


def held_today():
    today = datetime.now(JST).strftime('%Y%m%d')
    found = []
    if EPG.exists():
        try:
            root = ET.parse(EPG).getroot()
            seen = set()
            for p in root.findall('programme'):
                ch = (p.get('channel') or '').strip()
                start = (p.get('start') or '').strip()
                if ch in VENUES and start.startswith(today) and ch not in seen:
                    found.append(ch)
                    seen.add(ch)
        except Exception as e:
            print(f'JLC held detection EPG error: {type(e).__name__}')
    return found


def looks_like_stream(url):
    u = (url or '').lower()
    return '.m3u8' in u and u.startswith(('http://', 'https://'))


def stream_score(url):
    u = (url or '').lower()
    score = 0
    if 'master' in u: score += 50
    if 'playlist' in u: score += 30
    if 'index' in u: score += 20
    if 'chunklist' in u: score -= 30
    if re.search(r'/\d+p?/', u): score -= 5
    return score


def extract_src(payload):
    if not isinstance(payload, dict):
        return ''
    sources = payload.get('sources')
    if isinstance(sources, list) and sources:
        item = sources[0]
        if isinstance(item, dict) and item.get('src'):
            return str(item['src']).strip()
    return ''


def drain_media(driver):
    urls = []
    playback_srcs = []
    try:
        logs = driver.get_log('performance')
    except Exception:
        return urls, playback_srcs
    for entry in logs:
        try:
            msg = json.loads(entry['message'])['message']
            method = msg.get('method')
            params = msg.get('params') or {}
            request_id = ''
            if method == 'Network.requestWillBeSent':
                url = str((params.get('request') or {}).get('url') or '')
            elif method == 'Network.responseReceived':
                resp = params.get('response') or {}
                url = str(resp.get('url') or '')
                request_id = str(params.get('requestId') or '')
            else:
                continue
            if looks_like_stream(url):
                urls.append(url)
            if method == 'Network.responseReceived' and 'playback.api.streaks.jp/' in url and request_id:
                try:
                    body = driver.execute_cdp_cmd('Network.getResponseBody', {'requestId': request_id})
                    payload = json.loads((body or {}).get('body') or '{}')
                    src = extract_src(payload)
                    if src:
                        playback_srcs.append(src)
                except Exception:
                    pass
        except Exception:
            continue
    return urls, playback_srcs


def pick_stream(urls):
    uniq = []
    seen = set()
    for u in urls:
        if u and u not in seen:
            uniq.append(u)
            seen.add(u)
    if not uniq:
        return ''
    uniq.sort(key=stream_score, reverse=True)
    return uniq[0]


def iframe_srcs(driver):
    try:
        vals = driver.execute_script('''
            return Array.from(document.querySelectorAll('iframe[src]'))
              .map(x => x.src)
              .filter(Boolean);
        ''') or []
        out = []
        for x in vals:
            s = str(x)
            if s.startswith(('http://', 'https://')) and 'googletagmanager.com' not in s:
                out.append(s)
        return out
    except Exception:
        return []


def load_and_capture(driver, url, timeout_cls, seconds=8):
    candidates = []
    playback = []
    try:
        driver.get(url)
    except timeout_cls:
        try:
            driver.execute_script('window.stop();')
        except Exception:
            pass
    deadline = time.time() + seconds
    while time.time() < deadline:
        time.sleep(0.4)
        a, b = drain_media(driver)
        candidates.extend(a)
        playback.extend(b)
        if candidates or playback:
            break
    return candidates, playback


def main():
    for p in (STREAM_OUT, STATUS_OUT):
        p.unlink(missing_ok=True)

    active = held_today()
    streams = {}
    status = {
        'source': 'boatrace.sakura.tv -> livebb.jlc.ne.jp',
        'active_count': len(active),
        'active_stadiums': [VENUES[x][0] for x in active],
        'resolved_count': 0,
        'resolved_stadiums': [],
        'details': {},
    }
    if not active:
        STREAM_OUT.write_text('{}', encoding='utf-8')
        STATUS_OUT.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
        print('JLC browser: no held BOAT venue in local EPG')
        return 0

    try:
        from selenium import webdriver
        from selenium.common.exceptions import TimeoutException
        from selenium.webdriver.chrome.options import Options
    except Exception as e:
        print(f'JLC browser unavailable: selenium import failed ({type(e).__name__})')
        STREAM_OUT.write_text('{}', encoding='utf-8')
        STATUS_OUT.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
        return 0

    opts = Options()
    opts.page_load_strategy = 'eager'
    opts.add_argument('--headless=new')
    opts.add_argument('--no-sandbox')
    opts.add_argument('--disable-dev-shm-usage')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--autoplay-policy=no-user-gesture-required')
    opts.add_argument('--window-size=1280,720')
    opts.set_capability('goog:loggingPrefs', {'performance': 'ALL'})

    driver = None
    try:
        driver = webdriver.Chrome(options=opts)
        driver.set_page_load_timeout(15)
        driver.execute_cdp_cmd('Network.enable', {})

        for ch in active:
            code, slug = VENUES[ch]
            jcd = code[:2]
            sakura_page = f'https://boatrace.sakura.tv/{slug}/'
            livebb = f'https://livebb.jlc.ne.jp/bb_top/new_bb/index.php?tpl={jcd}'
            detail = {'sakura': sakura_page, 'livebb': livebb, 'frames': [], 'captured': False}
            candidates = []
            playback = []
            try:
                a, b = load_and_capture(driver, livebb, TimeoutException, 7)
                candidates.extend(a)
                playback.extend(b)

                frames = iframe_srcs(driver)
                detail['frames'] = frames[:8]
                if not candidates and not playback:
                    for frame in frames[:4]:
                        a, b = load_and_capture(driver, frame, TimeoutException, 7)
                        candidates.extend(a)
                        playback.extend(b)
                        if candidates or playback:
                            break

                src = pick_stream(playback + candidates)
                if src:
                    streams[code] = src
                    detail['captured'] = True
                    detail['host'] = urlsplit(src).netloc
                    print(f'JLC STREAM OK {ch} via {detail.get("host", "")}')
                else:
                    print(f'JLC STREAM WAIT {ch}: no playable stream observed frames={len(frames)}')
            except Exception as e:
                detail['error'] = type(e).__name__
                print(f'JLC STREAM WAIT {ch}: {type(e).__name__}')
            status['details'][code] = detail
    except Exception as e:
        print(f'JLC browser unavailable: {type(e).__name__}')
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass

    status['resolved_count'] = len(streams)
    status['resolved_stadiums'] = list(streams)
    STREAM_OUT.write_text(json.dumps(streams, ensure_ascii=False, indent=2), encoding='utf-8')
    STATUS_OUT.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'JLC browser streams: active={len(active)} resolved={len(streams)}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
