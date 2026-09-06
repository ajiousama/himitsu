#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import urllib.request
from pathlib import Path

UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1'
PLAYER = 'https://front.player.boatrace-cdn.jp'
TARGET = PLAYER + '/lib/streaks/2.5.8/streaksplayer.min.js?t=20260428000302'
OUT = Path('boat_jlc_probe.json')
NEEDLES = [
    'X-Streaks-Api-Key','X-Streaks-Session-Id','X-Streaks-User-Id','X-Streaks-Client',
    'PlaybackApi','Authorization','session_id','user_id','client','api_key','XMLHttpRequest','fetch('
]


def fetch(url, timeout=15):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': '*/*',
        'Origin': PLAYER,
        'Referer': PLAYER + '/player/live?service=jyobb&stadium=02toda&sourceType=br&dvr=1',
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', 'replace')


def snippets(text, needle):
    out=[]
    for m in re.finditer(re.escape(needle), text, re.I):
        s=text[max(0,m.start()-900):min(len(text),m.end()+1400)]
        if s not in out:
            out.append(s)
        if len(out)>=12:
            break
    return out


def main():
    body=fetch(TARGET)
    result={'url':TARGET,'length':len(body),'matches':{}}
    for needle in NEEDLES:
        hits=snippets(body, needle)
        if hits:
            result['matches'][needle]=hits
    # Capture literal X-Streaks header names and nearby object syntax even if minified.
    result['header_literals']=sorted(set(re.findall(r'X-Streaks-[A-Za-z-]+', body)))
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False)[:60000])

if __name__=='__main__':
    main()
