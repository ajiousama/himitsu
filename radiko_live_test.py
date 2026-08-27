#!/usr/bin/env python3
import base64, concurrent.futures, hashlib, json, os, random, urllib.parse, urllib.request, xml.etree.ElementTree as ET

AUTH_KEY = "bcd151073c03b352e1ef2fd66c32209da9ca0afa"
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
    print("radiko detected area:", area)
    print("NOTE: session/token are intentionally not printed.")
    return token, area


def discover_stations():
    stations = {}
    for n in range(1, 48):
        area = f"JP{n}"
        url = f"https://radiko.jp/v3/station/list/{area}.xml"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as r:
                root = ET.fromstring(r.read())
        except Exception as e:
            print(f"station list {area}: skip {type(e).__name__}")
            continue
        for st in root.findall("station"):
            sid = (st.findtext("id") or "").strip()
            name = (st.findtext("name") or sid).strip()
            if sid:
                stations.setdefault(sid, name)
    print("discovered stations:", len(stations))
    return stations


def playlist_create_url(station):
    try:
        req = urllib.request.Request(
            f"https://radiko.jp/v3/station/stream/pc_html5/{station}.xml",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            root = ET.fromstring(r.read())
    except Exception:
        return None
    for url in root.findall("url"):
        if url.get("areafree") == "1":
            node = url.find("playlist_create_url")
            if node is not None and node.text:
                return node.text.strip()
    return None


def test_station(token, area, station, name):
    base = playlist_create_url(station)
    if not base:
        return station, name, False, "no area-free playlist URL"
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
        "User-Agent": "Mozilla/5.0",
    }
    if area and area != "OUT":
        headers["X-Radiko-AreaId"] = area
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as r:
            body = r.read(4096).decode("utf-8", "replace")
        ok = "#EXTM3U" in body
        return station, name, ok, "OK" if ok else "not m3u8"
    except Exception as e:
        return station, name, False, f"{type(e).__name__}: {e}"


def main():
    session, areafree = premium_login()
    if not areafree:
        raise SystemExit("Premium login succeeded but area-free is not enabled")
    token, area = auth(session)
    stations = discover_stations()
    if not stations:
        raise SystemExit("No radiko stations discovered")

    oks = []
    ngs = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
        futures = [ex.submit(test_station, token, area, sid, name) for sid, name in stations.items()]
        for fut in concurrent.futures.as_completed(futures):
            sid, name, ok, detail = fut.result()
            print(f"{sid} {name}: {'OK' if ok else 'NG'} {detail if not ok else ''}".rstrip())
            (oks if ok else ngs).append((sid, name))

    oks.sort()
    ngs.sort()
    print("=== SUMMARY ===")
    print("LIVE OK count:", len(oks))
    print("LIVE NG count:", len(ngs))
    print("LIVE OK stations:")
    for sid, name in oks:
        print(f"  {sid}\t{name}")
    if not oks:
        raise SystemExit("No station LIVE succeeded")


if __name__ == "__main__":
    main()
