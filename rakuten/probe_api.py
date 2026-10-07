#!/usr/bin/env python3
import json
import requests

FRONT="https://channel.rakuten.co.jp"
API="https://backendapi.channel.rakuten.co.jp"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/154 Safari/537.36"
KEYS=("刺激","グラビア","年齢制限","NECO","セクシー","歓楽街","shigeki","gravure","adult","mens","sexy")

def walk(obj,path="$"):
    if isinstance(obj,dict):
        blob=json.dumps(obj,ensure_ascii=False).lower()
        if any(k.lower() in blob for k in KEYS):
            slim={k:obj.get(k) for k in ("id","channelId","title","name","manifestUrl","platform","rating","genreName","order","type") if k in obj}
            if slim: print("HIT",path,json.dumps(slim,ensure_ascii=False))
        for k,v in obj.items(): walk(v,path+"."+str(k))
    elif isinstance(obj,list):
        for i,v in enumerate(obj): walk(v,f"{path}[{i}]")

def summarize(data):
    if isinstance(data,dict):
        d=data.get("data")
        if isinstance(d,list): return f"list:{len(d)}"
        if isinstance(d,dict): return "dict:"+",".join(list(d)[:20])
        return type(d).__name__
    return type(data).__name__

def main():
    s=requests.Session()
    headers={"User-Agent":UA,"Accept":"application/json, text/plain, */*","Origin":FRONT,"Referer":FRONT+"/"}
    s.get(FRONT+"/",headers=headers,timeout=30)
    for typ in list(range(0,16))+["channel","channels","live","tv","all"]:
        u=API+"/platform/media/api/v1/content/list"
        try:
            r=s.get(u,headers=headers,params={"type":typ,"platform":1},timeout=30)
        except Exception as e:
            print("ERR",typ,type(e).__name__); continue
        print("TYPE",repr(typ),"STATUS",r.status_code,"BYTES",len(r.content))
        try:
            data=r.json()
            print("SUMMARY",repr(typ),summarize(data))
            if r.status_code==200:
                walk(data)
            else:
                err=(data.get("error") if isinstance(data,dict) else None)
                print("ERROR",repr(typ),json.dumps(err,ensure_ascii=False))
        except Exception:
            print("BODY",repr(typ),r.text[:500])
    return 0
if __name__=="__main__":
    raise SystemExit(main())
