#!/usr/bin/env python3
import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path('.boatcast_playback_key')
VENUES = [
    '01kiryu','02toda','03edogawa','04heiwajima','05tamagawa','06hamanako',
    '07gamagori','08tokoname','09tsu','10mikuni','11biwako','12suminoe',
    '13amagasaki','14naruto','15marugame','16kojima','17miyajima','18tokuyama',
    '19shimonoseki','20wakamatsu','21ashiya','22fukuoka','23karatsu','24omura',
]
UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36'


def parse_dt(value):
    if not value:
        return None
    s = str(value).strip().replace('Z', '+00:00')
    try:
        d = datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(timezone.utc)
    except Exception:
        return None


def active_item(item):
    if not isinstance(item, dict):
        return False
    start = parse_dt(item.get('start_at'))
    end = parse_dt(item.get('end_at'))
    now = datetime.now(timezone.utc)
    if start and now < start:
        return False
    if end and now > end:
        return False
    return bool(item.get('ref_id'))


def get_setting(stadium):
    url = f'https://front.player.boatrace-cdn.jp/setting/live/{stadium}/setting.json?t={int(time.time())}'
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': 'application/json,text/plain,*/*',
        'Referer': 'https://front.player.boatrace-cdn.jp/',
    })
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            return json.load(r)
    except Exception:
        return None


def choose_active_stadium():
    for stadium in VENUES:
        setting = get_setting(stadium)
        if not isinstance(setting, dict):
            continue
        for name in ('mix_dvr', 'mix_live', 'br_dvr', 'br_live'):
            if active_item(setting.get(name)):
                print(f'BOATCAST browser probe: active stadium={stadium} source={name}')
                return stadium
    return None


def find_key(headers):
    if not isinstance(headers, dict):
        return None
    for k, v in headers.items():
        if str(k).lower() == 'x-streaks-api-key' and v:
            return str(v).strip()
    return None


def auth_header_names(headers):
    if not isinstance(headers, dict):
        return []
    out = []
    for k in headers:
        lk = str(k).lower()
        if any(x in lk for x in ('api', 'key', 'auth', 'streak')):
            out.append(str(k))
    return sorted(set(out))


def main():
    OUT.unlink(missing_ok=True)
    stadium = choose_active_stadium()
    if not stadium:
        print('BOATCAST browser probe: no currently active venue found; skipping auth capture')
        return 0

    player = (
        'https://front.player.boatrace-cdn.jp/player/live?'
        f'service=boatcast&stadium={stadium}&sourceType=mix&dvr=1&'
        'audioMode=0&autoplay=1&bitrate=high'
    )

    try:
        from selenium import webdriver
        from selenium.common.exceptions import TimeoutException
        from selenium.webdriver.chrome.options import Options
    except Exception as e:
        print(f'BOATCAST browser probe unavailable: selenium import failed ({type(e).__name__})')
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
        try:
            driver.get(player)
        except TimeoutException:
            print('BOATCAST browser probe: page-load timeout accepted; continuing with network capture')
            try:
                driver.execute_script('window.stop();')
            except Exception:
                pass

        deadline = time.time() + 15
        request_urls = {}
        extra_headers = {}
        key = None
        playback_seen = False
        seen_auth_names = set()
        while time.time() < deadline and not key:
            time.sleep(0.4)
            for entry in driver.get_log('performance'):
                try:
                    msg = json.loads(entry['message'])['message']
                    method = msg.get('method')
                    params = msg.get('params') or {}
                    rid = params.get('requestId')
                    if method == 'Network.requestWillBeSent':
                        req = params.get('request') or {}
                        url = str(req.get('url') or '')
                        if rid:
                            request_urls[rid] = url
                        if 'playback.api.streaks.jp/' in url:
                            playback_seen = True
                            headers = req.get('headers') or {}
                            seen_auth_names.update(auth_header_names(headers))
                            key = find_key(headers) or key
                            if rid:
                                eh = extra_headers.get(rid) or {}
                                seen_auth_names.update(auth_header_names(eh))
                                key = find_key(eh) or key
                    elif method == 'Network.requestWillBeSentExtraInfo' and rid:
                        headers = params.get('headers') or {}
                        extra_headers[rid] = headers
                        if 'playback.api.streaks.jp/' in request_urls.get(rid, ''):
                            playback_seen = True
                            seen_auth_names.update(auth_header_names(headers))
                            key = find_key(headers) or key
                except Exception:
                    continue

        if key:
            OUT.write_text(key, encoding='utf-8')
            try:
                os.chmod(OUT, 0o600)
            except OSError:
                pass
            print('BOATCAST browser probe: playback API key captured from first-party request')
        elif playback_seen:
            names = ','.join(sorted(seen_auth_names)) or '(none)'
            print(f'BOATCAST browser probe: playback request observed; auth-like header names={names}')
        else:
            print('BOATCAST browser probe: playback request/key not observed')
    except Exception as e:
        print(f'BOATCAST browser probe unavailable: {type(e).__name__}')
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
