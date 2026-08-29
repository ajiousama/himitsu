from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

FREEWIFI = Path("freewifi")
GENERAL = Path("general_youtube.m3u")
JRA_STATUS = Path("today_jra_status.json")

A_START = "# === JRA_GCH_FREE_A_START ==="
A_END = "# === JRA_GCH_FREE_A_END ==="
B_START = "# === JRA_GCH_FREE_B_START ==="
B_END = "# === JRA_GCH_FREE_B_END ==="

A_ID = "jra.official"
B_ID = "jra.gch.free"

A_LOGO = "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/youtube/jra_youtube_free.jpg"
B_LOGO = "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/youtube/jra_gch_free.jpg"

# A = JRA official YouTube.
# B = current direct free 1ch HLS extracted from https://sp.gch.jp/jra
# through the Osaka resolver because GitHub Actions overseas IPs are rejected
# by the STREAKS playback API.
B_RAW = "https://himitsu-six.vercel.app/api/gch-free?raw=1"


def request_json(url: str, timeout: int = 20) -> dict | None:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0 Safari/537.36",
        "Accept": "application/json",
    }
    try:
        from curl_cffi import requests as crequests
        r = crequests.get(url, headers=headers, timeout=timeout, impersonate="chrome", allow_redirects=True)
        r.raise_for_status()
        return r.json()
    except Exception as first_error:
        try:
            from urllib.request import Request, urlopen
            req = Request(url, headers=headers)
            with urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", errors="replace"))
        except Exception as second_error:
            print("JSON request failed:", first_error, "/", second_error)
            return None


def jra_active_today() -> bool:
    try:
        data = json.loads(JRA_STATUS.read_text(encoding="utf-8-sig"))
        return int(data.get("active_count", 0)) > 0
    except Exception:
        return False


def existing_url(text: str, tvg_id: str) -> str | None:
    lines = text.splitlines()
    for i, line in enumerate(lines[:-1]):
        if line.startswith("#EXTINF:") and f'tvg-id="{tvg_id}"' in line:
            url = lines[i + 1].strip()
            if url.startswith(("http://", "https://")):
                return url
    return None


def find_youtube_url() -> str | None:
    try:
        from jra_freewifi_finalize import find_jra_live_by_title
        url = find_jra_live_by_title()
        if url:
            return url
    except Exception as e:
        print("A YouTube title lookup failed:", e)

    if GENERAL.exists():
        text = GENERAL.read_text(encoding="utf-8-sig", errors="replace")
        return existing_url(text, A_ID)
    return None


def jwt_expiry_from_url(url: str) -> int | None:
    try:
        token = parse_qs(urlparse(url).query).get("token", [None])[0]
        if not token:
            return None
        payload = token.split('.')[1]
        payload += '=' * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode()).decode())
        return int(data.get("exp")) if data.get("exp") is not None else None
    except Exception:
        return None


def valid_gch_manifest(url: str) -> bool:
    if not isinstance(url, str):
        return False
    if not re.match(r'^https://manifest\.streaks\.jp/.+\.m3u8(?:\?|$)', url):
        return False
    exp = jwt_expiry_from_url(url)
    if exp is not None and exp <= int(time.time()) + 300:
        print("B direct manifest token expires too soon:", exp)
        return False
    return True


def find_gch_url() -> str | None:
    data = request_json(B_RAW)
    if not isinstance(data, dict) or data.get("ok") is not True:
        print("B official page resolver unavailable:", data)
        return None
    url = data.get("hls")
    if not valid_gch_manifest(url):
        print("B resolver returned invalid manifest")
        return None
    exp = jwt_expiry_from_url(url)
    print(
        "B direct manifest extracted from https://sp.gch.jp/jra:",
        data.get("projectId"),
        data.get("playbackType"),
        "ssai=" + str(data.get("ssai")),
        "exp=" + str(exp),
    )
    return url


def strip_managed(text: str) -> str:
    for start, end in (
        (A_START, A_END),
        (B_START, B_END),
        ("# === JRA_OFFICIAL_YOUTUBE_START ===", "# === JRA_OFFICIAL_YOUTUBE_END ==="),
        ("# === JRA_GCH_FREE_START ===", "# === JRA_GCH_FREE_END ==="),
    ):
        text = re.sub(re.escape(start) + r".*?" + re.escape(end) + r"\n?", "", text, flags=re.S)

    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#EXTINF:") and i + 1 < len(lines):
            display = line.rsplit(",", 1)[-1] if "," in line else ""
            if (
                f'tvg-id="{A_ID}"' in line
                or f'tvg-id="{B_ID}"' in line
                or "GCH無料版A" in display
                or "GCH無料版B" in display
                or "JRA公式（GCH）無料版" in display
                or "グリーンチャンネル(無料版)" in display
                or "グリーンチャンネル（無料版）" in display
            ):
                i += 2
                continue
        out.append(line)
        i += 1
    return "\n".join(out).rstrip() + "\n"


def build_block(a_url: str | None, b_url: str | None) -> str:
    lines: list[str] = []
    if a_url:
        lines += [
            A_START,
            f'#EXTINF:-1 tvg-id="{A_ID}" tvg-name="GCH無料版A（YouTube）" tvg-logo="{A_LOGO}" group-title="競馬",GCH無料版A（YouTube）',
            a_url,
            A_END,
        ]
    if b_url:
        lines += [
            B_START,
            f'#EXTINF:-1 tvg-id="{B_ID}" tvg-name="GCH無料版B（グリーンチャンネルWeb）" tvg-logo="{B_LOGO}" group-title="競馬",GCH無料版B（グリーンチャンネルWeb）',
            b_url,
            B_END,
        ]
    return "\n".join(lines) + ("\n" if lines else "")


def main() -> int:
    if not FREEWIFI.exists():
        raise RuntimeError("freewifi not found")

    original = FREEWIFI.read_text(encoding="utf-8-sig", errors="replace")
    if not original.startswith("#EXTM3U"):
        raise RuntimeError("Refusing to update: freewifi lost #EXTM3U")

    cleaned = strip_managed(original)

    if not jra_active_today():
        FREEWIFI.write_text(cleaned, encoding="utf-8")
        print("JRA inactive today: removed A/B free channels")
        return 0

    a_url = find_youtube_url()
    b_url = find_gch_url()
    print("A YouTube:", "LIVE" if a_url else "not resolved")
    print("B GCH Web free 1ch:", "DIRECT M3U8" if b_url else "not resolved")

    if not a_url or not b_url:
        raise RuntimeError(f"GCH free A/B incomplete: A={bool(a_url)} B={bool(b_url)}")

    block = build_block(a_url, b_url)
    anchor = "## 競馬\n"
    cleaned = cleaned.replace(anchor, anchor + "\n" + block, 1) if anchor in cleaned else cleaned.rstrip() + "\n\n" + block

    if cleaned.count("#EXTINF:") < max(50, int(original.count("#EXTINF:") * 0.70)):
        raise RuntimeError("Refusing to update: playlist channel count collapsed")

    FREEWIFI.write_text(cleaned.rstrip() + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
