#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1'
TARGETS = [
    'https://livebb.jlc.ne.jp/bb_top/sp_bb/streamer/streamer26pj.php?jo=02',
    'https://front.player.boatrace-cdn.jp/player/live?service=jyobb&stadium=02toda&sourceType=br&dvr=1&autoplay=0&volume=50&bitrate=low',
]
OUT = Path('boat_jlc_probe.json')


def fetch(url, timeout=10):
    headers = {
        'User-Agent': UA,
        'Accept': '*/*',
        'Referer': 'https://livebb.jlc.ne.jp/bb_top/sp_bb/live_02.php',
    }
    if 'boatrace-cdn.jp' in url:
        headers['Origin'] = 'https://front.player.boatrace-cdn.jp'
        headers['Referer'] = 'https://front.player.boatrace-cdn.jp/'
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        return raw.decode('utf-8', 'replace'), r.geturl(), r.headers.get('Content-Type', ''), int(getattr(r, 'status', 200))


def extract(text):
    patterns = [
        r'https?://[^\s"\'<>\\]+',
        r'//[^\s"\'<>\\]+',
        r'[^\s"\'<>\\]*(?:m3u8|mpd|api|setting|config|uliza|playlist|manifest|stream|player)[^\s"\'<>\\]*',
    ]
    values = []
    for pat in patterns:
        for m in re.finditer(pat, text, re.I):
            v = m.group(0).replace('\\/', '/').strip()
            if v and v not in values:
                values.append(v)
    return values[:240]


def main():
    result = {'targets': []}
    for url in TARGETS:
        item = {'url': url}
        try:
            body, final, ctype, status = fetch(url)
            item.update({
                'status': status,
                'final': final,
                'content_type': ctype,
                'length': len(body),
                'interesting': extract(body),
                'body': body[:70000],
            })
        except Exception as e:
            item['error'] = f'{type(e).__name__}:{getattr(e, "code", "") or e}'
        result['targets'].append(item)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False)[:30000])


if __name__ == '__main__':
    main()
