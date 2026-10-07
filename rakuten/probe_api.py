#!/usr/bin/env python3
import re
from urllib.parse import urljoin, urlparse
import requests

BASE="https://channel.rakuten.co.jp/"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/154 Safari/537.36"
NEEDLES=("baseURL","baseUrl","apiBase","API_BASE","NEXT_PUBLIC","platform/media","platform/core")

def contexts(text, needle, span=1800):
    out=[]
    start=0
    while True:
        p=text.find(needle,start)
        if p<0: break
        out.append(text[max(0,p-span):p+span])
        start=p+len(needle)
        if len(out)>=10: break
    return out

def main():
    s=requests.Session()
    h=s.get(BASE,headers={"User-Agent":UA},timeout=30)
    print("HOME",h.status_code,len(h.content),h.url)
    for needle in NEEDLES:
        for c in contexts(h.text,needle,1000):
            print("HOME_CONTEXT",needle,c.replace("\n"," ")[:2500])
    scripts=re.findall(r'<script[^>]+src=["\']([^"\']+)["\']',h.text,re.I)
    urls=set()
    for src in scripts:
        u=urljoin(BASE,src)
        try:
            r=s.get(u,headers={"User-Agent":UA,"Referer":BASE},timeout=30)
        except Exception:
            continue
        text=r.text
        for m in re.finditer(r'https?://[^"\'\\\s)]+',text):
            v=m.group(0)
            host=urlparse(v).netloc.lower()
            if "rakuten" in host or "r10s" in host:
                urls.add(v[:700])
        for needle in NEEDLES:
            for c in contexts(text,needle,2200):
                print("JS_CONTEXT",needle,u,c.replace("\n"," ")[:5000])
    print("ABS_URLS",len(urls))
    for u in sorted(urls):
        print("ABS",u)
    return 0
if __name__=="__main__":
    raise SystemExit(main())
