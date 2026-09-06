#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1'
BASE = 'https://front.player.boatrace-cdn.jp'
TARGETS = [
    BASE + '/js/live.js?t=20260428000302',
    BASE + '/js/player.js?t=20260428000302',
    BASE + '/js/config/config.js?t=20260428000302',
]
OUT = Path('boat_jlc_probe.json')


def fetch(url, timeout=10):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': '*/*',
        'Origin': BASE,
        'Referer': BASE + '/player/live?service=jyobb&stadium=02toda&sourceType=br&dvr=1',
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        return raw.decode('utf-8', 'replace'), r.geturl(), r.headers.get('Content-Type', ''), int(getattr(r, 'status', 200))


def extract(text):
    patterns = [
        r'https?://[^\s"\'<>\\]+',
        r'[^\s"\'<>\\]*(?:m3u8|mpd|playback|streaks|api|setting|config|manifest|media|source|token|fetch|ajax)[^\s"\'<>\\]*',
    ]
    values = []
    for pat in patterns:
        for m in re.finditer(pat, text, re.I):
            v = m.group(0).replace('\\/', '/').strip()
            if v and v not in values:
                values.append(v)
    return values[:400]


def snippets(text):
    out = []
    for m in re.finditer(r'(?i)m3u8|mpd|playback|streaks|api|setting|manifest|media|source|token|fetch|ajax', text):
        s = text[max(0, m.start()-350):min(len(text), m.end()+700)]
        if s not in out:
            out.append(s)
        if len(out) >= 80:
            break
    return out


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
                'snippets': snippets(body),
                'body': body[:160000],
            })
        except Exception as e:
            item['error'] = f'{type(e).__name__}:{getattr(e, "code", "") or e}'
        result['targets'].append(item)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False)[:50000])


if __name__ == '__main__':
    main()
