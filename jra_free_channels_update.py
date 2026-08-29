from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

FREEWIFI = Path("freewifi")
JRA_STATUS = Path("today_jra_status.json")

A_START = "# === JRA_GCH_FREE_A_START ==="
A_END = "# === JRA_GCH_FREE_A_END ==="
B_START = "# === JRA_GCH_FREE_B_START ==="
B_END = "# === JRA_GCH_FREE_B_END ==="

A_ID = "jra.official"
B_ID = "jra.gch.free"

A_LOGO = "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/youtube/jra_youtube_free.jpg"
B_LOGO = "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/youtube/jra_gch_free.jpg"

# Canonical sources confirmed manually on 2026-08-29.
# IMPORTANT: Do not resolve A to googlevideo here. Keep the canonical YouTube live URL
# so the playlist cannot silently drift to a different live video.
A_FIXED = "https://www.youtube.com/live/9ZcqgwCQ4qk?si=hmPiB8fp-MMuEHQi"

# B is the exact current direct STREAKS manifest confirmed manually.
# If its JWT expires, fail closed instead of silently replacing it with a different stream.
B_FIXED = "https://manifest.streaks.jp/v4/gch-jra/97d99803d82b49bd9fc73cb568b219df/a214b09df7e04c22a15b4feba869b01d/hls/v3/manifest.m3u8?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJwcCI6IjNhZWVhMzU2ZmQ0MzQyMzE4ZjRhNDg2OWUwMzFiMDZiIiwiZGMiOiJjYTlmZDAwYTRiMmU0YTg1OGEyNmM1MTY5ZDIwY2U0ZiIsImVkZ2UiOiIzYjY5ZGJiYjYwMmI0M2NlODFmYjdkNGI3NjE0NjEzMCIsImNvZGVjcyI6ImF1dG8iLCJleHAiOjE3ODgxNDE2MDAsImlvcyI6MTgsInBwdyI6IjRwaiJ9._hI54Kx6gIyCMePTHppoHPhKbWkzpnSRiUPwLnkprtk"


def jra_active_today() -> bool:
    try:
        data = json.loads(JRA_STATUS.read_text(encoding="utf-8-sig"))
        return int(data.get("active_count", 0)) > 0
    except Exception:
        return False


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
        print("B pinned direct manifest token expires too soon:", exp)
        return False
    return True


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


def build_block(a_url: str, b_url: str) -> str:
    lines = [
        A_START,
        f'#EXTINF:-1 tvg-id="{A_ID}" tvg-name="GCH無料版A（YouTube）" tvg-logo="{A_LOGO}" group-title="競馬",GCH無料版A（YouTube）',
        a_url,
        A_END,
        B_START,
        f'#EXTINF:-1 tvg-id="{B_ID}" tvg-name="GCH無料版B（グリーンチャンネルWeb）" tvg-logo="{B_LOGO}" group-title="競馬",GCH無料版B（グリーンチャンネルWeb）',
        b_url,
        B_END,
    ]
    return "\n".join(lines) + "\n"


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

    a_url = A_FIXED
    b_url = B_FIXED

    if not a_url.startswith("https://www.youtube.com/live/9ZcqgwCQ4qk"):
        raise RuntimeError("A pinned YouTube source changed unexpectedly")
    if not valid_gch_manifest(b_url):
        raise RuntimeError("B pinned GCH manifest is invalid or expired; refusing wrong fallback")

    print("A YouTube: PINNED canonical live URL")
    print("B GCH Web free 1ch: PINNED direct STREAKS manifest; exp=", jwt_expiry_from_url(b_url))

    block = build_block(a_url, b_url)
    anchor = "## 競馬\n"
    cleaned = cleaned.replace(anchor, anchor + "\n" + block, 1) if anchor in cleaned else cleaned.rstrip() + "\n\n" + block

    if cleaned.count("#EXTINF:") < max(50, int(original.count("#EXTINF:") * 0.70)):
        raise RuntimeError("Refusing to update: playlist channel count collapsed")

    FREEWIFI.write_text(cleaned.rstrip() + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
