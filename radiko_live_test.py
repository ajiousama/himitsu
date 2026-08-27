#!/usr/bin/env python3
import base64, hashlib, random, urllib.parse, urllib.request

AUTH_KEY = "bcd151073c03b352e1ef2fd66c32209da9ca0afa"
STATIONS = {"RNB": "南海放送", "JOEU-FM": "FM愛媛"}
BASE_HEADERS = {
    "X-Radiko-App": "pc_html5",
    "X-Radiko-App-Version": "0.0.1",
    "X-Radiko-Device": "pc",
    "X-Radiko-User": "dummy_user",
}

def auth():
    req = urllib.request.Request("https://radiko.jp/v2/api/auth1", headers=BASE_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        token = r.headers["X-Radiko-AuthToken"]
        off = int(r.headers["X-Radiko-KeyOffset"])
        length = int(r.headers["X-Radiko-KeyLength"])
    partial = base64.b64encode(AUTH_KEY[off:off+length].encode()).decode()
    h = dict(BASE_HEADERS)
    h.update({"X-Radiko-AuthToken": token, "X-Radiko-Partialkey": partial})
    req = urllib.request.Request("https://radiko.jp/v2/api/auth2", headers=h)
    with urllib.request.urlopen(req, timeout=30) as r:
        area = r.read().decode().strip().split(",")[0]
    return token, area

def live_url(station):
    q = urllib.parse.urlencode({
        "station_id": station, "l": 15,
        "lsid": hashlib.md5(str(random.random()).encode()).hexdigest(), "type": "b"
    })
    return "https://alliance-stream-radiko.smartstream.ne.jp/so/playlist.m3u8?" + q

def main():
    token, area = auth()
    print("radiko area:", area)
    print("NOTE: X-Radiko-AuthToken header is required for playback; token is intentionally not printed.")
    for sid, name in STATIONS.items():
        url = live_url(sid)
        req = urllib.request.Request(url, headers={"X-Radiko-AuthToken": token, "User-Agent": "Mozilla/5.0"})
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                body = r.read(4096).decode("utf-8", "replace")
            ok = "#EXTM3U" in body
            print(f"{sid} {name}: {'OK' if ok else 'NG'}")
        except Exception as e:
            print(f"{sid} {name}: NG {type(e).__name__}: {e}")

if __name__ == "__main__":
    main()
