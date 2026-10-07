#!/usr/bin/env python3
import json, re
import requests

BASE = "https://gizmo.rakuten.tv/v3"
HEADERS = {
    "Origin": "https://www.rakuten.tv",
    "Referer": "https://www.rakuten.tv/",
    "Accept": "application/json, text/plain, */*",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/154 Safari/537.36",
}
PARAMS = {
    "classification_id": 309,
    "device_identifier": "web",
    "device_stream_audio_quality": "2.0",
    "device_stream_hdr_type": "NONE",
    "device_stream_video_quality": "FHD",
    "live_channel_support": "true",
    "locale": "en",
    "market_code": "jp",
    "user_status": "visitor",
}
KEYWORDS = ("刺激", "グラビア", "年齢制限", "NECO", "セクシー", "歓楽街",
            "shigeki", "gravure", "adult", "mens", "sexy")

def walk(obj, path="$"):
    if isinstance(obj, dict):
        blob = json.dumps(obj, ensure_ascii=False).lower()
        if any(k.lower() in blob for k in KEYWORDS):
            slim = {}
            for k in ("id","title","name","type","content_type","live_channel_id","channel_id","numerical_id","channel_number"):
                if k in obj:
                    slim[k]=obj[k]
            if slim:
                print("HIT", path, json.dumps(slim, ensure_ascii=False))
        for k,v in obj.items():
            walk(v, path+"."+str(k))
    elif isinstance(obj, list):
        for i,v in enumerate(obj):
            walk(v, f"{path}[{i}]")

def main():
    s=requests.Session()
    r=s.get(BASE+"/skeleton/gardens/default", headers=HEADERS, params=PARAMS, timeout=30)
    print("skeleton:", r.status_code, r.url)
    print("content_type:", r.headers.get("content-type"))
    if r.status_code != 200:
        print(r.text[:3000])
        return 0
    try:
        data=r.json()
    except Exception:
        print(r.text[:5000])
        return 0
    print("top_keys:", list(data)[:30])
    print("json_bytes:", len(r.content))
    walk(data)
    return 0

if __name__=="__main__":
    raise SystemExit(main())
