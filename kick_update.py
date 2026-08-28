from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

FREEWIFI = Path("freewifi")
CONFIG = Path("kick_channels.json")
START = "# === KICK_MANAGED_START ==="
END = "# === KICK_MANAGED_END ==="
YT_ANCHOR = "# === GENERAL_YOUTUBE_MANAGED_START ==="

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Referer": "https://kick.com/",
    "Origin": "https://kick.com",
}


def norm(value: Any) -> str:
    s = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return re.sub(r"[\s_\-・･()（）\[\]【】]+", "", s)


def request_json(url: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    if params:
        url = f"{url}?{urlencode(params)}"

    try:
        from curl_cffi import requests as crequests

        r = crequests.get(
            url,
            headers=HEADERS,
            timeout=30,
            impersonate="chrome",
            allow_redirects=True,
        )
        r.raise_for_status()
        data = r.json()
        if isinstance(data, dict):
            return data
        raise RuntimeError(f"Unexpected JSON type: {type(data).__name__}")
    except ImportError:
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=30) as r:
            data = json.loads(r.read().decode("utf-8"))
        if isinstance(data, dict):
            return data
        raise RuntimeError(f"Unexpected JSON type: {type(data).__name__}")


def channel_details(slug: str) -> dict[str, Any]:
    return request_json(f"https://kick.com/api/v2/channels/{slug}")


def is_live(details: dict[str, Any]) -> bool:
    live = details.get("livestream")
    if not isinstance(live, dict):
        return False
    return live.get("is_live") is not False


def playback_url(details: dict[str, Any]) -> str | None:
    value = details.get("playback_url")
    if not isinstance(value, str) or not value.startswith("https://"):
        return None
    if ".m3u8" not in value:
        return None
    return value


def search_candidates(query: str, match_terms: list[str]) -> list[str]:
    data = request_json("https://kick.com/api/search", {"searched_word": query})
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
        if item.get("isLive") is True:
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
    sticky = bool(item.get("sticky_while_live"))

    if isinstance(fixed_slug, str) and fixed_slug.strip():
        slug = fixed_slug.strip()
        try:
            details = channel_details(slug)
            if not is_live(details):
                return None, slug, "offline"
            if sticky and existing_url:
                return existing_url, slug, "live (fixed URL kept)"
            url = playback_url(details)
            if not url:
                return None, slug, "live but no usable playback_url"
            return url, slug, "live"
        except Exception as e:
            if sticky and existing_url:
                return existing_url, slug, f"lookup failed; fixed URL kept: {e}"
            return None, slug, f"lookup failed: {e}"

    query = str(item.get("search") or name)
    try:
        candidates = search_candidates(query, terms)
    except Exception as e:
        return None, None, f"search failed: {e}"

    if not candidates:
        return None, None, "no search candidates"

    for slug in candidates:
        try:
            details = channel_details(slug)
        except Exception as e:
            print(f"KICK candidate lookup failed {name} / {slug}: {e}")
            continue
        if not is_live(details):
            continue
        if not details_match(details, terms):
            continue
        if sticky and existing_url:
            return existing_url, slug, "live (fixed URL kept)"
        url = playback_url(details)
        if url:
            return url, slug, "live (search resolved)"

    return None, None, "no matching live channel"


def strip_old_kick(text: str, names: set[str]) -> str:
    text = re.sub(
        re.escape(START) + r".*?" + re.escape(END) + r"\n?",
        "",
        text,
        flags=re.S,
    )

    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#EXTINF:") and i + 1 < len(lines):
            display = line.rsplit(",", 1)[-1].strip() if "," in line else ""
            if display in names:
                print("Removing legacy KICK entry:", display)
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
    print(f"KICK managed block updated: {live_count}/{len(config)} live")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"KICK updater fatal error: {exc}", file=sys.stderr)
        raise
