#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import re
import time
import urllib.request

import radio_tv as base

# Keep the working ABC/Osaka/Ehime definitions, but allow every station ID
# returned by the existing Radiko Premium nationwide station list.
# NHK-FM Matsuyama intentionally remains the existing direct feed.
REGION_LABELS = {
    "北海道": "HOKKAIDO",
    "東北": "TOHOKU",
    "関東": "KANTO",
    "甲信越": "KOSHINETSU",
    "東海": "TOKAI",
    "近畿": "KINKI",
    "中国": "CHUGOKU",
    "四国": "SHIKOKU",
    "九州沖縄": "KYUSHU / OKINAWA",
}
SID_RE = re.compile(r"^[A-Za-z0-9_-]{2,32}$")


def _accent(sid: str) -> tuple[int, int, int]:
    d = hashlib.sha256(sid.encode("utf-8")).digest()
    return (70 + d[0] % 150, 55 + d[1] % 135, 65 + d[2] % 145)


class NationwideStations(dict):
    def __init__(self, initial):
        super().__init__(initial)
        self._nationwide = {}
        self._nationwide_at = 0.0

    def _refresh(self, force: bool = False):
        now = time.time()
        if not force and self._nationwide and now - self._nationwide_at < 6 * 3600:
            return
        url = f"{base.RADIKO_BASE}/api/radiko?list=1"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=20) as r:
            payload = json.loads(r.read().decode("utf-8", "replace"))
        stations = payload.get("stations") or {}
        if not isinstance(stations, dict) or len(stations) < 80:
            raise RuntimeError(
                f"radiko station discovery too small: {len(stations) if isinstance(stations, dict) else 0}"
            )
        self._nationwide = stations
        self._nationwide_at = now

    def _dynamic(self, sid: str):
        if not isinstance(sid, str) or not SID_RE.fullmatch(sid):
            raise KeyError(sid)
        self._refresh()
        meta = self._nationwide.get(sid)
        if not meta:
            raise KeyError(sid)
        region = REGION_LABELS.get(str(meta.get("region") or ""), "JAPAN")
        # Use the exact station ID in text so cards remain readable even on a
        # runtime that lacks Japanese fonts; the central Radiko logo supplies
        # the station branding/name.
        return (sid, f"RADIKO / {region}", _accent(sid), sid, None)

    def __contains__(self, key):
        if dict.__contains__(self, key):
            return True
        try:
            self._dynamic(key)
            return True
        except Exception:
            return False

    def __getitem__(self, key):
        try:
            return dict.__getitem__(self, key)
        except KeyError:
            return self._dynamic(key)


_initial = dict(base.STATIONS)
# NHK R1 Matsuyama exists on Radiko as JOZK, so it can use the same
# image+audio mux route as the other nationwide stations.
_initial["nhk_r1_matsuyama"] = (
    "NHK RADIO 1 MATSUYAMA",
    "RADIKO / SHIKOKU",
    (210, 34, 34),
    "JOZK",
    None,
)
# Keep this direct feed exactly as requested because Radiko has no local
# NHK-FM Matsuyama station ID.
_initial["nhk_fm_matsuyama"] = (
    "NHK FM MATSUYAMA",
    "FM MATSUYAMA",
    (54, 138, 57),
    None,
    "https://simul2.drdi.st.nhk/live/17/joined/master.m3u8",
)

base.STATIONS = NationwideStations(_initial)

# Re-export the working request handler. All of radio_tv.py's existing art,
# ffmpeg, debug, and streaming logic now sees the nationwide mapping above.
handle_request = base.handle_request
