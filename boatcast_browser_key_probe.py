#!/usr/bin/env python3
import json
import os
import time
from pathlib import Path

OUT = Path('.boatcast_playback_key')
PLAYER = (
    'https://front.player.boatrace-cdn.jp/player/live?'
    'service=boatcast&stadium=12suminoe&sourceType=mix&dvr=1&'
    'audioMode=0&autoplay=1&bitrate=high'
)


def find_key(headers):
    if not isinstance(headers, dict):
        return None
    for k, v in headers.items():
        if str(k).lower() == 'x-streaks-api-key' and v:
            return str(v).strip()
    return None


def main():
    OUT.unlink(missing_ok=True)
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
            driver.get(PLAYER)
        except TimeoutException:
            print('BOATCAST browser probe: page-load timeout accepted; continuing with network capture')
            try:
                driver.execute_script('window.stop();')
            except Exception:
                pass

        deadline = time.time() + 12
        request_urls = {}
        extra_headers = {}
        key = None
        playback_seen = False
        while time.time() < deadline and not key:
            time.sleep(0.5)
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
                            key = find_key(req.get('headers')) or key
                            if not key and rid:
                                key = find_key(extra_headers.get(rid)) or key
                    elif method == 'Network.requestWillBeSentExtraInfo':
                        if rid:
                            extra_headers[rid] = params.get('headers') or {}
                            if 'playback.api.streaks.jp/' in request_urls.get(rid, ''):
                                playback_seen = True
                                key = find_key(extra_headers[rid]) or key
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
            print('BOATCAST browser probe: playback request observed but API-key header was not visible')
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
