#!/usr/bin/env python3
import base64, json, os, random, hashlib, urllib.parse, urllib.request, xml.etree.ElementTree as ET

AUTH_KEY = "bcd151073c03b352e1ef2fd66c32209da9ca0afa"
STATIONS = {
    "RNB": "南海放送",
    "JOEU-FM": "FM愛媛",
    "MBS": "MBSラジオ",
    "ABC": "ABCラジオ",
    "OBC": "ラジオ大阪",
    "FM802": "FM802",
    "FMO": "FM大阪",
    "CCL": "FM COCOLO",
    "KBS": "KBS京都ラジオ",
}
BASE_HEADERS = {
    "X-Radiko-App": "pc_html5",
    "X-Radiko-App-Version": "0.0.1",
    "X-Radiko-Device": "pc",
    "X-Radiko-User": "dummy_user",
}

def premium_login():
    mail = os.environ.get("RADIKO_MAIL", "").strip()
    password = os.environ.get("RADIKO_PASSWORD", "").strip()
    if not mail or not password:
        raise SystemExit("RADIKO_MAIL / RADIKO_PASSWORD are not set")
    data = urllib.parse.urlencode({"mail": mail, "pass": password}).encode()
    req = urllib.request.Request("https://radiko.jp/v4/api/member/login", data=data, method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        obj = json.loads(r.read().decode("utf-8"))
    session = str(obj.get("radiko_session") or "").strip()
    areafree = str(obj.get("areafree") or "0")
    if not session:
        raise SystemExit("radiko premium login failed")
    print("premium login: OK")
    print("areafree:", areafree)
    return session, areafree == "1"

def auth(session):
    req = urllib.request.Request("https://radiko.jp/v2/api/auth1", headers=BASE_HEADERS)
    with urllib.request.urlopen(req, timeout=30) as r:
        token = r.headers["X-Radiko-AuthToken"]
        off = int(r.headers["X-Radiko-KeyOffset"])
        length = int(r.headers["X-Radiko-KeyLength"])
    partial = base64.b64encode(AUTH_KEY[off:off+length].encode()).decode()
    h = dict(BASE_HEADERS)
    h.update({"X-Radiko-AuthToken": token, "X-Radiko-Partialkey": partial})
    url = "https://radiko.jp/v2/api/auth2?radiko_session=" + urllib.parse.quote(session)
    req = urllib.request.Request(url, headers=h)
    with urllib.request.urlopen(req, timeout=30) as r:
        body = r.read().decode().strip()
    area = body.split(",")[0] if body else "OUT"
    if area == "OUT":
        raise SystemExit("premium auth returned OUT")
    print("radiko detected area:", area)
    print("NOTE: session/token are intentionally not printed.")
    return token, area

def playlist_create_url(station, areafree):
    req = urllib.request.Request(f"https://radiko.jp/v3/station/stream/pc_html5/{station}.xml")
    with urllib.request.urlopen(req, timeout=30) as r:
        root = ET.fromstring(r.read())
    wanted = "1" if areafree else "0"
    for url in root.findall("url"):
        if url.get("areafree") == wanted:
            node = url.find("playlist_create_url")
            if node is not None and node.text:
                return node.text.strip()
    return None

def test_station(token, area, station, name, areafree):
    base = playlist_create_url(station, areafree)
    if not base:
        print(f"{station} {name}: NG no playlist URL")
        return False
    q = urllib.parse.urlencode({
        "station_id": station,
        "l": 15,
        "lsid": hashlib.md5(str(random.random()).encode()).hexdigest(),
        "type": "b",
    })
    sep = "&" if "?" in base else "?"
    url = base + sep + q
    headers = {
        "X-Radiko-AuthToken": token,
        "X-Radiko-AreaId": area,
        "User-Agent": "Mozilla/5.0",
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            body = r.read(4096).decode("utf-8", "replace")
        ok = "#EXTM3U" in body
        print(f"{station} {name}: {'OK' if ok else 'NG'}")
        return ok
    except Exception as e:
        print(f"{station} {name}: NG {type(e).__name__}: {e}")
        return False

def main():
    session, areafree = premium_login()
    if not areafree:
        raise SystemExit("Premium login succeeded but area-free is not enabled")
    token, area = auth(session)
    oks = []
    for sid, name in STATIONS.items():
        if test_station(token, area, sid, name, True):
            oks.append(sid)
    print("LIVE OK:", ",".join(oks) if oks else "none")
    if not oks:
        raise SystemExit("No station LIVE succeeded")

if __name__ == "__main__":
    main()
