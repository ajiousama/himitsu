#!/usr/bin/env python3
"""Safely refresh the approved newblog channel URLs for FreeWiFi.

Use NEWBLOG_MASTER_URL (GitHub Actions secret). The master URL and stream
authentication tokens are never printed by this script.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "newblog/channel_map.json"
SOURCE = ROOT / "newblog/source.m3u"
HOST = "0i4neux01.charandom.blog"
JP_STREAM = re.compile(r"/stream/jp/([\w+\-]+)/stream-output\.m3u8\Z")
MAX_DOWNLOAD_BYTES = 2 * 1024 * 1024
# Publicly maintained mirror. Used ONLY when the approved upstream rejects authentication.
PUBLIC_MIRROR = "https://raw.githubusercontent.com/ZXArkin/my-personal-iptv/iptv-radio/jp-playlist.m3u"
TOKEN_PATTERN = re.compile(r'ac_tk=[^&"\s]+')


class UnsafeSource(ValueError):
    pass


def get_slug(uri: str) -> str | None:
    """Return a Japanese source slug, ignoring non-JP channels."""
    p = urlsplit(uri.strip())
    if p.scheme != "https" or p.hostname != HOST:
        return None
    matched = JP_STREAM.fullmatch(p.path)
    if matched is None:
        return None
    if not parse_qs(p.query).get("ac_tk"):
        raise UnsafeSource(f"JP station {matched.group(1)} has no access token")
    return matched.group(1)


def parse_playlist(body: str, *, old: bool = False) -> tuple[list[str], dict[str, tuple[int, str, str]]]:
    """Parse M3U and return {slug: (metadata line index, metadata, URL)}."""
    lines = body.lstrip("\ufeff").splitlines()
    if not lines or not lines[0].startswith("#EXTM3U"):
        raise UnsafeSource("Source is not an extended M3U playlist")
    found: dict[str, tuple[int, str, str]] = {}
    for i, line in enumerate(lines):
        if not line.startswith("#EXTINF:"):
            continue
        if i + 1 >= len(lines) or not lines[i + 1].strip() or lines[i + 1].startswith("#"):
            raise UnsafeSource(f"Incomplete EXTINF entry at line {i + 1}")
        uri = lines[i + 1].strip()
        slug = get_slug(uri)
        if slug is None:
            if old:
                raise UnsafeSource(f"Unexpected stored channel URL at line {i + 2}")
            continue
        if slug in found:
            raise UnsafeSource(f"Duplicate Japanese channel: {slug}")
        found[slug] = (i, line, uri)
    if not found:
        raise UnsafeSource("No matching Japanese channels in master playlist")
    return lines, found


def update_source(original: str, master: str, approved: set[str]) -> tuple[str, list[str], list[str]]:
    """Keep the stored 101-row ordering, replacing only approved metadata/URLs."""
    original_lines, existing = parse_playlist(original, old=True)
    _, latest = parse_playlist(master)
    if set(existing) != approved:
        raise UnsafeSource("Stored channel list does not match channel_map.json")
    missing = sorted(approved - set(latest))
    if missing:
        raise UnsafeSource(f"Missing {len(missing)} approved channels: {', '.join(missing)}")
    unexpected = sorted(set(latest) - approved)
    changed: list[str] = []
    updated_lines = original_lines[:]
    for slug, (line_index, old_inf, old_url) in existing.items():
        _, new_inf, new_url = latest[slug]
        # An external mirror may refresh tokens, but must not rewrite names,
        # logos, catchup configuration, stream paths, or other URL parameters.
        # Approved changes are limited strictly to the ac_tk value.
        if TOKEN_PATTERN.sub("ac_tk=<TOKEN>", new_inf) != TOKEN_PATTERN.sub("ac_tk=<TOKEN>", old_inf):
            raise UnsafeSource(f"Unapproved metadata change for {slug}")
        if TOKEN_PATTERN.sub("ac_tk=<TOKEN>", new_url) != TOKEN_PATTERN.sub("ac_tk=<TOKEN>", old_url):
            raise UnsafeSource(f"Unapproved stream URL change for {slug}")
        if new_inf != old_inf or new_url != old_url:
            changed.append(slug)
        updated_lines[line_index] = new_inf
        updated_lines[line_index + 1] = new_url
    return "\n".join(updated_lines).rstrip("\n") + "\n", changed, unexpected


def _fetch_playlist(url: str, *, label: str) -> str:
    """Fetch a fixed HTTPS source; reject redirects and keep credentials out of logs."""
    request = urllib.request.Request(url, headers={
        "User-Agent": "freewifi-newblog-sync/1.0",
        "Accept": "application/x-mpegURL, application/vnd.apple.mpegurl, text/plain, */*",
    })
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            if response.geturl().split("?", 1)[0] != url.split("?", 1)[0]:
                raise UnsafeSource(f"Unexpected {label} URL redirect")
            data = response.read(MAX_DOWNLOAD_BYTES + 1)
    except urllib.error.HTTPError as exc:
        raise UnsafeSource(f"Failed to retrieve {label} M3U (HTTP {exc.code})") from None
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        # Exceptions may contain sensitive URLs; only report their type.
        raise UnsafeSource(f"Failed to retrieve {label} M3U ({type(exc).__name__})") from None
    if len(data) > MAX_DOWNLOAD_BYTES:
        raise UnsafeSource(f"{label} playlist exceeds 2 MiB")
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise UnsafeSource(f"{label} playlist is not UTF-8") from None


def download_source(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != HOST or parsed.path != "/stream/master.m3u":
        raise UnsafeSource("NEWBLOG_MASTER_URL is not the expected HTTPS master playlist")
    if not parse_qs(parsed.query).get("pass"):
        raise UnsafeSource("NEWBLOG_MASTER_URL must contain the master playlist pass parameter")
    try:
        return _fetch_playlist(url, label="master")
    except UnsafeSource as exc:
        # A password-protected primary source may temporarily reject the secret.
        # Fallback is fixed to one public mirror; it must pass the SAME 101-station
        # validation as the direct master before any source file can be published.
        if str(exc) not in {
            "Failed to retrieve master M3U (HTTP 401)",
            "Failed to retrieve master M3U (HTTP 403)",
        }:
            raise
        print("::warning::Primary newblog master denied access; checking approved public mirror", file=sys.stderr)
        return _fetch_playlist(PUBLIC_MIRROR, label="public mirror")



# Independent, public token source. Its plain-text playlist omits some of
# our 101 approved channels, so it must never replace the canonical catalog.
KAMONKA_MIRROR = "https://raw.githubusercontent.com/kamonka/kamonka.github.io/main/tv.txt"
KAMONKA_STREAM = re.compile(
    r"https://0i4neux01\.charandom\.blog/stream/jp/[\w+\-]+/stream-output\.m3u8\?[^\s,#]+",
    re.I,
)
TOKEN_VALUE = re.compile(r"^[A-Za-z0-9_.\-]{32,600}$")
PROBE_SLUGS = ("nhk_g", "tbs", "fuji_tv_one", "kbs")


def extract_kamonka_tokens(body: str, approved: set[str]) -> dict[str, str]:
    """Validate the independently curated comma/URL text list (not an M3U).

    Ignore unapproved slugs and alternative '#' URLs, require a strong overlap
    with our approved stations and one consistent JWT/JWE value, and never
    import third-party metadata or channel names.
    """
    if len(body) > MAX_DOWNLOAD_BYTES or "<html" in body[:200].lower():
        raise UnsafeSource("Invalid kamonka source")
    found: dict[str, str] = {}
    for line in body.splitlines():
        if "," not in line:
            continue
        # Some records contain '#' separated alternate providers.
        urls = line.split(",", 1)[1].split("#")
        for item in urls:
            item = item.strip()
            if not KAMONKA_STREAM.fullmatch(item):
                continue
            slug = get_slug(item)
            if slug not in approved:
                continue
            parsed = urlsplit(item)
            qs = parse_qs(parsed.query)
            if qs.get("mode") != ["hls"] or len(qs.get("ac_tk", [])) != 1:
                continue
            token = qs["ac_tk"][0]
            if not TOKEN_VALUE.fullmatch(token):
                raise UnsafeSource("Invalid kamonka access-token format")
            if slug in found and found[slug] != token:
                raise UnsafeSource("Ambiguous kamonka token for approved station")
            found[slug] = token
    # The source currently lists 94/101 channels. Keep the missing ones.
    if len(found) < 90 or len(set(found.values())) != 1:
        raise UnsafeSource("Kamonka source has insufficient or inconsistent approved stations")
    return found


def apply_kamonka_tokens(original: str, tokens: dict[str, str], approved: set[str]) -> tuple[str, list[str]]:
    """Apply kamonka's verified shared ac_tk to all 101 approved stations.

    Kamonka publishes 94 of our stations today; all 94 use one identical
    stream token. The user confirmed four different stations play, and approved
    inferred use of the same token for the seven absent stations. Change
    only the ac_tk value, including each channel's catchup template; never
    modify metadata, channel paths, ordering, or unrelated FreeWiFi providers.
    """
    lines, existing = parse_playlist(original, old=True)
    if set(existing) != approved:
        raise UnsafeSource("Stored channel list does not match channel_map.json")
    values = set(tokens.values())
    if not tokens or len(values) != 1 or not set(tokens).issubset(approved):
        raise UnsafeSource("Kamonka token missing, ambiguous, or unapproved")
    shared_token = next(iter(values))
    replacement = "ac_tk=" + shared_token
    updated = lines[:]
    changed = []
    for slug, (i, info, url) in existing.items():
        new_info = TOKEN_PATTERN.sub(lambda _: replacement, info)
        new_url = TOKEN_PATTERN.sub(lambda _: replacement, url)
        if new_info != info or new_url != url:
            changed.append(slug)
        updated[i], updated[i + 1] = new_info, new_url
    return "\n".join(updated).rstrip("\n") + "\n", changed


def probe_candidate(body: str, *, name: str) -> str:
    """Probe small HLS manifests; never download video and never log tokens.

    Return 'ok', 'forbidden', or 'unknown'. Ambiguous/network-blocked results
    must never replace a previously published source.
    """
    _, streams = parse_playlist(body, old=True)
    passed = 0
    forbidden = False
    for slug in PROBE_SLUGS:
        if slug not in streams:
            continue
        uri = streams[slug][2]
        request = urllib.request.Request(
            uri, headers={"User-Agent": "Mozilla/5.0",
                          "Accept": "application/vnd.apple.mpegurl, application/x-mpegURL, */*"}
        )
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                if urlsplit(response.geturl()).scheme != "https":
                    continue
                sample = response.read(2048).lstrip(b"\xef\xbb\xbf")
                if sample.startswith(b"#EXTM3U"):
                    passed += 1
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                forbidden = True
        except (urllib.error.URLError, TimeoutError, OSError):
            continue
    result = "forbidden" if forbidden else "ok" if passed >= 2 else "unknown"
    print(f"newblog probe: {name}={result} ({passed}/{len(PROBE_SLUGS)} manifests)")
    return result


def choose_source(original: str, master_url: str, approved: set[str]) -> tuple[str, str, int]:
    """Monitor master, ZXArkin and kamonka independently.

    Use only candidates for which the runner can actually fetch HLS manifests;
    do not assume the most recently committed token is valid.
    """
    candidates: list[tuple[str, str, int]] = []
    parsed = urlsplit(master_url)
    if master_url:
        if (parsed.scheme != "https" or parsed.hostname != HOST
                or parsed.path != "/stream/master.m3u"
                or not parse_qs(parsed.query).get("pass")):
            raise UnsafeSource("NEWBLOG_MASTER_URL is not the approved HTTPS master playlist")
        try:
            master = _fetch_playlist(master_url, label="master")
            body, changed, _ = update_source(original, master, approved)
            candidates.append(("master", body, len(changed)))
        except UnsafeSource as exc:
            # Never display a secret, token, or URL in logs.
            if str(exc) in ("Failed to retrieve master M3U (HTTP 401)",
                            "Failed to retrieve master M3U (HTTP 403)"):
                print("::warning::newblog master authentication denied; checking public mirrors")
            else:
                print("::warning::newblog master unavailable or invalid; retaining existing channels")

    # Public mirrors are independent candidates, not a chain which always
    # trusts the latest Git commit. Kamonka may have a valid older token.
    try:
        body = _fetch_playlist(PUBLIC_MIRROR, label="ZXArkin public mirror")
        candidate, changed, _ = update_source(original, body, approved)
        candidates.append(("ZXArkin", candidate, len(changed)))
    except UnsafeSource:
        print("::warning::ZXArkin mirror not available or not approved")

    try:
        body = _fetch_playlist(KAMONKA_MIRROR, label="kamonka public mirror")
        tokens = extract_kamonka_tokens(body, approved)
        candidate, changed = apply_kamonka_tokens(original, tokens, approved)
        candidates.append(("kamonka", candidate, len(changed)))
        print(f"newblog candidate: kamonka approved={len(tokens)}, missing={len(approved)-len(tokens)}")
    except UnsafeSource:
        print("::warning::kamonka mirror not available or not approved")

    if not candidates:
        raise UnsafeSource("No validated newblog source available; last good source preserved")
    # Master first if it works; otherwise favour the user-tested kamonka over
    # ZXArkin when both are demonstrably working.
    results = {}
    for name, body, _ in candidates:
        results[name] = probe_candidate(body, name=name)
    for preferred in ("master", "kamonka", "ZXArkin"):
        for name, candidate, count in candidates:
            if name == preferred and results[name] == "ok":
                return candidate, name, count
    # No verified replacement. Do not churn to a newer but expired token.
    print("::warning::No candidate proven playable; preserving existing newblog tokens")
    return original, "preserved", 0



def main() -> int:
    url = os.environ.get("NEWBLOG_MASTER_URL", "").strip()
    try:
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        approved = set(catalog)
        if len(approved) != 101:
            raise UnsafeSource("Expected 101 approved channels in channel_map.json")
        original = SOURCE.read_text(encoding="utf-8-sig")
        updated, selected, count = choose_source(original, url, approved)
        if updated != original:
            SOURCE.write_text(updated, encoding="utf-8")
        print(f"newblog: approved={len(approved)}, selected={selected}, changed={count}")
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as fp:
                fp.write(f"## FreeWiFi newblog refresh\n\nApproved: {len(approved)} · Selected: {selected} · Changed: {count}\n\n")
        return 0
    except (UnsafeSource, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: newblog refresh blocked; last good source preserved. {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
