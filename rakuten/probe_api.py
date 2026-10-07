#!/usr/bin/env python3
import re
from urllib.parse import urljoin
import requests

BASE="https://channel.rakuten.co.jp/"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/154 Safari/537.36"
NEEDLES=(
    "/platform/media/api/v1/content/list",
    "/platform/media/api/v1/content/:id/player/info",
    "manifestUrl",
    "CONTENT_LIST",
)

def main():
    s=requests.Session()
    h=s.get(BASE,headers={"User-Agent":UA},timeout=30)
    print("HOME",h.status_code,len(h.content),h.url)
    scripts=re.findall(r'<script[^>]+src=["\']([^"\']+)["\']',h.text,re.I)
    for src in scripts:
        u=urljoin(BASE,src)
        try:
            r=s.get(u,headers={"User-Agent":UA,"Referer":BASE},timeout=30)
        except Exception as e:
            continue
        text=r.text
        for needle in NEEDLES:
            start=0
            while True:
                pos=text.find(needle,start)
                if pos<0: break
                print("=== CONTEXT",needle,u,"pos",pos,"===")
                print(text[max(0,pos-3500):pos+5500])
                start=pos+len(needle)
    return 0
if __name__=="__main__":
    raise SystemExit(main())
