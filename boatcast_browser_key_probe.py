#!/usr/bin/env python3
import json
import os
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

KEY_OUT = Path('.boatcast_playback_key')
STREAM_OUT = Path('.boatcast_browser_streams.json')
STATUS_OUT = Path('.boatcast_browser_status.json')
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
    if not isinstance(item, dict) or not item.get('ref_id'):
        return False
    start = parse_dt(item.get('start_at'))
    end = parse_dt(item.get('end_at'))
    now = datetime.now(timezone.utc)
    if start and now < start:
        return False
    if end and now > end:
        return False
    return True


def get_setting(stadium):
    url = f'https://front.player.boatrace-cdn.jp/setting/live/{stadium}/setting.json?t={int(time.time())}'
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': 'application/json,text/plain,*/*',
        'Referer': 'https://front.player.boatrace-cdn.jp/',
    })
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.load(r)
    except Exception:
        return None


def collect_active():
    active = []
    for stadium in VENUES:
        setting = get_setting(stadium)
        if not isinstance(setting, dict):
            continue
        picked = None
        for name in ('mix_dvr', 'mix_live', 'br_dvr', 'br_live'):
            item = setting.get(name)
            if active_item(item):
                picked = {'stadium': stadium, 'source': name, 'ref_id': str(item.get('ref_id'))}
                break
        if picked:
            active.append(picked)
    return active


def find_key(headers):
    if not isinstance(headers, dict):
        return None
    for k, v in headers.items():
        if str(k).lower() == 'x-streaks-api-key' and v:
            return str(v).strip()
    return None


def extract_src(payload):
    if not isinstance(payload, dict):
        return ''
    sources = payload.get('sources')
    if isinstance(sources, list) and sources:
        src = (sources[0] or {}).get('src') if isinstance(sources[0], dict) else None
        if src:
            return str(src).strip()
    return ''


def main():
    for p in (KEY_OUT, STREAM_OUT, STATUS_OUT):
        p.unlink(missing_ok=True)

    active = collect_active()
    status = {
        'active_count': len(active),
        'active_stadiums': [x['stadium'] for x in active],
        'resolved_count': 0,
        'resolved_stadiums': [],
        'probe_http_status': None,
    }
    if not active:
        STREAM_OUT.write_text('{}', encoding='utf-8')
        STATUS_OUT.write_text(json.dumps(status, ensure_ascii=False), encoding='utf-8')
        print('BOATCAST browser: no currently active venue')
        return 0

    probe = active[0]
    print(f"BOATCAST browser: active={len(active)} probe={probe['stadium']} source={probe['source']}")
    player = (
        'https://front.player.boatrace-cdn.jp/player/live?'
        f"service=boatcast&stadium={probe['stadium']}&sourceType=mix&dvr=1&"
        'audioMode=0&autoplay=1&bitrate=high'
    )

    try:
        from selenium import webdriver
        from selenium.common.exceptions import TimeoutException
        from selenium.webdriver.chrome.options import Options
    except Exception as e:
        print(f'BOATCAST browser unavailable: selenium import failed ({type(e).__name__})')
        STREAM_OUT.write_text('{}', encoding='utf-8')
        STATUS_OUT.write_text(json.dumps(status, ensure_ascii=False), encoding='utf-8')
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
    streams = {}
    try:
        driver = webdriver.Chrome(options=opts)
        driver.set_page_load_timeout(12)
        driver.set_script_timeout(12)
        driver.execute_cdp_cmd('Network.enable', {})
        try:
            driver.get(player)
        except TimeoutException:
            try:
                driver.execute_script('window.stop();')
            except Exception:
                pass

        official_url = None
        official_key = None
        probe_status = None
        deadline = time.time() + 12
        while time.time() < deadline and (official_url is None or probe_status is None):
            time.sleep(0.35)
            for entry in driver.get_log('performance'):
                try:
                    msg = json.loads(entry['message'])['message']
                    method = msg.get('method')
                    params = msg.get('params') or {}
                    if method == 'Network.requestWillBeSent':
                        req = params.get('request') or {}
                        url = str(req.get('url') or '')
                        if 'playback.api.streaks.jp/' in url:
                            official_url = official_url or url
                            official_key = official_key or find_key(req.get('headers') or {})
                    elif method == 'Network.responseReceived':
                        resp = params.get('response') or {}
                        url = str(resp.get('url') or '')
                        if 'playback.api.streaks.jp/' in url:
                            probe_status = int(resp.get('status') or 0)
                            official_url = official_url or url
                except Exception:
                    continue

        status['probe_http_status'] = probe_status
        if official_key:
            KEY_OUT.write_text(official_key, encoding='utf-8')
            try:
                os.chmod(KEY_OUT, 0o600)
            except OSError:
                pass
            print('BOATCAST browser: first-party playback key observed')
        print(f'BOATCAST browser: official playback status={probe_status or 0}')

        # Use the exact URL shape produced by the official player, preserving
        # any current query parameters. Replace only the media ref per venue.
        if official_url and probe['ref_id'] in official_url:
            for item in active:
                target = official_url.replace(probe['ref_id'], item['ref_id'])
                script = r'''
                    const url = arguments[0];
                    const done = arguments[arguments.length - 1];
                    fetch(url, {method:'GET', credentials:'include', cache:'no-store'})
                      .then(async r => done({status:r.status, text:await r.text()}))
                      .catch(e => done({status:0, error:String(e)}));
                '''
                try:
                    ans = driver.execute_async_script(script, target) or {}
                    code = int(ans.get('status') or 0)
                    if code != 200:
                        print(f"BOATCAST browser WAIT {item['stadium']}: HTTP {code}")
                        continue
                    payload = json.loads(ans.get('text') or '{}')
                    src = extract_src(payload)
                    if src:
                        streams[item['stadium']] = src
                        print(f"BOATCAST browser OK {item['stadium']} ref={item['ref_id']}")
                    else:
                        print(f"BOATCAST browser WAIT {item['stadium']}: no source")
                except Exception as e:
                    print(f"BOATCAST browser WAIT {item['stadium']}: {type(e).__name__}")
        else:
            print('BOATCAST browser: official playback URL/ref template not captured')
    except Exception as e:
        print(f'BOATCAST browser unavailable: {type(e).__name__}')
    finally:
        if driver is not None:
            try:
                driver.quit()
            except Exception:
                pass

    status['resolved_count'] = len(streams)
    status['resolved_stadiums'] = list(streams)
    STREAM_OUT.write_text(json.dumps(streams, ensure_ascii=False), encoding='utf-8')
    STATUS_OUT.write_text(json.dumps(status, ensure_ascii=False), encoding='utf-8')
    print(f"BOATCAST browser streams: active={status['active_count']} resolved={status['resolved_count']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
