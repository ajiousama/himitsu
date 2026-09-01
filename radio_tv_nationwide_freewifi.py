#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
from urllib.parse import quote

FREEWIFI = Path("freewifi")
VERCEL_RADIO_TV = "https://himitsu-six.vercel.app/api/radio-tv"
NHK_LOGO = "https://upload.wikimedia.org/wikipedia/commons/b/bb/NHK_logo_2020.svg"
NHK_FM_OSAKA = "https://simul2.drdi.st.nhk/live/13/joined/master.m3u8"
NHK_FM_MATSUYAMA = "https://simul2.drdi.st.nhk/live/17/joined/master.m3u8"

# The Vercel radio-TV service uses stable aliases for NHK R1. Commercial
# stations use their Radiko station IDs directly.
RADIO_TV_ALIAS = {
    "JOBK": "nhk_r1_osaka",
    "JOZK": "nhk_r1_matsuyama",
}


def radio_tv_url(sid: str) -> str:
    station = RADIO_TV_ALIAS.get(sid, sid)
    return f"{VERCEL_RADIO_TV}?station={quote(station, safe='')}"


def radiko_entry(tvgid: str, sid: str, name: str, group: str, logo: str | None = None) -> str:
    if logo is None:
        logo = f"https://radiko.jp/v2/static/station/logo/{sid}/lrtrim/688x160.png"
    return (
        f'#EXTINF:-1 tvg-id="{tvgid}" tvg-logo="{logo}" group-title="{group}",{name}\n'
        f'{radio_tv_url(sid)}\n'
    )


def compact_block() -> str:
    parts: list[str] = ["## ラジオ\n\n"]

    parts.append(radiko_entry("radiko.JOBK", "JOBK", "NHKラジオ第1（大阪）", "ラジオ"))
    parts.append(
        f'#EXTINF:-1 tvg-id="nhk_fm_osaka" tvg-logo="{NHK_LOGO}" group-title="ラジオ",NHK-FM（大阪）\n'
        f'{NHK_FM_OSAKA}\n'
    )
    parts.append(radiko_entry("radiko.JOZK", "JOZK", "NHKラジオ第1（松山）", "ラジオ"))
    parts.append(
        f'#EXTINF:-1 tvg-id="nhk_fm_matsuyama" tvg-logo="{NHK_LOGO}" group-title="ラジオ",NHK-FM（松山）\n'
        f'{NHK_FM_MATSUYAMA}\n'
    )

    parts.append("\n## 愛媛（ラジオ）\n\n")
    parts.append(radiko_entry("radiko.JOEU-FM", "JOEU-FM", "FM愛媛（ラジオ）", "愛媛（ラジオ）"))
    parts.append(radiko_entry("radiko.RNB", "RNB", "RNB南海放送（ラジオ）", "愛媛（ラジオ）"))

    parts.append("\n## 在阪（ラジオ）\n\n")
    parts.append(radiko_entry("radiko.ABC", "ABC", "ABCラジオ（ラジオ）", "在阪（ラジオ）"))
    parts.append(radiko_entry("radiko.CCL", "CCL", "FM COCOLO（ラジオ）", "在阪（ラジオ）"))
    parts.append(radiko_entry("radiko.802", "802", "FM802（ラジオ）", "在阪（ラジオ）"))
    parts.append(radiko_entry("radiko.FMO", "FMO", "FM大阪（ラジオ）", "在阪（ラジオ）"))
    parts.append(radiko_entry("radiko.MBS", "MBS", "MBSラジオ（ラジオ）", "在阪（ラジオ）"))
    parts.append(radiko_entry("radiko.OBC", "OBC", "OBCラジオ大阪（ラジオ）", "在阪（ラジオ）"))

    parts.append("\n## 京都（ラジオ）\n\n")
    parts.append(radiko_entry("radiko.KBS", "KBS", "KBS京都ラジオ（ラジオ）", "京都（ラジオ）"))
    parts.append(radiko_entry("radiko.ALPHA-STATION", "ALPHA-STATION", "α-STATION FM KYOTO（ラジオ）", "京都（ラジオ）"))

    parts.append("\n## 滋賀（ラジオ）\n\n")
    parts.append(radiko_entry("radiko.E-RADIO", "E-RADIO", "e-radio FM滋賀（ラジオ）", "滋賀（ラジオ）"))

    parts.append("\n## 兵庫（ラジオ）\n\n")
    parts.append(radiko_entry("radiko.CRK", "CRK", "ラジオ関西（ラジオ）", "兵庫（ラジオ）"))

    return "".join(parts).rstrip() + "\n\n"


def main() -> int:
    text = FREEWIFI.read_text(encoding="utf-8-sig", errors="replace")
    start = text.find("## ラジオ")
    end = text.find("## 愛媛CATV", start + 1)
    if start < 0 or end < 0 or end <= start:
        raise RuntimeError("could not locate radio section boundaries")

    updated = text[:start] + compact_block() + text[end:]

    # Never allow this repair to damage unrelated sections.
    if "## Rakuten-JP" not in updated:
        raise RuntimeError("Rakuten-JP section disappeared; refusing to write")
    if NHK_FM_MATSUYAMA not in updated:
        raise RuntimeError("NHK-FM Matsuyama direct feed disappeared; refusing to write")

    radio_section = updated[start:updated.find("## 愛媛CATV", start)]
    vercel_count = radio_section.count(VERCEL_RADIO_TV + "?station=")
    if not 12 <= vercel_count <= 20:
        raise RuntimeError(f"compact FreeWiFi radio count unexpected: {vercel_count}")
    if "### 北海道" in radio_section or "station=TBS" in radio_section:
        raise RuntimeError("nationwide catalog leaked into FreeWiFi radio section")
    if "ajiousama-radiko.onrender.com/radio-tv/" in radio_section:
        raise RuntimeError("Render radio-TV URL leaked into compact FreeWiFi radio section")

    FREEWIFI.write_text(updated, encoding="utf-8")
    print(f"FreeWiFi compact radio restored: {vercel_count} Vercel image+audio stations + 2 local NHK-FM feeds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
