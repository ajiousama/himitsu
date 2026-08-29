from __future__ import annotations

import base64
import json
import re
import time
from html import unescape
from pathlib import Path
from urllib.parse import urljoin

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

GCH_HOME = "https://sp.gch.jp/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140.0 Safari/537.36",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Referer": GCH_HOME,
}

MANIFEST_RE = re.compile(
    r'https://manifest\.streaks\.jp/[^"\'< >\s]+?\.m3u8(?:\?[^"\'< >\s]+)?'.replace(' ', ''),
    re.I,
)
SCRIPT_RE = re.compile(r'<script[^>]+src=["\']([^"\']+)["\']', re.I)
URL_RE = re.compile(r'https://[^"\'< >\s\\]+'.replace(' ', ''), re.I)


def request_text(url: str, timeout: int = 20) -> str:
    try:
        from curl_cffi import requests as crequests
        r = crequests.get(url, headers=HEADERS, timeout=timeout, impersonate="chrome", allow_redirects=True)
        r.raise_for_status()
        return r.text
    except Exception:
        from urllib.request import Request, urlopen
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="replace")


def jra_active_today() -> bool:
    try:
        data = json.loads(JRA_STATUS.read_text(encoding="utf-8-sig"))
        return int(data.get("active_count", 0)) > 0
    except Exception:
        return False


def jwt_exp(url: str) -> int | None:
    m = re.search(r'(?:[?&]token=)([^&]+)', url)
    if not m:
        return None
    parts = m.group(1).split(".")
    if len(parts) < 2:
        return None
    try:
        payload = parts[1] + "=" * (-len(parts[1]) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload).decode("utf-8"))
        return int(data.get("exp")) if data.get("exp") is not None else None
    except Exception:
        return None


def usable_manifest(url: str) -> bool:
    exp = jwt_exp(url)
    if exp is not None and exp <= int(time.time()) + 300:
        return False
    return url.startswith("https://manifest.streaks.jp/") and ".m3u8" in url


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


def candidate_manifests(text: str) -> list[str]:
    out: list[str] = []
    normalized = unescape(text).replace("\\/", "/")
    for raw in MANIFEST_RE.findall(normalized):
        url = raw.rstrip("\\")
        if url not in out:
            out.append(url)
    return out


def find_gch_url(existing: str | None) -> str | None:
    if existing and usable_manifest(existing):
        print("B existing GCH URL is still valid")
        return existing

    try:
        home = request_text(GCH_HOME)
    except Exception as e:
        print("B GCH home fetch failed:", e)
        return None

    for url in candidate_manifests(home):
        if usable_manifest(url):
            print("B GCH manifest found in HTML")
            return url

    scripts: list[str] = []
    for src in SCRIPT_RE.findall(home):
        url = urljoin(GCH_HOME, unescape(src))
        if url not in scripts:
            scripts.append(url)

    print("B GCH script assets:", len(scripts))
    for asset in scripts[:30]:
        try:
            js = request_text(asset, timeout=15)
        except Exception as e:
            print("B script fetch failed:", asset, e)
            continue

        for url in candidate_manifests(js):
            if usable_manifest(url):
                print("B GCH manifest found in JS:", asset)
                return url

        possible: list[str] = []
        normalized = unescape(js).replace("\\/", "/")
        for u in URL_RE.findall(normalized):
            low = u.lower()
            if any(k in low for k in ("gch-jra", "streaks.jp")) and any(k in low for k in ("api", "live", "stream", "manifest")):
                possible.append(u.rstrip("\\"))
        for endpoint in possible[:10]:
            if endpoint.endswith(".m3u8") and usable_manifest(endpoint):
                return endpoint
            try:
                body = request_text(endpoint, timeout=10)
            except Exception:
                continue
            for url in candidate_manifests(body):
                if usable_manifest(url):
                    print("B GCH manifest found via endpoint:", endpoint)
                    return url

    print("B GCH signed manifest not found")
    return None


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

    previous_b = existing_url(original, B_ID)
    cleaned = strip_managed(original)

    if not jra_active_today():
        FREEWIFI.write_text(cleaned, encoding="utf-8")
        print("JRA inactive today: removed A/B free channels")
        return 0

    a_url = find_youtube_url()
    b_url = find_gch_url(previous_b)
    print("A YouTube:", "LIVE" if a_url else "not resolved")
    print("B GCH Web:", "LIVE" if b_url else "not resolved")

    block = build_block(a_url, b_url)
    if block:
        anchor = "## 競馬\n"
        cleaned = cleaned.replace(anchor, anchor + "\n" + block, 1) if anchor in cleaned else cleaned.rstrip() + "\n\n" + block

    if cleaned.count("#EXTINF:") < max(50, int(original.count("#EXTINF:") * 0.70)):
        raise RuntimeError("Refusing to update: playlist channel count collapsed")

    FREEWIFI.write_text(cleaned.rstrip() + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
