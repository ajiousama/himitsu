#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
import re
import urllib.request

PLAYLIST = Path("council/playlist.m3u")
JST = timezone(timedelta(hours=9))
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Safari/604.1"

COUNCILS = {
    "matsuyama": {
        "id": "ecatv.matsuyama_gikai",
        "name": "松山市議会中継",
        "logo": "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/ehime_catv/14_matsuyama_gikai.png",
        "stream": "https://cdn-ecatv-stream.durasite.net/live/ms_gikai/chunklist_w152985868.m3u8",
        "schedule": "https://www.city.matsuyama.ehime.jp/shigikai/nittei/202106_teireikai.html",
    },
    "ehime": {
        "id": "ecatv.ehime_gikai",
        "name": "愛媛県議会中継",
        "logo": "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/ehime_catv/15_ehime_gikai.png",
        "stream": "https://cdn-ecatv-stream.durasite.net/live/kengikai/chunklist_w1364306427.m3u8",
        "schedule": "https://www.pref.ehime.jp/site/gikai/156871.html",
    },
}


def fetch_text(url: str, timeout: int = 15) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Cache-Control": "no-cache"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
        ctype = r.headers.get_content_charset() or "utf-8"
    return raw.decode(ctype, errors="replace")


def html_to_text(html: str) -> str:
    html = re.sub(r"(?is)<script.*?</script>|<style.*?</style>", " ", html)
    html = re.sub(r"(?s)<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unescape(html))


def scheduled_today(url: str, now: datetime) -> bool:
    try:
        html = fetch_text(url)
    except Exception as e:
        print(f"schedule fetch failed: {url}: {type(e).__name__}: {e}")
        return False

    md = rf"{now.month}月\s*{now.day}日"
    # Prefer one HTML table row at a time. The old flattened-text check could
    # accidentally pair today's committee row with a later day's plenary row.
    for row in re.findall(r"(?is)<tr\b[^>]*>.*?</tr>", html):
        text = html_to_text(row)
        if re.search(md, text) and "本会議" in text:
            print(f"schedule check {url}: today_plenary=True")
            return True

    # Conservative fallback for non-table pages: only inspect a short local
    # window around the exact date and never reach into the next day's entry.
    text = html_to_text(html)
    for m in re.finditer(md, text):
        local_window = text[max(0, m.start() - 24):m.end() + 72]
        if "本会議" in local_window:
            print(f"schedule check {url}: today_plenary=True")
            return True

    print(f"schedule check {url}: today_plenary=False")
    return False


def stream_live(url: str) -> bool:
    try:
        text = fetch_text(url, timeout=12)
    except Exception as e:
        print(f"stream check failed: {url}: {type(e).__name__}: {e}")
        return False
    ok = text.lstrip().startswith("#EXTM3U") and (
        "#EXTINF:" in text or "#EXT-X-STREAM-INF:" in text or "#EXT-X-PART:" in text
    )
    print(f"stream check {url}: live_playlist={ok}")
    return ok


def entry(cfg: dict) -> str:
    return (
        f'#EXTINF:-1 tvg-id="{cfg["id"]}" group-title="愛媛CATV" '
        f'tvg-logo="{cfg["logo"]}",{cfg["name"]}\n'
        f'{cfg["stream"]}\n'
    )


def main() -> int:
    now = datetime.now(JST)
    active = []
    in_day_window = 9 <= now.hour < 19
    for key, cfg in COUNCILS.items():
        is_active = in_day_window and scheduled_today(cfg["schedule"], now) and stream_live(cfg["stream"])
        print(f"{key}: active={is_active}")
        if is_active:
            active.append(cfg)

    PLAYLIST.parent.mkdir(parents=True, exist_ok=True)
    lines = ["#EXTM3U", "## 議会ライブ"]
    for cfg in active:
        lines.extend(entry(cfg).rstrip().splitlines())
    PLAYLIST.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print("Council live visible:", ", ".join(cfg["name"] for cfg in active) or "(none)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
