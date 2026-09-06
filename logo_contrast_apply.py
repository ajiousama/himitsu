#!/usr/bin/env python3
from __future__ import annotations

import concurrent.futures
import hashlib
import io
import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageOps

FREEWIFI = Path("freewifi")
DB_PATH = Path("logo_contrast_sources.json")
OUT_DIR = Path("logos/contrast")
RAW_BASE = "https://raw.githubusercontent.com/ajiousama/himitsu/main"
UA = {"User-Agent": "Mozilla/5.0 (FreeWiFi logo contrast normalizer)"}

# External logo providers that are known to include transparent/dark artwork or
# very small raster logos.  Existing ajiousama, Rakuten and YouTube/public-sports
# logos are intentionally left alone.
TARGET_HOSTS = {
    "radiko.jp",
    "www.radiko.jp",
    "tvguide.myjcom.jp",
    "api2.bangumi.org",
    "www.skyperfectv.co.jp",
    "skyperfectv.co.jp",
    "www.lyngsat.com",
    "lyngsat.com",
    "upload.wikimedia.org",
}

RADIO_SIDS = [
    "JOEU-FM", "RNB", "ABC", "CCL", "802", "FMO",
    "MBS", "OBC", "KBS", "ALPHA-STATION", "E-RADIO", "CRK",
]

LOGO_RE = re.compile(r'tvg-logo="([^"]+)"')
ID_RE = re.compile(r'tvg-id="([^"]+)"')


def source_radio_logo(sid: str) -> str:
    return f"https://radiko.jp/v2/static/station/logo/{sid}/lrtrim/688x160.png"


def safe_slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    return value.strip("._-") or "logo"


def local_relpath(tvgid: str, source_url: str) -> str:
    digest = hashlib.sha1(source_url.encode("utf-8")).hexdigest()[:8]
    return f"logos/contrast/{safe_slug(tvgid)}_{digest}.png"


def raw_url(relpath: str) -> str:
    return f"{RAW_BASE}/{urllib.parse.quote(relpath, safe='/._-')}"


def is_target(url: str) -> bool:
    try:
        host = (urllib.parse.urlsplit(url).hostname or "").lower()
    except Exception:
        return False
    return host in TARGET_HOSTS


def fetch_image(url: str, timeout: int = 15) -> Image.Image:
    req = urllib.request.Request(url.rstrip("?"), headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read(8 * 1024 * 1024)
    im = Image.open(io.BytesIO(data))
    try:
        im.seek(0)
    except Exception:
        pass
    return im.convert("RGBA")


def make_white_card(source_url: str, relpath: str) -> tuple[str, str | None]:
    out = Path(relpath)
    try:
        im = fetch_image(source_url)
        # A 512x512 white card is intentionally used so black-background IPTV
        # clients never swallow black/dark or transparent portions of logos.
        card = Image.new("RGBA", (512, 512), (255, 255, 255, 255))
        fitted = ImageOps.contain(im, (448, 448), method=Image.Resampling.LANCZOS)
        x = (512 - fitted.width) // 2
        y = (512 - fitted.height) // 2
        card.alpha_composite(fitted, (x, y))
        out.parent.mkdir(parents=True, exist_ok=True)
        card.convert("RGB").save(out, format="PNG", optimize=True)
        return relpath, None
    except Exception as e:
        return relpath, f"{type(e).__name__}: {e}"


def load_db() -> dict[str, dict[str, str]]:
    if not DB_PATH.exists():
        return {}
    try:
        raw = json.loads(DB_PATH.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            return {str(k): dict(v) for k, v in raw.items() if isinstance(v, dict)}
    except Exception:
        pass
    return {}


def main() -> int:
    if not FREEWIFI.exists():
        raise SystemExit("freewifi not found")

    text = FREEWIFI.read_text(encoding="utf-8-sig", errors="replace")

    # Repair the already-found malformed Channel Ginga entries before parsing.
    text = text.replace('tvg-logo="tvg-logo="https://', 'tvg-logo="https://')

    db = load_db()

    # Keep the compact FreeWiFi radio logos permanently refreshable even after
    # freewifi has been rewritten to local contrast-safe assets.
    for sid in RADIO_SIDS:
        src = source_radio_logo(sid)
        tvgid = f"radiko.{sid}"
        db.setdefault(src, {"tvg_id": tvgid, "path": local_relpath(tvgid, src)})

    # Discover target external logos still present in FreeWiFi.
    for line in text.splitlines():
        if not line.lstrip().startswith("#EXTINF:"):
            continue
        m_logo = LOGO_RE.search(line)
        if not m_logo:
            continue
        src = m_logo.group(1).strip()
        if not src.startswith(("http://", "https://")) or not is_target(src):
            continue
        m_id = ID_RE.search(line)
        tvgid = m_id.group(1).strip() if m_id else "logo"
        db.setdefault(src, {"tvg_id": tvgid, "path": local_relpath(tvgid, src)})

    # Refresh/generate all known contrast-safe assets concurrently.
    items = []
    for src, meta in db.items():
        path = meta.get("path") or local_relpath(meta.get("tvg_id", "logo"), src)
        meta["path"] = path
        items.append((src, path))

    errors: dict[str, str] = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futs = {ex.submit(make_white_card, src, path): (src, path) for src, path in items}
        for fut in concurrent.futures.as_completed(futs):
            src, path = futs[fut]
            _, err = fut.result()
            if err:
                errors[src] = err

    replaced = 0
    kept_external = 0
    for src, meta in db.items():
        path = meta["path"]
        if not Path(path).exists():
            kept_external += text.count(src)
            continue
        local = raw_url(path)
        count = text.count(src)
        if count:
            text = text.replace(src, local)
            replaced += count

    FREEWIFI.write_text(text, encoding="utf-8")
    DB_PATH.write_text(json.dumps(db, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # A malformed tvg-logo attribute is a hard failure because it can disappear
    # completely in IPTV clients.
    if 'tvg-logo="tvg-logo=' in text:
        raise SystemExit("malformed nested tvg-logo remains")

    radio_local = sum(text.count(raw_url(db[source_radio_logo(sid)]["path"])) for sid in RADIO_SIDS)
    print(f"contrast logos known={len(db)} generated={sum(Path(v['path']).exists() for v in db.values())}")
    print(f"FreeWiFi logo refs replaced={replaced} external-kept={kept_external} compact-radio-local={radio_local}/12")
    if errors:
        print(f"logo fetch warnings={len(errors)}")
        for src, err in list(errors.items())[:12]:
            print(f"WARN {src}: {err}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
