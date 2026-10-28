#!/usr/bin/env python3
"""Keep newblog live streams and replay VOD out of yovi, FreeWiFi and TV.

Never reintroduce retired newblog streams into FreeWiFi or TV canonical.
No changes to 5002, Sinori or 49 approved FreeWiFi YoiTV rows (14 terrestrial, 18 BS, 17 CS).
"""
from pathlib import Path
import re
from sync_tv import get_source, catchup_attributes, replay_templates, vod_payload, VOD_START, VOD_END

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "newblog/source.m3u"
FREEWIFI = ROOT / "freewifi"
CANONICAL = ROOT / "tv/playlist.m3u"
YOVI = ROOT / "yovi"
LABEL = "（newblog系）"


def parse_rows(text):
    lines = text.splitlines()
    result = []
    i = 0
    while i < len(lines):
        if lines[i].startswith("#EXTINF:"):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and not lines[j].startswith("#"):
                result.append((lines[i], lines[j].strip()))
                i = j + 1
                continue
        i += 1
    return result


def is_newblog(inf, url):
    return (LABEL in inf
            or 'tvg-id="newblog.vod.' in inf
            or "0i4neux01.charandom.blog/stream/jp/" in url)


def strip_newblog(text):
    lines = text.splitlines()
    output = []
    i = 0
    while i < len(lines):
        if lines[i].strip() == VOD_START:
            i += 1
            while i < len(lines) and lines[i].strip() != VOD_END:
                i += 1
            if i == len(lines):
                raise ValueError("Unclosed newblog VOD block")
            i += 1
            continue
        if lines[i].startswith("#EXTINF:"):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            url = lines[j].strip() if j < len(lines) else ""
            if is_newblog(lines[i], url):
                i = j + 1
                continue
        output.append(lines[i])
        i += 1
    return re.sub(r"\n{4,}", "\n\n\n", "\n".join(output)).rstrip() + "\n"


def count_sources(text, term):
    return sorted(url for inf, url in parse_rows(text) if term in url)


def build_live():
    template = replay_templates()
    if len(template) != 101:
        raise ValueError("newblog replay metadata is incomplete")
    result = []
    for slug, meta, url in get_source():
        cat = meta["category"]
        group = ("BS newblog系" if slug == "green_channel" else
                 "Rch newblog系" if cat == "Rch" else f"{cat} newblog系")
        tag = ('#EXTINF:-1 tvg-id="' + meta["id"] + '" tvg-logo="' + meta["logo"]
               + '" group-title="' + group + '"'
               + catchup_attributes(slug, template) + ","
               + meta["name"] + LABEL)
        result.append((tag, url))
    if len(result) != 101:
        raise ValueError("Expected exactly 101 newblog live streams")
    return result


def insert_beside(lines, tag, uri):
    channel_id = re.search(r'tvg-id="([^"]+)"', tag)
    if not channel_id:
        raise ValueError("Missing channel ID")
    needle = 'tvg-id="' + channel_id.group(1) + '"'
    last = None
    for index, line in enumerate(lines):
        if line.startswith("#EXTINF:") and needle in line:
            j = index + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            last = j + 1
    if last is not None:
        lines[last:last] = ["", tag, uri]
    else:
        lines.extend(["", tag, uri])


def sync():
    before_free = FREEWIFI.read_text(encoding="utf-8-sig")
    before_tv = CANONICAL.read_text(encoding="utf-8-sig")
    before_yovi = YOVI.read_text(encoding="utf-8-sig")
    clean_free = strip_newblog(before_free)
    clean_tv = strip_newblog(before_tv)
    preserved = ("/tv/yoitv.php", ":5002/", "ri.shinori.my.id/")
    for label, before, after in (("freewifi", before_free, clean_free),
                                 ("canonical", before_tv, clean_tv)):
        for term in preserved:
            if count_sources(before, term) != count_sources(after, term):
                raise RuntimeError(f"{label}: protected source changed: {term}")
        if any(is_newblog(tag, url) for tag, url in parse_rows(after)):
            raise RuntimeError(f"{label}: retired newblog stream returned")
    # Owner policy: keep yovi free of all newblog live and VOD entries.
    # This must stay idempotent even when an older workflow invokes sync().
    updated_yovi = strip_newblog(before_yovi)
    for path, old, new in ((FREEWIFI,before_free,clean_free),
                           (CANONICAL,before_tv,clean_tv),
                           (YOVI,before_yovi,updated_yovi)):
        if old != new:
            path.write_text(new, encoding="utf-8")
    print("newblog live and VOD removed from yovi; FreeWiFi and canonical cleared")


if __name__ == "__main__":
    sync()
