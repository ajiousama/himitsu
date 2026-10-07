#!/usr/bin/env python3
import json
import requests

BASE="https://channel.rakuten.co.jp"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/154 Safari/537.36"
KEYS=("刺激","グラビア","年齢制限","NECO","セクシー","歓楽街","shigeki","gravure","adult","mens","sexy")

def walk(obj,path="$"):
    if isinstance(obj,dict):
        blob=json.dumps(obj,ensure_ascii=False).lower()
        if any(k.lower() in blob for k in KEYS):
            slim={k:obj.get(k) for k in ("id","channelId","title","name","manifestUrl","platform","rating","genreName") if k in obj}
            if slim:
                print("HIT",path,json.dumps(slim,ensure_ascii=False))
        for k,v in obj.items():
            walk(v,path+"."+str(k))
    elif isinstance(obj,list):
        for i,v in enumerate(obj):
            walk(v,f"{path}[{i}]")

def main():
    s=requests.Session()
    h={"User-Agent":UA,"Accept":"application/json, text/plain, */*","Referer":BASE+"/"}
    home=s.get(BASE+"/",headers=h,timeout=30)
    print("HOME",home.status_code,len(home.content))
    candidates=[
        BASE+"/platform/media/api/v1/content/list",
        BASE+"/platform/media/api/v1/content/list?limit=200",
        BASE+"/platform/media/api/v1/content/list?page=1&limit=200",
    ]
    for u in candidates:
        try:
            r=s.get(u,headers=h,timeout=30)
        except Exception as e:
            print("REQ_ERR",u,type(e).__name__,str(e)[:300]); continue
        print("REQ",r.status_code,u,"ctype",r.headers.get("content-type"),"bytes",len(r.content))
        print("BODY_HEAD",r.text[:1200].replace("\n"," "))
        if r.status_code==200 and "json" in (r.headers.get("content-type") or ""):
            try:
                data=r.json()
                print("TOP",list(data)[:30] if isinstance(data,dict) else type(data).__name__)
                walk(data)
            except Exception as e:
                print("JSON_ERR",type(e).__name__,str(e))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
