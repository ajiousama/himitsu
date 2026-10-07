#!/usr/bin/env python3
import json
import requests
FRONT="https://channel.rakuten.co.jp"
API="https://backendapi.channel.rakuten.co.jp"
UA="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/154 Safari/537.36"

def main():
    s=requests.Session()
    h={"User-Agent":UA,"Accept":"application/json, text/plain, */*","Origin":FRONT,"Referer":FRONT+"/"}
    s.get(FRONT+"/",headers=h,timeout=30)
    vals=["web","WEB","Web","pc","PC","browser","BROWSER","web_pc","desktop","1","0",0,1,2,4,8,16]
    for p in vals:
        try:
            r=s.get(API+"/platform/media/api/v1/content/list",headers=h,params={"type":0,"platform":p},timeout=20)
            print("PLATFORM",repr(p),"STATUS",r.status_code,"BYTES",len(r.content))
            try:
                d=r.json()
                print("RESP",repr(p),json.dumps({"status":d.get("status"),"error":d.get("error"),"data_type":type(d.get("data")).__name__},ensure_ascii=False))
            except Exception:
                print("BODY",repr(p),r.text[:500])
        except Exception as e:
            print("ERR",repr(p),type(e).__name__,str(e)[:200])
    return 0
if __name__=="__main__":
    raise SystemExit(main())
