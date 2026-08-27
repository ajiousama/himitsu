#!/usr/bin/env python3
import concurrent.futures
import datetime as dt
import html
import urllib.request
import xml.etree.ElementTree as ET

UA = {"User-Agent": "Mozilla/5.0"}
JST = dt.timezone(dt.timedelta(hours=9))


def _open(url, timeout=12):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=timeout)


def _fetch_program_area(date_yyyymmdd, pref):
    area = f"JP{pref}"
    urls = [
        f"https://api.radiko.jp/program/v3/date/{date_yyyymmdd}/area/{area}.xml",
        f"https://radiko.jp/v3/program/date/{date_yyyymmdd}/{area}.xml",
    ]
    last = None
    for url in urls:
        try:
            with _open(url) as r:
                return ET.fromstring(r.read())
        except Exception as e:
            last = e
    raise last


def _xmltv_time(s):
    # radiko uses YYYYMMDDHHMMSS in Japan local time.
    if not s or len(s) < 14:
        return None
    return f"{s[:14]} +0900"


def _txt(node, name):
    v = node.findtext(name)
    return (v or "").strip()


def build_xmltv(days=3):
    today = dt.datetime.now(JST).date()
    dates = [(today + dt.timedelta(days=i)).strftime("%Y%m%d") for i in range(days)]

    roots = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        futs = {
            ex.submit(_fetch_program_area, d, p): (d, p)
            for d in dates for p in range(1, 48)
        }
        for fut in concurrent.futures.as_completed(futs):
            key = futs[fut]
            try:
                roots[key] = fut.result()
            except Exception:
                pass

    channels = {}
    programmes = []
    seen_prog = set()

    for d in dates:
        for p in range(1, 48):
            root = roots.get((d, p))
            if root is None:
                continue
            for st in root.findall(".//station"):
                sid = (st.get("id") or _txt(st, "id")).strip()
                if not sid:
                    continue
                name = (_txt(st, "name") or sid).strip()
                ch_id = f"radiko.{sid}"
                channels.setdefault(ch_id, name)
                for prog in st.findall("./progs/prog"):
                    start = _xmltv_time(prog.get("ft") or "")
                    stop = _xmltv_time(prog.get("to") or "")
                    if not start or not stop:
                        continue
                    key = (ch_id, start, stop)
                    if key in seen_prog:
                        continue
                    seen_prog.add(key)
                    programmes.append({
                        "channel": ch_id,
                        "start": start,
                        "stop": stop,
                        "title": _txt(prog, "title") or "放送中",
                        "sub_title": _txt(prog, "sub_title"),
                        "desc": _txt(prog, "desc"),
                        "info": _txt(prog, "info"),
                        "pfm": _txt(prog, "pfm"),
                    })

    tv = ET.Element("tv", {"generator-info-name": "ajiousama radiko XMLTV"})
    for ch_id, name in sorted(channels.items()):
        ch = ET.SubElement(tv, "channel", {"id": ch_id})
        ET.SubElement(ch, "display-name", {"lang": "ja"}).text = name

    for item in sorted(programmes, key=lambda x: (x["start"], x["channel"])):
        pr = ET.SubElement(tv, "programme", {
            "start": item["start"],
            "stop": item["stop"],
            "channel": item["channel"],
        })
        ET.SubElement(pr, "title", {"lang": "ja"}).text = item["title"]
        if item["sub_title"]:
            ET.SubElement(pr, "sub-title", {"lang": "ja"}).text = item["sub_title"]
        if item["pfm"]:
            ET.SubElement(pr, "credits").append(ET.Element("presenter"))
            pr.find("credits/presenter").text = item["pfm"]
        desc = item["desc"] or item["info"]
        if desc:
            ET.SubElement(pr, "desc", {"lang": "ja"}).text = desc

    return ET.tostring(tv, encoding="utf-8", xml_declaration=True)


if __name__ == "__main__":
    data = build_xmltv(3)
    open("radiko_epg.xml", "wb").write(data)
    print(f"wrote radiko_epg.xml ({len(data)} bytes)")
