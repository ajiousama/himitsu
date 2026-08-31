from __future__ import annotations

import base64
import json
import re
import sys
import time
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse
from urllib.request import Request, urlopen

FREEWIFI = Path("freewifi")
CONFIG = Path("kick_channels.json")
START = "# === KICK_MANAGED_START ==="
END = "# === KICK_MANAGED_END ==="
YT_ANCHOR = "# === GENERAL_YOUTUBE_MANAGED_START ==="
MIN_TOKEN_LIFETIME = 600
REFRESH_RETRIES = 3

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Referer": "https://kick.com/",
    "Origin": "https://kick.com",
    "Cache-Control": "no-cache",
}


def norm(value: Any) -> str:
    s = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[\s_\-・･()（）\[\]【】]+", "", s)


def request_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    if params:
        url = f"{url}?{urlencode(params)}"
    try:
        from curl_cffi import requests as crequests
        r = crequests.get(url, headers=HEADERS, timeout=25, impersonate="chrome", allow_redirects=True)
        r.raise_for_status()
        data = r.json()
    except ImportError:
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=25) as r:
            data = json.loads(r.read().decode("utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"Unexpected JSON type: {type(data).__name__}")
    return data


def channel_details(slug: str) -> dict[str, Any]:
    errors = []
    # cache-busting query prevents a stale playback_url being reused by an edge cache
    bust = int(time.time() * 1000)
    for base in (
        f"https://kick.com/api/v2/channels/{slug}",
        f"https://kick.com/api/v1/channels/{slug}",
        f"https://api.kick.com/private/v1/channels/{slug}",
    ):
        try:
            return request_json(base, {"_": bust})
        except Exception as exc:
            errors.append(f"{base}: {type(exc).__name__}")
    raise RuntimeError("; ".join(errors))


def playback_url(obj: Any) -> str | None:
    if isinstance(obj, dict):
        for key in ("playback_url", "playbackUrl", "source", "src"):
            value = obj.get(key)
            if isinstance(value, str):
                value = value.replace("\\/", "/")
                if value.startswith("https://") and ".m3u8" in value:
                    return value
        for value in obj.values():
            hit = playback_url(value)
            if hit:
                return hit
    elif isinstance(obj, list):
        for value in obj:
            hit = playback_url(value)
            if hit:
                return hit
    return None


def jwt_exp(url: str) -> int | None:
    try:
        token = (parse_qs(urlparse(url).query).get("token") or [None])[0]
        if not token or token.count(".") < 2:
            return None
        payload = token.split(".")[1]
        payload += "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(payload.encode()).decode("utf-8"))
        exp = data.get("exp")
        return int(exp) if exp is not None else None
    except Exception:
        return None


def token_lifetime(url: str) -> int | None:
    exp = jwt_exp(url)
    return exp - int(time.time()) if exp is not None else None


def fresh_url_for_slug(slug: str) -> tuple[dict[str, Any], str | None, str]:
    last_details: dict[str, Any] = {}
    last_url: str | None = None
    for attempt in range(1, REFRESH_RETRIES + 1):
        details = channel_details(slug)
        last_details = details
        url = playback_url(details)
        last_url = url
        if not is_live(details):
            return details, None, "offline"
        if not url:
            if attempt < REFRESH_RETRIES:
                time.sleep(2)
            continue
        life = token_lifetime(url)
        if life is None:
            return details, url, "live refreshed (token exp unavailable)"
        print(f"KICK {slug}: JWT remaining {life}s (attempt {attempt}/{REFRESH_RETRIES})")
        if life >= MIN_TOKEN_LIFETIME:
            return details, url, f"live refreshed; JWT remaining {life}s"
        if attempt < REFRESH_RETRIES:
            time.sleep(2)
    life = token_lifetime(last_url) if last_url else None
    return last_details, None, f"live but fresh JWT unavailable (remaining={life}s)"


def is_live(details: dict[str, Any]) -> bool:
    if details.get("is_live") is True or details.get("isLive") is True:
        return True
    live = details.get("livestream")
    if isinstance(live, dict):
        if live.get("is_live") is False or live.get("isLive") is False:
            return False
        return True
    return playback_url(details) is not None


def search_candidates(query: str, match_terms: list[str]) -> list[str]:
    data = request_json("https://kick.com/api/search", {"searched_word": query, "_": int(time.time() * 1000)})
    channels = data.get("channels") or []
    if not isinstance(channels, list):
        return []
    qn = norm(query)
    term_norms = [norm(x) for x in match_terms if norm(x)]
    ranked: list[tuple[int, str]] = []
    seen: set[str] = set()
    for item in channels:
        if not isinstance(item, dict):
            continue
        slug = item.get("slug")
        user = item.get("user") if isinstance(item.get("user"), dict) else {}
        username = user.get("username") if isinstance(user, dict) else ""
        if not isinstance(slug, str) or not slug or slug in seen:
            continue
        seen.add(slug)
        hay = norm(json.dumps(item, ensure_ascii=False, sort_keys=True))
        score = 0
        if qn and qn in hay:
            score += 100
        score += 25 * sum(1 for t in term_norms if t and t in hay)
        if item.get("isLive") is True or item.get("is_live") is True:
            score += 10
        if qn and (norm(slug) == qn or norm(username) == qn):
            score += 200
        ranked.append((score, slug))
    ranked.sort(key=lambda x: (-x[0], x[1]))
    return [slug for _, slug in ranked[:10]]


def details_match(details: dict[str, Any], terms: list[str]) -> bool:
    hay = norm(json.dumps(details, ensure_ascii=False, sort_keys=True))
    wanted = [norm(x) for x in terms if norm(x)]
    return any(t in hay for t in wanted) if wanted else True


def existing_kick_urls(text: str, names: set[str]) -> dict[str, str]:
    found: dict[str, str] = {}
    lines = text.splitlines()
    for i, line in enumerate(lines[:-1]):
        if not line.startswith("#EXTINF:") or "," not in line:
            continue
        display = line.rsplit(",", 1)[-1].strip()
        if display not in names:
            continue
        url = lines[i + 1].strip()
        if url.startswith("https://") and ".m3u8" in url:
            found[display] = url
    return found


def resolve_channel(item: dict[str, Any], existing_url: str | None = None) -> tuple[str | None, str | None, str]:
    name = str(item["name"])
    fixed_slug = item.get("slug")
    terms = [str(x) for x in item.get("match_terms", [])]

    if isinstance(fixed_slug, str) and fixed_slug.strip():
        slug = fixed_slug.strip()
        try:
            details, url, status = fresh_url_for_slug(slug)
            if url:
                return url, slug, status
            if not is_live(details):
                return None, slug, "offline"
            # Never overwrite a LIVE entry with a known stale token.
            if existing_url and (token_lifetime(existing_url) or -1) > 0:
                return existing_url, slug, status + "; still-valid previous URL kept"
            return None, slug, status
        except Exception as e:
            if existing_url and (token_lifetime(existing_url) or -1) > 0:
                return existing_url, slug, f"lookup failed; still-valid previous URL kept: {e}"
            return None, slug, f"lookup failed and no valid previous URL: {e}"

    query = str(item.get("search") or name)
    try:
        candidates = search_candidates(query, terms)
    except Exception as e:
        if existing_url and (token_lifetime(existing_url) or -1) > 0:
            return existing_url, None, f"search failed; still-valid previous URL kept: {e}"
        return None, None, f"search failed: {e}"

    for slug in candidates:
        try:
            details, url, status = fresh_url_for_slug(slug)
        except Exception as e:
            print(f"KICK candidate lookup failed {name} / {slug}: {e}")
            continue
        if not is_live(details) or not details_match(details, terms):
            continue
        if url:
            return url, slug, status

    if existing_url and (token_lifetime(existing_url) or -1) > 0:
        return existing_url, None, "no fresh matching live URL; still-valid previous URL kept"
    return None, None, "no fresh matching live URL"


def strip_old_kick(text: str, names: set[str]) -> str:
    text = re.sub(re.escape(START) + r".*?" + re.escape(END) + r"\n?", "", text, flags=re.S)
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#EXTINF:") and i + 1 < len(lines):
            display = line.rsplit(",", 1)[-1].strip() if "," in line else ""
            if display in names:
                i += 2
                continue
        out.append(line)
        i += 1
    return "\n".join(out).rstrip() + "\n"


def render_block(config: list[dict[str, Any]], existing: dict[str, str]) -> tuple[str, int]:
    lines = [START, "## KICK"]
    live_count = 0
    for item in config:
        name = str(item["name"])
        tvg_id = str(item.get("tvg_id") or "").strip()
        logo = str(item.get("logo") or "")
        url, slug, status = resolve_channel(item, existing.get(name))
        print(f"KICK {name}: {status}" + (f" [{slug}]" if slug else ""))
        if not url:
            continue
        meta = '#EXTINF:-1 group-title="その他"'
        if tvg_id:
            meta += f' tvg-id="{tvg_id}"'
        if logo:
            meta += f' tvg-logo="{logo}"'
        lines.extend([f"{meta},{name}", url])
        live_count += 1
    lines.append(END)
    return "\n".join(lines) + "\n", live_count


def insert_block(text: str, block: str) -> str:
    if YT_ANCHOR in text:
        return text.replace(YT_ANCHOR, block + "\n" + YT_ANCHOR, 1)
    return text.rstrip() + "\n\n" + block


def main() -> int:
    if not FREEWIFI.exists() or not CONFIG.exists():
        raise RuntimeError("freewifi or kick_channels.json is missing")
    original = FREEWIFI.read_text(encoding="utf-8-sig", errors="replace")
    if not original.startswith("#EXTM3U"):
        raise RuntimeError("Refusing to update: freewifi lost #EXTM3U header")
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    if not isinstance(config, list) or not config:
        raise RuntimeError("kick_channels.json must contain a non-empty list")

    names = {str(x["name"]) for x in config}
    existing = existing_kick_urls(original, names)
    cleaned = strip_old_kick(original, names)
    block, live_count = render_block(config, existing)
    updated = insert_block(cleaned, block)

    if updated.count("#EXTINF:") < max(50, int(original.count("#EXTINF:") * 0.70)):
        raise RuntimeError("Refusing to update: playlist channel count collapsed")
    FREEWIFI.write_text(updated, encoding="utf-8")
    print(f"KICK managed block updated: {live_count}/{len(config)} entries")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"KICK updater fatal error: {exc}", file=sys.stderr)
        raise
