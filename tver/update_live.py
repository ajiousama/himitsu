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
TIMEOUT = 45

LOGOS = {
    "news24": "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/contrast/tver.news24_ecf50e0e.png",
    "tbs news": "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/contrast/tver.tbs_newsdig_65e73997.png",
    "politics": "https://raw.githubusercontent.com/ajiousama/himitsu/main/tver/logos/politics_live.jpg",
    "sports": "https://raw.githubusercontent.com/ajiousama/himitsu/main/tver/logos/sports_live.jpg",
}

# Keep the user-adopted politics/sports logos stable on every 10-minute refresh.
POLITICS_RE = re.compile(r"政治|国会|参議院|衆議院|首相|選挙|党首|内閣|政党|党大会")
SPORTS_RE = re.compile(
    r"スポーツ|野球|巨人|阪神|DeNA|中日|広島|ヤクルト|クライマックス|日本シリーズ|"
    r"サッカー|Jリーグ|駅伝|マラソン|競馬|GⅠ|GⅡ|GI|GII|"
    r"テニス|バスケ|バレー|ゴルフ|ラグビー|陸上|オリンピック|"
    r"フィギュア|スケート|水泳|卓球|相撲|格闘技|柔道|"
    r"ソフトボール|スポーツ中継|トーナメント|ワールドカップ",
    re.I,
)


def safe_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value).strip("_") or "live"


def clean_title(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def useful_title(title: str) -> bool:
    if not title or title in {"配信休止", "配信準備中"}:
        return False
    return bool(re.search(r"[A-Za-z0-9一-龯ぁ-んァ-ヶ]", title))


def logo_for(title: str, series_title: str = "") -> str:
    low = title.lower()
    if "news24" in low:
        return LOGOS["news24"]
    if "tbs" in low and "news" in low:
        return LOGOS["tbs news"]
    combined = title + " " + series_title
    if POLITICS_RE.search(combined):
        return LOGOS["politics"]
    if SPORTS_RE.search(combined):
        return LOGOS["sports"]
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


def normalize(items: list[dict]) -> list[dict]:
    rows: list[dict] = []
    seen: set[str] = set()
    for item in items:
        live_id = str(item.get("id") or "").strip()
        title = clean_title(item.get("title"))
        if not re.fullmatch(r"le[a-z0-9]+", live_id, re.I):
            continue
        if not useful_title(title):
            continue
        if live_id in seen:
            continue
        seen.add(live_id)

        rows.append({
            "id": live_id,
            "title": title,
            "series_title": clean_title(item.get("seriesTitle")),
            "broadcaster": clean_title(item.get("broadcasterName")),
            "tvg_id": tvg_id_for(title, live_id),
            "logo": logo_for(title, clean_title(item.get("seriesTitle"))),
            "url": RESOLVER + "?special=" + quote(live_id, safe="") + "&forceFunctionRegion=ap-northeast-1",
            "start_at": item.get("startAt"),
            "end_at": item.get("endAt"),
        })
    return rows


def build() -> None:
    data = fetch_catalog()
    active = normalize(data.get("special") or [])
    schedule = normalize(data.get("schedule") or [])

    # The public Special Live page is now the primary discovery source. A fully
    # empty schedule is treated as a discovery outage so a temporary TVer page
    # failure never wipes the known state.
    if not schedule:
        try:
            dbg = requests.get(
                RESOLVER,
                params={"debug": "page", "forceFunctionRegion": "ap-northeast-1"},
                timeout=TIMEOUT,
            ).json()
            print("TVer page debug:", json.dumps(dbg, ensure_ascii=False))
        except Exception as exc:
            print("TVer page debug failed:", exc)
        raise SystemExit("TVer public Special Live schedule is empty; keeping previous state")

    active.sort(key=lambda x: x["title"])
    schedule.sort(key=lambda x: (int(x.get("start_at") or 0), x["title"]))

    lines = ["#EXTM3U", "", "### TVerﾘｱﾙﾀｲﾑ", ""]
    for row in active:
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
                "discovery_source": "tver_public_page_authoritative_plus_search_v13",
                "special_count": len(active),
                "schedule_count": len(schedule),
                "simul_on_air": data.get("simul") or [],
                "entries": active,
                "schedule": schedule,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )

    print(f"TVer Special Live synced: active={len(active)} scheduled={len(schedule)}")
    for row in active:
        print(f"  LIVE {row['id']} {row['title']}")
    for row in schedule:
        if row["id"] not in {x["id"] for x in active}:
            print(f"  NEXT {row['id']} {row['start_at']} {row['title']}")


if __name__ == "__main__":
    build()
