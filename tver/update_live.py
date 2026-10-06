#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from urllib.parse import quote

import requests

RESOLVER = "https://ihhiymkepuydykrhmzwo.supabase.co/functions/v1/tver-live"
OUT = Path("tver/playlist.m3u")
STATUS = Path("tver/live_status.json")
TIMEOUT = 30

LOGOS = {
    "news24": "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/contrast/tver.news24_ecf50e0e.png",
    "tbs news": "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/contrast/tver.tbs_newsdig_65e73997.png",
}

def safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "live"

def logo_for(title: str) -> str:
    low = title.lower()
    if "news24" in low:
        return LOGOS["news24"]
    if "tbs" in low and "news" in low:
        return LOGOS["tbs news"]
    return ""

def tvg_id_for(title: str, live_id: str) -> str:
    low = title.lower()
    if "news24" in low:
        return "tver.news24"
    if "tbs" in low and "news" in low:
        return "tver.tbs_newsdig"
    return "tver.special." + safe_id(live_id)

def fetch_catalog() -> dict:
    r = requests.get(
        RESOLVER,
        params={"catalog": "1", "forceFunctionRegion": "ap-northeast-1"},
        headers={"Cache-Control": "no-cache", "Pragma": "no-cache"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError("resolver catalog returned ok=false")
    return data

def build() -> None:
    data = fetch_catalog()
    specials = data.get("special") or []

    # NEWS24 / NEWS DIG are normally always present. An empty list is treated
    # as resolver discovery failure so a transient API change does not wipe
    # the previous working FreeWiFi block.
    if not specials:
        try:
            dbg = requests.get(
                RESOLVER,
                params={"debug": "home", "forceFunctionRegion": "ap-northeast-1"},
                timeout=TIMEOUT,
            ).json()
            print("TVer debug:", json.dumps(dbg, ensure_ascii=False))
            srch = requests.get(
                RESOLVER,
                params={"debug": "search", "forceFunctionRegion": "ap-northeast-1"},
                timeout=TIMEOUT,
            ).json()
            print("TVer search debug:", json.dumps(srch, ensure_ascii=False))
        except Exception as exc:
            print("TVer debug failed:", exc)
        raise SystemExit("TVer catalog returned no playable Special Live entries; keeping previous playlist")

    rows = []
    seen = set()
    for item in specials:
        live_id = str(item.get("id") or "").strip()
        title = str(item.get("title") or "").strip()
        if not re.fullmatch(r"le[a-z0-9]+", live_id, re.I):
            continue
        if not title or title in {"配信休止", "配信準備中"}:
            continue
        # TVer sometimes exposes decorative placeholder cards as live items.
        # Do not publish entries whose title has no Japanese/ASCII letters or digits.
        if not re.search(r"[A-Za-z0-9一-龯ぁ-んァ-ヶ]", title):
            continue
        if live_id in seen:
            continue
        seen.add(live_id)

        rows.append({
            "id": live_id,
            "title": title,
            "tvg_id": tvg_id_for(title, live_id),
            "logo": logo_for(title),
            "url": RESOLVER + "?special=" + quote(live_id, safe="") + "&forceFunctionRegion=ap-northeast-1",
            "start_at": item.get("startAt"),
            "end_at": item.get("endAt"),
        })

    if not rows:
        raise SystemExit("TVer catalog had no usable live IDs; keeping previous playlist")

    rows.sort(key=lambda x: x["title"])
    lines = ["#EXTM3U", "", "### TVerﾘｱﾙﾀｲﾑ", ""]

    for row in rows:
        attrs = [
            f'tvg-id="{row["tvg_id"]}"',
            f'tvg-name="{row["title"]}"',
            'group-title="TVerﾘｱﾙﾀｲﾑ"',
        ]
        if row["logo"]:
            attrs.insert(2, f'tvg-logo="{row["logo"]}"')
        lines.append(f'#EXTINF:-1 {" ".join(attrs)},{row["title"]}')
        lines.append(row["url"])
        lines.append("")

    OUT.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    STATUS.write_text(
        json.dumps(
            {
                "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "resolver": data.get("resolver"),
                "resolver_region": data.get("region"),
                "special_count": len(rows),
                "simul_on_air": data.get("simul") or [],
                "entries": rows,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print(f"TVer Special Live synced: {len(rows)}")
    for row in rows:
        print(f"  {row['id']} {row['title']}")

if __name__ == "__main__":
    build()
