#!/usr/bin/env python3
from __future__ import annotations

import os
import re
import urllib.parse
from pathlib import Path

FREEWIFI = Path("freewifi")
BASE = os.environ.get(
    "RADIO_TV_BASE",
    "https://raw.githubusercontent.com/ajiousama/himitsu/main/radio-tv-static",
).rstrip("/")

TARGETS = {
    "nhk_r1_osaka": "nhk_r1_osaka",
    "nhk_fm_osaka": "nhk_fm_osaka",
    "nhk_r1_matsuyama": "nhk_r1_matsuyama",
    "nhk_fm_matsuyama": "nhk_fm_matsuyama",
    "radiko.JOEU-FM": "JOEU-FM",
    "radiko.RNB": "RNB",
    "radiko.ABC": "ABC",
    "radiko.CCL": "CCL",
    "radiko.802": "802",
    "radiko.FMO": "FMO",
    "radiko.MBS": "MBS",
    "radiko.OBC": "OBC",
    "radiko.KBS": "KBS",
    "radiko.ALPHA-STATION": "ALPHA-STATION",
    "radiko.E-RADIO": "E-RADIO",
    "radiko.CRK": "CRK",
}


def main():
    text = FREEWIFI.read_text(encoding="utf-8-sig")
    lines = text.splitlines()
    changed = set()

    for i, line in enumerate(lines):
        if not line.lstrip().startswith("#EXTINF:"):
            continue
        m = re.search(r'tvg-id="([^"]+)"', line)
        if not m:
            continue
        tvgid = m.group(1)
        station = TARGETS.get(tvgid)
        if not station:
            continue
        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j >= len(lines) or lines[j].lstrip().startswith("#"):
            raise SystemExit(f"stream URL missing after {tvgid}")
        folder = urllib.parse.quote(station, safe="")
        new_url = f"{BASE}/{folder}/master.m3u8"
        if lines[j].strip() != new_url:
            lines[j] = new_url
        changed.add(tvgid)

    missing = sorted(set(TARGETS) - changed)
    if missing:
        raise SystemExit("radio entries missing from freewifi: " + ", ".join(missing))
    FREEWIFI.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print(f"FreeWiFi radio TV URLs updated: {len(changed)} stations")


if __name__ == "__main__":
    main()
