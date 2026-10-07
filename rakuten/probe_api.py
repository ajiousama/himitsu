#!/usr/bin/env python3
import re
from urllib.parse import urljoin
import requests
BASE="https://channel.rakuten.co.jp/"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/154 Safari/537.36"
def main():
    s=requests.Session()
    h=s.get(BASE,headers={"User-Agent":UA},timeout=30)
    scripts=re.findall(r'<script[^>]+src=["\']([^"\']+)["\']',h.text,re.I)
    paths=set()
    for src in scripts:
        u=urljoin(BASE,src)
        try:r=s.get(u,headers={"User-Agent":UA,"Referer":BASE},timeout=30)
        except Exception:continue
        for m in re.finditer(r'/platform/[A-Za-z0-9_./:{}?=&-]+',r.text):
            paths.add(m.group(0))
    for p in sorted(paths):
        print("PATH",p)
    return 0
if __name__=="__main__":
    raise SystemExit(main())
