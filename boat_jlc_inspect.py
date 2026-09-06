#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1'
ROOTS = [
    'https://livebb.jlc.ne.jp/bb_top/sp_bb/live_02.php',
    'https://live.boatcast.jp/boatcastsp/live_02.php',
    'https://boatrace.sakura.tv/toda/',
]
OUT = Path('boat_jlc_probe.json')


def fetch(url, timeout=8):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': 'text/html,application/xhtml+xml,application/javascript,text/javascript,*/*;q=0.8',
        'Referer': url,
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        final = r.geturl()
        ctype = r.headers.get('Content-Type', '')
    return raw.decode('utf-8', 'replace'), final, ctype


def extract_refs(text, base):
    text = html.unescape(text)
    refs = []
    # HTML src/href plus absolute/protocol-relative URLs embedded in JS/JSON.
    patterns = [
        r'''(?:src|href)\s*=\s*["']([^"']+)["']''',
        r'''(?:https?:)?//[^"'<>\\\s]+''',
        r'''["']([^"']*(?:m3u8|uliza|player|playlist|manifest|stream|movie|live)[^"']*)["']''',
    ]
    for pat in patterns:
        for m in re.finditer(pat, text, re.I):
            value = m.group(1) if m.lastindex else m.group(0)
            value = value.strip().replace('\\/', '/')
            if value.startswith('//'):
                value = 'https:' + value
            try:
                value = urllib.parse.urljoin(base, value)
            except Exception:
                continue
            if value.startswith(('http://', 'https://')) and value not in refs:
                refs.append(value)
    return refs


def interesting(ref):
    low = ref.lower()
    return any(k in low for k in ('m3u8', 'uliza', 'player', 'playlist', 'manifest', 'stream', 'movie', 'live', '.js'))


def main():
    result = {'roots': [], 'children': []}
    child_urls = []
    for root in ROOTS:
        item = {'url': root}
        try:
            text, final, ctype = fetch(root)
            refs = extract_refs(text, final)
            item.update({
                'final': final,
                'content_type': ctype,
                'length': len(text),
                'interesting_refs': [x for x in refs if interesting(x)][:80],
                'all_refs': refs[:120],
                'snippets': [
                    text[max(0, m.start()-180):min(len(text), m.end()+300)]
                    for m in re.finditer(r'(?i)m3u8|uliza|player|playlist|manifest|stream|movie|live', text)
                ][:30],
            })
            for ref in refs:
                low = ref.lower()
                if (low.endswith('.js') or 'player' in low or 'uliza' in low or 'live' in low) and ref not in child_urls:
                    child_urls.append(ref)
        except Exception as e:
            item['error'] = f'{type(e).__name__}:{getattr(e, "code", "") or e}'
        result['roots'].append(item)

    for url in child_urls[:16]:
        item = {'url': url}
        try:
            text, final, ctype = fetch(url, timeout=6)
            refs = extract_refs(text, final)
            item.update({
                'final': final,
                'content_type': ctype,
                'length': len(text),
                'interesting_refs': [x for x in refs if interesting(x)][:80],
                'snippets': [
                    text[max(0, m.start()-220):min(len(text), m.end()+350)]
                    for m in re.finditer(r'(?i)m3u8|uliza|player|playlist|manifest|stream|movie|live', text)
                ][:40],
            })
        except Exception as e:
            item['error'] = f'{type(e).__name__}:{getattr(e, "code", "") or e}'
        result['children'].append(item)

    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False)[:16000])


if __name__ == '__main__':
    main()
