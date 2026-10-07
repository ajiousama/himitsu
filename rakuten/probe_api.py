#!/usr/bin/env python3
import json, sys
import requests

BASE = "https://gizmo.rakuten.tv/v3"
PARAMS = {
    "classification_id": 309,
    "device_identifier": "web",
    "locale": "jp",
    "market_code": "jp",
}
HEADERS = {
    "Origin": "https://rakuten.tv",
    "Referer": "https://rakuten.tv/",
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/154 Safari/537.36",
}
KEYWORDS = ("刺激", "グラビア", "年齢制限", "NECO", "セクシー", "歓楽街")

def main():
    s = requests.Session()
    r = s.get(BASE + "/live_channels", headers=HEADERS, params={**PARAMS, "page": 1, "per_page": 100}, timeout=20)
    print("live_channels:", r.status_code, r.url)
    if r.status_code != 200:
        print(r.text[:1000])
        return 0
    data = r.json().get("data") or []
    print("channel_count:", len(data))
    hits = []
    for ch in data:
        title = str(ch.get("title") or "")
        if any(k.lower() in title.lower() for k in KEYWORDS):
            hits.append(ch)
    print("matches:", len(hits))
    for ch in hits:
        print("CHANNEL", json.dumps({
            "id": ch.get("id"),
            "numerical_id": ch.get("numerical_id"),
            "channel_number": ch.get("channel_number"),
            "title": ch.get("title"),
            "type": ch.get("type"),
            "labels": ch.get("labels"),
        }, ensure_ascii=False))
        langs = ((ch.get("labels") or {}).get("languages") or [])
        audio = (langs[0].get("id") if langs and isinstance(langs[0], dict) else "JA")
        body = {
            "audio_language": audio,
            "audio_quality": "2.0",
            "classification_id": 309,
            "content_id": ch.get("id"),
            "content_type": "live_channels",
            "device_serial": "not implemented",
            "player": "web:HLS-NONE:NONE",
            "strict_video_quality": False,
            "subtitle_language": "MIS",
            "video_type": "stream",
        }
        rr = s.post(BASE + "/avod/streamings", headers=HEADERS, params=PARAMS, json=body, timeout=20)
        print("STREAM_STATUS", ch.get("title"), rr.status_code)
        if rr.status_code != 200:
            print(rr.text[:1000])
            continue
        payload = rr.json()
        infos = (payload.get("data") or {}).get("stream_infos") or []
        for info in infos[:3]:
            url = info.get("url") or ""
            base = url.split(".m3u8", 1)[0] + ".m3u8" if ".m3u8" in url else url
            print("STREAM", ch.get("title"), base)
            try:
                test = s.get(base, headers=HEADERS, timeout=15, stream=True)
                print("STREAM_GET", ch.get("title"), test.status_code, test.url)
                test.close()
            except Exception as e:
                print("STREAM_GET_ERROR", ch.get("title"), type(e).__name__, str(e)[:200])
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
