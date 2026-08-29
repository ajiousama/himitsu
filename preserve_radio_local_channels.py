#!/usr/bin/env python3
import os
import re
import urllib.parse
from pathlib import Path

from radiko_freewifi import discover_stations

FREEWIFI = Path("freewifi")
START = "# === LOCAL_RADIO_KEEP_START ==="
END = "# === LOCAL_RADIO_KEEP_END ==="
OLD_START = "# === NETGEN_LOCAL_KEEP_START ==="
OLD_END = "# === NETGEN_LOCAL_KEEP_END ==="
RADIKO_START = "# === RADIKO_MANAGED_START ==="
BASE = os.environ.get("RADIKO_PUBLIC_BASE", "https://himitsu-six.vercel.app").rstrip("/")


def wanted(meta, sid):
    pref = meta.get("pref")
    name = meta.get("name", "")
    if pref == 38:
        return "愛媛（ラジオ）"
    if pref == 27:
        return "在阪（ラジオ）"
    if pref == 26 and (sid.upper() == "KBS" or "KBS京都" in name or "ALPHA-STATION" in name.upper() or "α-STATION" in name.upper()):
        return "京都（ラジオ）"
    if pref == 25 and ("E-RADIO" in name.upper() or "E RADIO" in name.upper() or "FM滋賀" in name):
        return "滋賀（ラジオ）"
    if pref == 28 and ("ラジオ関西" in name or sid.upper() in {"CRK", "JOCR"}):
        return "兵庫（ラジオ）"
    return None


def build_block(stations):
    rows = []
    for sid, meta in stations.items():
        group = wanted(meta, sid)
        if not group:
            continue
        name = meta.get("name", sid).replace("\n", " ").strip()
        if not name.endswith("（ラジオ）"):
            name += "（ラジオ）"
        logo = (meta.get("logo") or "").replace('"', "%22")
        station = urllib.parse.quote(sid, safe="")
        rows.append((meta.get("pref", 99), name, sid, logo, group, f"{BASE}/api/radiko?station={station}"))
    rows.sort()

    lines = [START, "## FreeWiFiに残すラジオ（愛媛＋在阪＋京都＋滋賀＋ラジオ関西）"]
    for _, name, sid, logo, group, url in rows:
        lines.append(f'#EXTINF:-1 tvg-id="radiko.{sid}" tvg-logo="{logo}" group-title="{group}",{name}')
        lines.append(url)
    lines.append(END)
    return "\n".join(lines), rows


def main():
    text = FREEWIFI.read_text(encoding="utf-8-sig")
    text = re.sub(rf"\n?{re.escape(OLD_START)}.*?{re.escape(OLD_END)}\n?", "\n", text, flags=re.S)
    text = re.sub(rf"\n?{re.escape(START)}.*?{re.escape(END)}\n?", "\n", text, flags=re.S)

    stations = discover_stations()
    block, rows = build_block(stations)
    if len(rows) < 11:
        raise SystemExit(f"local radio selection too small: {len(rows)}")

    marker = RADIKO_START if RADIKO_START in text else "# === NHK_RADIO_MANAGED_START ==="
    if marker in text:
        text = text.replace(marker, block + "\n\n" + marker, 1)
    else:
        text = text.rstrip() + "\n\n" + block + "\n"

    FREEWIFI.write_text(text, encoding="utf-8")
    print("kept local radio copies:", ", ".join(name for _, name, *_ in rows))


if __name__ == "__main__":
    main()
