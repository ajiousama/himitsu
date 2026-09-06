#!/usr/bin/env python3
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1'
BASE = 'https://front.player.boatrace-cdn.jp'
TARGETS = [
    BASE + f'/setting/live/02toda/setting.json?t={int(time.time())}',
    BASE + f'/setting/live/03edogawa/setting.json?t={int(time.time())}',
    BASE + f'/setting/live/04heiwajima/setting.json?t={int(time.time())}',
    BASE + f'/setting/live/09tsu/setting.json?t={int(time.time())}',
    BASE + f'/setting/live/11biwako/setting.json?t={int(time.time())}',
]
OUT = Path('boat_jlc_probe.json')


def fetch(url, timeout=10):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': 'application/json,*/*;q=0.8',
        'Origin': BASE,
        'Referer': BASE + '/player/live?service=jyobb&stadium=02toda&sourceType=br&dvr=1',
        'Cache-Control': 'no-cache',
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        return raw.decode('utf-8', 'replace'), r.geturl(), r.headers.get('Content-Type', ''), int(getattr(r, 'status', 200))


def main():
    result = {'targets': []}
    for url in TARGETS:
        item = {'url': url}
        try:
            body, final, ctype, status = fetch(url)
            item.update({'status': status, 'final': final, 'content_type': ctype, 'body': body})
            try:
                item['json'] = json.loads(body)
            except Exception:
                pass
        except Exception as e:
            item['error'] = f'{type(e).__name__}:{getattr(e, "code", "") or e}'
        result['targets'].append(item)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    main()
