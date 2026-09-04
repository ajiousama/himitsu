#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
import re
import urllib.request

FREEWIFI = Path("freewifi")
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
        text = html_to_text(fetch_text(url))
    except Exception as e:
        print(f"schedule fetch failed: {url}: {type(e).__name__}: {e}")
        return False
    md = rf"{now.month}月\s*{now.day}日"
    # Only plenary-session days are eligible. Committee-only days stay hidden.
    hit = re.search(md + r".{0,180}?本会議", text)
    print(f"schedule check {url}: today_plenary={bool(hit)}")
    return bool(hit)


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


def strip_entry(text: str, tvg_id: str) -> str:
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#EXTINF:") and f'tvg-id="{tvg_id}"' in line:
            i += 1
            while i < len(lines) and not lines[i].startswith("#EXTINF:") and not lines[i].startswith("## ") and not lines[i].startswith("# ==="):
                i += 1
            continue
        out.append(line)
        i += 1
    return "\n".join(out).rstrip() + "\n"


def entry(cfg: dict) -> str:
    return (
        f'#EXTINF:-1 tvg-id="{cfg["id"]}" group-title="愛媛CATV" '
        f'tvg-logo="{cfg["logo"]}",{cfg["name"]}\n'
        f'{cfg["stream"]}\n'
    )


def main() -> int:
    if not FREEWIFI.exists():
        raise SystemExit("freewifi not found")
    now = datetime.now(JST)
    text = FREEWIFI.read_text(encoding="utf-8-sig", errors="replace")

    # Hide by default. Only re-add after both official-schedule and live-HLS checks pass.
    for cfg in COUNCILS.values():
        text = strip_entry(text, cfg["id"])

    active = []
    # Practical live window; prevents overnight stale playlists from surfacing.
    in_day_window = 9 <= now.hour < 19
    for key, cfg in COUNCILS.items():
        is_active = in_day_window and scheduled_today(cfg["schedule"], now) and stream_live(cfg["stream"])
        print(f"{key}: active={is_active}")
        if is_active:
            active.append(cfg)

    if active:
        payload = "\n".join(entry(cfg).rstrip() for cfg in active) + "\n\n"
        anchor = "## Rakuten-JP"
        if anchor in text:
            text = text.replace(anchor, payload + anchor, 1)
        else:
            text = text.rstrip() + "\n\n" + payload

    FREEWIFI.write_text(text.rstrip() + "\n", encoding="utf-8")
    print("Council live visible:", ", ".join(cfg["name"] for cfg in active) or "(none)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
