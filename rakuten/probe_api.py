#!/usr/bin/env python3
import json, requests
FRONT="https://channel.rakuten.co.jp"
API="https://backendapi.channel.rakuten.co.jp"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/154 Safari/537.36"
KEYS=("刺激","グラビア","年齢制限","NECO","セクシー","歓楽街","shigeki","gravure","adult","mens","sexy")

def walk(obj,path="$"):
    if isinstance(obj,dict):
        blob=json.dumps(obj,ensure_ascii=False).lower()
        if any(k.lower() in blob for k in KEYS):
            slim={k:obj.get(k) for k in ("id","channelId","title","name","manifestUrl","platform","rating","genreName","order") if k in obj}
            print("HIT",path,json.dumps(slim,ensure_ascii=False))
        for k,v in obj.items(): walk(v,path+"."+str(k))
    elif isinstance(obj,list):
        for i,v in enumerate(obj): walk(v,f"{path}[{i}]")

def main():
    s=requests.Session()
    h={"User-Agent":UA,"Accept":"application/json, text/plain, */*","Origin":FRONT,"Referer":FRONT+"/"}
    s.get(FRONT+"/",headers=h,timeout=30)
    for path in ("/platform/content/channels","/platform/content/now-playing"):
        u=API+path
        r=s.get(u,headers=h,timeout=30)
        print("REQ",path,r.status_code,len(r.content),r.headers.get("content-type"))
        print("BODY_HEAD",r.text[:2000].replace("\n"," "))
        if r.status_code==200:
            try:
                data=r.json()
                print("TOP",type(data).__name__, list(data)[:30] if isinstance(data,dict) else "")
                walk(data)
            except Exception as e:
                print("JSON_ERR",type(e).__name__,str(e))
    return 0
if __name__=="__main__":
    raise SystemExit(main())
