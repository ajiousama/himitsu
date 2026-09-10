from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152.0 Safari/537.36'
START_URLS = [
    'https://www.tipstar.com/',
    'https://about.tipstar.com/',
]
OUT = Path('tipstar_autorace_probe.json')

VENUES = ['川口', '伊勢崎', '浜松', '山陽', '飯塚']
PATTERNS = [
    re.compile(r'https?://[^\"\'\\\s<>]+?\.m3u8(?:\?[^\"\'\\\s<>]*)?', re.I),
    re.compile(r'https?://[^\"\'\\\s<>]*cloudfront\.net/out/v1/[^\"\'\\\s<>]+', re.I),
]


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': '*/*',
        'Accept-Language': 'ja-JP,ja;q=0.9,en;q=0.7',
        'Cache-Control': 'no-cache',
    })
    with urllib.request.urlopen(req, timeout=25) as r:
        raw = r.read()
        ctype = r.headers.get('Content-Type', '')
    for enc in ('utf-8', 'utf-8-sig', 'cp932'):
        try:
            return raw.decode(enc)
        except Exception:
            pass
    return raw.decode('utf-8', errors='replace')


def assets(base: str, text: str) -> list[str]:
    out = []
    for pat in (
        r'<script[^>]+src=[\"\']([^\"\']+)',
        r'<link[^>]+href=[\"\']([^\"\']+)',
    ):
        for m in re.finditer(pat, text, re.I):
            u = urllib.parse.urljoin(base, m.group(1))
            if u.startswith('http') and u not in out:
                out.append(u)
    return out


def extract_urls(text: str) -> list[str]:
    found = []
    normalized = text.replace('\\u002F', '/').replace('\\/', '/')
    for pat in PATTERNS:
        for m in pat.finditer(normalized):
            u = m.group(0).rstrip(');,]}')
            if u not in found:
                found.append(u)
    return found


def main():
    report = {'sources': [], 'assets_checked': 0, 'candidate_urls': [], 'venue_mentions': {v: [] for v in VENUES}, 'errors': []}
    queue = []
    seen = set()

    for start in START_URLS:
        try:
            text = fetch(start)
            report['sources'].append({'url': start, 'bytes': len(text)})
            queue.extend(assets(start, text))
            report['candidate_urls'].extend(extract_urls(text))
            for v in VENUES:
                if v in text:
                    report['venue_mentions'][v].append(start)
        except Exception as e:
            report['errors'].append(f'{start}: {e}')

    # Scan a bounded set of JS/CSS assets for stream URLs and API clues.
    for url in queue[:80]:
        if url in seen:
            continue
        seen.add(url)
        try:
            text = fetch(url)
            report['assets_checked'] += 1
            for u in extract_urls(text):
                if u not in report['candidate_urls']:
                    report['candidate_urls'].append(u)
            for v in VENUES:
                if v in text and url not in report['venue_mentions'][v]:
                    report['venue_mentions'][v].append(url)
        except Exception as e:
            report['errors'].append(f'{url}: {e}')

    # Keep only plausible race/live candidates first, while preserving all if few exist.
    plausible = [u for u in report['candidate_urls'] if any(k in u.lower() for k in ('m3u8', 'cloudfront', 'live', 'stream'))]
    if plausible:
        report['candidate_urls'] = plausible

    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
