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
    vals=list(range(0,41))+["ALL","LIVE","NORMAL","RESTRICTED","AGE","ADULT","R15","R18","CHANNEL","TV","FREE","OTHER","1","2","3","4","5"]
    for typ in vals:
        try:
            r=s.get(API+"/platform/media/api/v1/content/list",headers=h,params={"type":typ,"platform":"WEB"},timeout=20)
            print("TYPE",repr(typ),"STATUS",r.status_code,"BYTES",len(r.content))
            try:
                d=r.json()
                err=d.get("error") if isinstance(d,dict) else None
                data=d.get("data") if isinstance(d,dict) else None
                print("RESP",repr(typ),json.dumps({"status":d.get("status") if isinstance(d,dict) else None,"error":err,"data_type":type(data).__name__,"data_len":len(data) if isinstance(data,(list,dict)) else None},ensure_ascii=False))
                if r.status_code==200:
                    print("DATA_HEAD",repr(typ),json.dumps(data,ensure_ascii=False)[:3000])
            except Exception:
                print("BODY",repr(typ),r.text[:500])
        except Exception as e:
            print("ERR",repr(typ),type(e).__name__,str(e)[:200])
    return 0
if __name__=="__main__":
    raise SystemExit(main())
