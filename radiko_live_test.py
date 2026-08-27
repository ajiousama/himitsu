#!/usr/bin/env python3
import base64, hashlib, random, urllib.parse, urllib.request
import xml.etree.ElementTree as ET

AUTH_KEY = "bcd151073c03b352e1ef2fd66c32209da9ca0afa"
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

def station_list(area):
    url = f"https://radiko.jp/v3/station/list/{area}.xml"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        root = ET.fromstring(r.read())
    out = []
    for st in root.findall("station"):
        sid = (st.findtext("id") or "").strip()
        name = (st.findtext("name") or "").strip()
        if sid:
            out.append((sid, name or sid))
    return out

def live_url(station):
    q = urllib.parse.urlencode({
        "station_id": station, "l": 15,
        "lsid": hashlib.md5(str(random.random()).encode()).hexdigest(), "type": "b"
    })
    return "https://alliance-stream-radiko.smartstream.ne.jp/so/playlist.m3u8?" + q

def probe(token, sid):
    req = urllib.request.Request(live_url(sid), headers={
        "X-Radiko-AuthToken": token,
        "User-Agent": "Mozilla/5.0",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read(4096).decode("utf-8", "replace")
    return "#EXTM3U" in body

def main():
    token, area = auth()
    print("radiko detected area:", area)
    print("NOTE: token is intentionally not printed.")

    stations = station_list(area)
    print(f"free station list for {area}: {len(stations)} stations")
    ok_count = 0
    for sid, name in stations:
        try:
            ok = probe(token, sid)
            ok_count += int(ok)
            print(f"{sid}\t{name}\t{'OK' if ok else 'NG'}")
        except Exception as e:
            print(f"{sid}\t{name}\tNG {type(e).__name__}: {e}")
    print(f"LIVE probe result: {ok_count}/{len(stations)} OK")

if __name__ == "__main__":
    main()
