#!/usr/bin/env python3
import re
from urllib.parse import urljoin
import requests

BASE="https://channel.rakuten.co.jp/"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/154 Safari/537.36"
KEYS=("fast.rakuten.tv","rtv_channel_name","playback","streaming","stream_url","streamUrl","hls","m3u8","channelId","channel_id","api/")

def main():
    s=requests.Session()
    r=s.get(BASE,headers={"User-Agent":UA},timeout=30)
    print("HOME",r.status_code,len(r.content),r.url)
    html=r.text
    scripts=re.findall(r'<script[^>]+src=["\']([^"\']+)["\']',html,re.I)
    print("SCRIPTS",len(scripts))
    for src in scripts:
        print("SCRIPT_SRC",urljoin(BASE,src))
    for src in scripts:
        u=urljoin(BASE,src)
        try:
            rr=s.get(u,headers={"User-Agent":UA,"Referer":BASE},timeout=30)
        except Exception as e:
            print("SCRIPT_ERR",u,type(e).__name__)
            continue
        text=rr.text
        hits=[]
        low=text.lower()
        if any(k.lower() in low for k in KEYS):
            # Pull URLs and compact snippets around high-value terms.
            for pat in (r'https?://[^"\'\\\s]+', r'/api/[A-Za-z0-9_./?=&{}:-]+'):
                for m in re.finditer(pat,text):
                    val=m.group(0)
                    if any(k.lower() in val.lower() for k in ("rakuten","stream","channel","play","api")):
                        hits.append(val[:500])
            for key in KEYS:
                pos=low.find(key.lower())
                if pos>=0:
                    snippet=text[max(0,pos-220):pos+420].replace("\n"," ")
                    hits.append("SNIP "+key+" "+snippet[:700])
        if hits:
            print("SCRIPT_HIT",u,"bytes",len(rr.content))
            seen=set()
            for h in hits:
                if h in seen: continue
                seen.add(h)
                print(h)
                if len(seen)>=40: break
    return 0

if __name__=="__main__":
    raise SystemExit(main())
