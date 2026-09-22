from pathlib import Path
import json
import os
import re
import urllib.parse
import urllib.request

FREEWIFI = Path("tv/playlist.m3u")
API_URL = "http://app.harukashop.site:3008/api/news/get-link"
AU = os.environ.get("HARUKA_AU", "05zs80LO1csztPgNDkFeJcwkiSqNw9J6")
HEADERS = {
    "user-agent": "Dart/3.12 (dart:io)",
    "au": AU,
    "content-type": "application/json; charset=UTF-8",
}
PAYLOAD = {"os": 1, "appId": 7, "deviceId": 602539, "newsId": 12}
STREAM_PATH_RE = re.compile(r"/stream/\d+\.m3u8")


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

    for i, line in enumerate(lines):
        if not line.startswith("#EXTINF:") or "(haruka(9394))" not in line:
            continue

        j = i + 1
        while j < len(lines) and not lines[j].strip():
            j += 1
        if j >= len(lines) or lines[j].lstrip().startswith("#"):
            raise RuntimeError(f"HARUKA entry has no URL after line {i + 1}")

        old_url = lines[j].strip()
        parsed = urllib.parse.urlparse(old_url)
        if parsed.scheme not in {"http", "https"} or not STREAM_PATH_RE.fullmatch(parsed.path):
            raise RuntimeError(f"Unexpected HARUKA playlist URL: {old_url!r}")

        matched += 1
        new_url = f"{base_url}{parsed.path}"
        if parsed.query:
            new_url += f"?{parsed.query}"
        if parsed.fragment:
            new_url += f"#{parsed.fragment}"

        if new_url != old_url:
            lines[j] = new_url
            changed += 1

    if matched == 0:
        raise RuntimeError("No (haruka(9394)) entries found in freewifi")

    trailing_newline = "\n" if text.endswith(("\n", "\r")) else ""
    return "\n".join(lines) + trailing_newline, matched, changed


def main() -> None:
    original = FREEWIFI.read_text(encoding="utf-8-sig", errors="strict")
    base_url = fetch_current_base()
    updated, matched, changed = refresh_playlist(original, base_url)

    print(f"HARUKA current base: {base_url}")
    print(f"HARUKA entries checked: {matched}; changed: {changed}")

    if changed:
        FREEWIFI.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    main()
