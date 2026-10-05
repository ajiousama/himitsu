from pathlib import Path
import json
import os
import re
import urllib.parse
import urllib.request

FREEWIFI = Path("tv/playlist.m3u")
PUBLISHED = Path("freewifi")
RAKUTEN_PLAYLIST = Path("rakuten/playlist.m3u")
API_URL = "http://app.harukashop.site:3008/api/news/get-link"
AU = os.environ.get("HARUKA_AU", "05zs80LO1csztPgNDkFeJcwkiSqNw9J6")
HEADERS = {
    "user-agent": "Dart/3.12 (dart:io)",
    "au": AU,
    "content-type": "application/json; charset=UTF-8",
}
PAYLOAD = {"os": 1, "appId": 7, "deviceId": 602539, "newsId": 12}
STREAM_PATH_RE = re.compile(r"/stream/\d+\.m3u8")
HARUKA_NAME_RE = re.compile(r"\(haruka(?:\(9394\))?\)\s*$", re.I)


def is_haruka_entry(line: str) -> bool:
    """Match terrestrial and BS/CS display-name variants, irrespective of group."""
    return line.startswith("#EXTINF:") and bool(HARUKA_NAME_RE.search(line))


def is_haruka_stream_url(url: str) -> bool:
    """Treat every 9394 /stream/<n>.m3u8 URL as a HARUKA stream."""
    try:
        parsed = urllib.parse.urlparse(url.strip())
        port = parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme in {"http", "https"}
        and port == 9394
        and bool(STREAM_PATH_RE.fullmatch(parsed.path))
    )


def fetch_current_base() -> str:
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(PAYLOAD).encode("utf-8"),
        headers=HEADERS,
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as response:
        body = json.loads(response.read().decode("utf-8"))

    if body.get("status") != 200:
        raise RuntimeError(f"HARUKA API returned status={body.get('status')!r}")

    link = body.get("data", {}).get("link")
    if not isinstance(link, str) or not link:
        raise RuntimeError("HARUKA API response has no data.link")

    parsed = urllib.parse.urlparse(link)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RuntimeError(f"Unexpected HARUKA link: {link!r}")
    try:
        port = parsed.port
    except ValueError as exc:
        raise RuntimeError(f"Invalid HARUKA link: {link!r}") from exc
    if port != 9394:
        raise RuntimeError(f"Unexpected HARUKA port: {port!r}")

    return f"{parsed.scheme}://{parsed.netloc}"


def refresh_playlist(text: str, base_url: str) -> tuple[str, int, int]:
    lines = text.splitlines()
    matched = 0
    changed = 0

    # Do not depend on the display name or group. In this project, port 9394
    # with /stream/<number>.m3u8 is the HARUKA signature, so refresh every
    # matching URL wherever it appears (TV, BS/CS, Rch/Pigoo, manual blocks).
    for i, line in enumerate(lines):
        old_url = line.strip()
        if not is_haruka_stream_url(old_url):
            continue

        parsed = urllib.parse.urlparse(old_url)
        matched += 1
        new_url = f"{base_url}{parsed.path}"
        if parsed.query:
            new_url += f"?{parsed.query}"
        if parsed.fragment:
            new_url += f"#{parsed.fragment}"

        if new_url != old_url:
            lines[i] = new_url
            changed += 1

    if matched == 0:
        raise RuntimeError("No HARUKA 9394 stream URLs found in playlist")

    trailing_newline = "\n" if text.endswith(("\n", "\r")) else ""
    return "\n".join(lines) + trailing_newline, matched, changed


def main() -> None:
    base_url = fetch_current_base()
    print(f"HARUKA current base: {base_url}")

    # Validate both outputs before writing either. The published aggregate can
    # contain HARUKA rows outside TV's section (for example Pigoo in Rch).
    updates = []
    for path in (FREEWIFI, RAKUTEN_PLAYLIST, PUBLISHED):
        original = path.read_text(encoding="utf-8-sig", errors="strict")
        updated, matched, changed = refresh_playlist(original, base_url)
        print(f"{path}: HARUKA entries checked: {matched}; changed: {changed}")
        updates.append((path, updated, changed))

    for path, updated, changed in updates:
        if changed:
            path.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    main()
