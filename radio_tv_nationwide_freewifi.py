#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import urllib.parse
import urllib.request
from pathlib import Path

FREEWIFI = Path("freewifi")
RADIKO_LIST = "https://himitsu-six.vercel.app/api/radiko?list=1"
RENDER_BASE = "https://ajiousama-radiko.onrender.com"
NHK_FM_MATSUYAMA = "https://simul2.drdi.st.nhk/live/17/joined/master.m3u8"
REGION_ORDER = ["北海道", "東北", "関東", "甲信越", "東海", "近畿", "中国", "四国", "九州沖縄"]


def fetch_stations() -> dict[str, dict]:
    req = urllib.request.Request(RADIKO_LIST, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        payload = json.loads(r.read().decode("utf-8", "replace"))
    stations = payload.get("stations") or {}
    if not isinstance(stations, dict) or len(stations) < 100:
        raise RuntimeError(f"radiko station discovery too small: {len(stations) if isinstance(stations, dict) else 0}")
    return stations


def esc_attr(value: str) -> str:
    return value.replace("&", "&amp;").replace('"', "&quot;")


def station_entry(sid: str, meta: dict) -> str:
    name = html.unescape(str(meta.get("name") or sid)).strip() or sid
    logo = f"https://radiko.jp/v2/static/station/logo/{urllib.parse.quote(sid, safe='')}/lrtrim/688x160.png"
    return (
        f'#EXTINF:-1 tvg-id="radiko.{esc_attr(sid)}" tvg-logo="{logo}" group-title="ラジオ",{name}\n'
        f'{RENDER_BASE}/radio-tv/{urllib.parse.quote(sid, safe="")}\n'
    )


def build_block(stations: dict[str, dict]) -> str:
    lines: list[str] = ["## ラジオ", "", "### 松山（固定）", ""]

    # Keep the Matsuyama local NHK services easy to find. R1 uses Radiko JOZK;
    # NHK-FM Matsuyama is not on Radiko, so preserve the current direct feed.
    jozk = stations.get("JOZK", {"name": "NHKラジオ第1（松山）", "region": "四国"})
    lines.append(station_entry("JOZK", jozk).rstrip())
    lines.append("")
    lines.extend([
        '#EXTINF:-1 tvg-id="nhk_fm_matsuyama" tvg-logo="https://upload.wikimedia.org/wikipedia/commons/b/bb/NHK_logo_2020.svg" group-title="ラジオ",NHK-FM（松山）',
        NHK_FM_MATSUYAMA,
        "",
    ])

    for region in REGION_ORDER:
        region_items = [
            (sid, meta) for sid, meta in stations.items()
            if sid != "JOZK" and str(meta.get("region") or "") == region
        ]
        if not region_items:
            continue
        lines.extend([f"### {region}", ""])
        for sid, meta in sorted(region_items, key=lambda x: (int(x[1].get("pref") or 99), html.unescape(str(x[1].get("name") or x[0])), x[0])):
            lines.append(station_entry(sid, meta).rstrip())
            lines.append("")

    return "\n".join(lines).rstrip() + "\n\n"


def main() -> int:
    text = FREEWIFI.read_text(encoding="utf-8-sig", errors="replace")
    start = text.find("## ラジオ")
    end = text.find("## 愛媛CATV", start + 1)
    if start < 0 or end < 0 or end <= start:
        raise RuntimeError("could not locate radio section boundaries")

    stations = fetch_stations()
    block = build_block(stations)
    updated = text[:start] + block + text[end:]

    # Safety checks: preserve non-radio content and the Matsuyama FM exception.
    if "## Rakuten-JP" not in updated:
        raise RuntimeError("Rakuten-JP section disappeared; refusing to write")
    if NHK_FM_MATSUYAMA not in updated:
        raise RuntimeError("NHK-FM Matsuyama direct feed disappeared; refusing to write")
    render_count = updated.count(RENDER_BASE + "/radio-tv/")
    if render_count < 100:
        raise RuntimeError(f"nationwide Render radio count too small: {render_count}")

    FREEWIFI.write_text(updated, encoding="utf-8")
    print(f"Nationwide RADIO written: {render_count} image+audio stations + NHK-FM Matsuyama direct")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
