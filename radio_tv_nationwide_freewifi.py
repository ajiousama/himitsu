#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

FREEWIFI = Path("freewifi")
RADIO_AUDIO_BASE = "https://himitsu-six.vercel.app/api/radiko"
RADIO_RENDER_BASE = "https://ajiousama-radiko.onrender.com/radio-tv"


def radio_url(sid: str) -> str:
    return f"{RADIO_AUDIO_BASE}?station={quote(sid, safe='')}&stage=media"


def radiko_entry(tvgid: str, sid: str, name: str, logo: str | None = None) -> str:
    if logo is None:
        logo = f"https://radiko.jp/v2/static/station/logo/{sid}/lrtrim/688x160.png"
    return (
        f'#EXTINF:-1 tvg-id="{tvgid}" tvg-logo="{logo}" group-title="ラジオ",{name}\n'
        f'{radio_url(sid)}\n'
    )


def compact_block() -> str:
    parts: list[str] = ["## ラジオ\n\n"]

    stations = [
        ("radiko.JOEU-FM", "JOEU-FM", "FM愛媛（ラジオ）"),
        ("radiko.RNB", "RNB", "RNB南海放送（ラジオ）"),
        ("radiko.ABC", "ABC", "ABCラジオ（ラジオ）"),
        ("radiko.CCL", "CCL", "FM COCOLO（ラジオ）"),
        ("radiko.802", "802", "FM802（ラジオ）"),
        ("radiko.FMO", "FMO", "FM大阪（ラジオ）"),
        ("radiko.MBS", "MBS", "MBSラジオ（ラジオ）"),
        ("radiko.OBC", "OBC", "OBCラジオ大阪（ラジオ）"),
        ("radiko.KBS", "KBS", "KBS京都ラジオ（ラジオ）"),
        ("radiko.ALPHA-STATION", "ALPHA-STATION", "α-STATION FM KYOTO（ラジオ）"),
        ("radiko.E-RADIO", "E-RADIO", "e-radio FM滋賀（ラジオ）"),
        ("radiko.CRK", "CRK", "ラジオ関西（ラジオ）"),
    ]
    parts.extend(radiko_entry(tvgid, sid, name) for tvgid, sid, name in stations)

    return "".join(parts).rstrip() + "\n\n"


def main() -> int:
    text = FREEWIFI.read_text(encoding="utf-8-sig", errors="replace")
    start = text.find("## ラジオ")
    end = text.find("## 愛媛CATV", start + 1)
    if start < 0 or end < 0 or end <= start:
        raise RuntimeError("could not locate radio section boundaries")

    updated = text[:start] + compact_block() + text[end:]

    if "## Rakuten-JP" not in updated:
        raise RuntimeError("Rakuten-JP section disappeared; refusing to write")

    radio_section = updated[start:updated.find("## 愛媛CATV", start)]
    audio_count = radio_section.count(RADIO_AUDIO_BASE + "?station=")
    if audio_count != 12:
        raise RuntimeError(f"compact FreeWiFi direct-radio count unexpected: {audio_count}")
    if RADIO_RENDER_BASE + "/" in radio_section:
        raise RuntimeError("slow Render radio-TV route leaked into FreeWiFi radio section")
    if "NHKラジオ" in radio_section or "NHK-FM" in radio_section or "nhk_r1_" in radio_section or "nhk_fm_" in radio_section:
        raise RuntimeError("NHK radio leaked into FreeWiFi radio section")
    extinf_lines = [line for line in radio_section.splitlines() if line.startswith("#EXTINF:")]
    if len(extinf_lines) != 12 or any('group-title="ラジオ"' not in line for line in extinf_lines):
        raise RuntimeError("FreeWiFi radio groups are not uniformly ラジオ")
    if "### 北海道" in radio_section or "station=TBS" in radio_section:
        raise RuntimeError("nationwide catalog leaked into FreeWiFi radio section")
    if "himitsu-six.vercel.app/api/radio-tv" in radio_section:
        raise RuntimeError("Vercel radio-TV URL leaked into compact FreeWiFi radio section")
    if "raw.githubusercontent.com/ajiousama/himitsu/radio-ts-assets/" in radio_section:
        raise RuntimeError("TS visual master leaked into compact FreeWiFi radio section")

    FREEWIFI.write_text(updated, encoding="utf-8")
    print(f"FreeWiFi compact radio restored: {audio_count} audio-first stations")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
