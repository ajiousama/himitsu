"""Inspect Rakuten's public programme source before enabling publication."""
import json
import re
import urllib.request
from urllib.parse import urljoin

BASE = 'https://channel.rakuten.co.jp'

def get(url):
    req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0','Referer':BASE + '/'})
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode('utf-8')

def main():
    html = get(BASE + '/schedule')
    scripts = re.findall(r'<script[^>]+src="([^"]+)"', html)
    for src in scripts:
        if '/_next/static/chunks/' not in src or any(x in src for x in ('polyfills','framework','webpack','/main-')):
            continue
        url = urljoin(BASE, src)
        text = get(url)
        urls = sorted(set(re.findall(r'https?://[^\s"\x27`<>\\]+', text)))
        relevant = [u for u in urls if any(x in u.lower() for x in ('rakuten','rchannel'))]
        snippets = [text[max(0,m.start()-500):m.end()+3000] for m in re.finditer(r'(?:iw:function|platform:|40711:function|34453:function)',text)]
        print(json.dumps({'script':url,'urls':relevant[:30],'snippets':snippets[:12]}, ensure_ascii=False))

if __name__ == '__main__':
    main()
