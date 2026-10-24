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
PUBLIC_MIRROR = "https://raw.githubusercontent.com/ZXArkin/my-personal-iptv/main/jp-playlist.m3u"
TOKEN_PATTERN = re.compile(r'ac_tk=[^&"\\s]+')


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


def main() -> int:
    url = os.environ.get("NEWBLOG_MASTER_URL", "").strip()
    if not url:
        print("ERROR: GitHub Actions secret NEWBLOG_MASTER_URL is not configured", file=sys.stderr)
        return 2
    try:
        catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
        approved = set(catalog)
        if len(approved) != 101:
            raise UnsafeSource("Expected 101 approved channels in channel_map.json")
        original = SOURCE.read_text(encoding="utf-8-sig")
        updated, changed, new_slugs = update_source(original, download_source(url), approved)
        if updated != original:
            SOURCE.write_text(updated, encoding="utf-8")
        print(f"newblog: approved={len(approved)}, changed={len(changed)}, unapproved_new={len(new_slugs)}")
        if changed:
            print("Updated channels: " + ", ".join(sorted(changed)))
        if new_slugs:
            print("::warning::Unapproved new channels (not imported): " + ", ".join(new_slugs))
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as fp:
                fp.write(f"## FreeWiFi newblog refresh\n\nApproved: {len(approved)} · Changed: {len(changed)} · New (not imported): {len(new_slugs)}\n\n")
                if new_slugs:
                    fp.write("Unapproved slugs: " + ", ".join(new_slugs) + "\n")
        return 0
    except (UnsafeSource, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: newblog refresh blocked; last good source preserved. {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
