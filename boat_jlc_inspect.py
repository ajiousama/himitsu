#!/usr/bin/env python3
from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from pathlib import Path

UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1'
PLAYER = 'https://front.player.boatrace-cdn.jp'
PLAYBACK = 'https://playback.api.streaks.jp/v1/projects/cp-boatrace-prod/medias/ref:{ref_id}?audio_only=false'
CODES = ['02toda','03edogawa','04heiwajima','09tsu','11biwako']
OUT = Path('boat_jlc_probe.json')


def get(url, referer=None, timeout=10):
    headers = {
        'User-Agent': UA,
        'Accept': 'application/json,*/*;q=0.8',
        'Origin': PLAYER,
        'Referer': referer or PLAYER + '/',
        'Cache-Control': 'no-cache',
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode('utf-8', 'replace')
            return {'status': int(getattr(r, 'status', 200)), 'body': raw, 'headers': dict(r.headers.items())}
    except urllib.error.HTTPError as e:
        try:
            raw = e.read().decode('utf-8', 'replace')
        except Exception:
            raw = ''
        return {'status': int(e.code), 'body': raw, 'headers': dict(e.headers.items()) if e.headers else {}}
    except Exception as e:
        return {'status': 0, 'error': f'{type(e).__name__}:{e}'}


def main():
    result = {'venues': []}
    for code in CODES:
        setting_url = PLAYER + f'/setting/live/{code}/setting.json?t={int(time.time())}'
        setting_resp = get(setting_url, PLAYER + f'/player/live?service=jyobb&stadium={code}&sourceType=br&dvr=1')
        item = {'code': code, 'setting': setting_resp}
        try:
            setting = json.loads(setting_resp.get('body') or '{}')
        except Exception:
            setting = {}
        live_ref = ((setting.get('br_live') or {}).get('ref_id') or '').strip()
        dvr_ref = ((setting.get('br_dvr') or {}).get('ref_id') or '').strip()
        item['live_ref'] = live_ref
        item['dvr_ref'] = dvr_ref
        if live_ref:
            item['live_playback'] = get(PLAYBACK.format(ref_id=urllib.parse.quote(live_ref, safe='')),
                                        PLAYER + f'/player/live?service=jyobb&stadium={code}&sourceType=br&dvr=1')
        if dvr_ref:
            item['dvr_playback'] = get(PLAYBACK.format(ref_id=urllib.parse.quote(dvr_ref, safe='')),
                                       PLAYER + f'/player/live?service=jyobb&stadium={code}&sourceType=br&dvr=1')
        result['venues'].append(item)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False)[:40000])


if __name__ == '__main__':
    main()
