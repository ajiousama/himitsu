#!/usr/bin/env python3
"""Maintain 101 approved newblog entries after existing FreeWiFi TV sources."""
from __future__ import annotations
import json, re, time
from datetime import datetime
from html import unescape
from zoneinfo import ZoneInfo
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "newblog/source.m3u"
CATALOG = ROOT / "newblog/channel_map.json"
TV = ROOT / "tv/playlist.m3u"
LABEL = "（newblog系）"
COUNT = 101

VOD_REPLAYS = ROOT / "newblog/vod_replays.json"
VOD_START = "# === NEWBLOG_VOD_START ==="
VOD_END = "# === NEWBLOG_VOD_END ==="
REPLAY_DAYS = 14  # Keep replay controls and the VOD shelf within two weeks.
REPLAY_RETENTION_SECONDS = REPLAY_DAYS * 86400
REPLAY_DAYS_BY_SLUG = {"kbs": 7, "fuji_tv_one": 7}  # Verified shorter catch-up: KBS Kyoto and Fuji TV ONE.


def replay_retention_seconds(slug):
    return REPLAY_DAYS_BY_SLUG.get(slug, REPLAY_DAYS) * 86400
APPROVED_REPLAY_SLUGS = {"gccx_one": "fuji_tv_one", "nogizaka_koujichuu": "tv_tokyo", "knight_scoop": "abc", "homeru_chan": "mbs", "bakobako_kbs": "kbs", "bakobako_sun": "sun", "tsurigoro": "kansai_tv", "big_fishing_kbs": "kbs", "big_fishing_sun": "sun", "keibajou_no_tatsujin": "green_channel", "keiba_wanderer": "green_channel"}


def replay_templates():
    """Read current newblog replay templates without logging signed URLs."""
    if not SOURCE.is_file():
        return {}
    templates = {}
    for line in SOURCE.read_text(encoding="utf-8-sig").splitlines():
        if not line.startswith("#EXTINF:"):
            continue
        match = re.search(r'catchup-source="([^"]+)"', line)
        if not match:
            continue
        url = match.group(1)
        parsed = urlsplit(url)
        slug_match = re.fullmatch(r"/stream/jp/([a-z0-9_+\-]+)/replay\.m3u8", parsed.path)
        if (parsed.scheme == "https" and parsed.hostname == "0i4neux01.charandom.blog"
                and slug_match and parse_qs(parsed.query).get("ac_tk")
                and ("$" + "{start}") in url):
            templates[slug_match.group(1)] = url
    return templates



BIG_FISHING_IDS = {"big_fishing_kbs", "big_fishing_sun"}

# Search only programmes already approved in the VOD registry. The EPG
# carries broadcast start times, so no replay URL or airtime is guessed.
EPG_TITLE_MATCHES = {
    "gccx_one": ("ゲームセンターCX",),
    "nogizaka_koujichuu": ("乃木坂工事中",),
    "knight_scoop": ("探偵！ナイトスクープ", "探偵!ナイトスクープ"),
    "homeru_chan": ("土曜のあさはほめるちゃん", "土曜の朝はほめるちゃん"),
    "bakobako_kbs": ("ケンコバのバコバコナイト",),
    "bakobako_sun": ("ケンコバのバコバコナイト",),
    "tsurigoro": ("釣りごろつられごろ", "釣りごろ釣られごろ"),
    "big_fishing_kbs": ("ビッグ・フィッシング", "ビッグフィッシング"),
    "big_fishing_sun": ("ビッグ・フィッシング", "ビッグフィッシング"),
    "keibajou_no_tatsujin": ("競馬場の達人",),
    "keiba_wanderer": ("競馬ワンダラー",),
}


def discover_registered_replays(now_epoch, registered):
    """Refresh approved show episodes using broadcast-matched EPG history."""
    history = ROOT / "haru/haru_kai_epg_history.xml"
    if not history.is_file():
        return []
    by_slug = {}
    for item in registered:
        item_id = item.get("id")
        if item_id in EPG_TITLE_MATCHES:
            by_slug.setdefault(APPROVED_REPLAY_SLUGS[item_id], {})[item_id] = item
    # Register recurring shows directly; no guessed broadcast timestamp is needed.
    channel_meta = json.loads(CATALOG.read_text(encoding="utf-8"))["green_channel"]
    by_slug.setdefault("green_channel", {})["keiba_wanderer"] = {
        "id": "keiba_wanderer", "slug": "green_channel",
        "tvg_name": "競馬ワンダラー", "logo": channel_meta["logo"],
    }
    body = history.read_text(encoding="utf-8", errors="replace")
    pairs = re.finditer(
        r"<!--\s*https://haru\.charandom\.blog/stream/jp/([a-z0-9_+\-]+)/replay\.m3u8\?[^<]*?start=(\d+)[^<]*?-->\s*<programme\b[^>]*>(.*?)</programme>",
        body, re.S | re.I,
    )
    found = []
    seen = set()
    for match in pairs:
        slug, start = match.group(1), int(match.group(2))
        candidates = by_slug.get(slug, {})
        if not candidates or not 0 <= now_epoch - start < replay_retention_seconds(slug):
            continue
        local = datetime.fromtimestamp(start, ZoneInfo("Asia/Tokyo"))
        title_match = re.search(r"<title(?:\s+[^>]*)?>(.*?)</title>", match.group(3), re.S | re.I)
        if not title_match:
            continue
        title = unescape(re.sub(r"<[^>]+>", "", title_match.group(1))).strip()
        for item in candidates.values():
            # Broadcasters may insert ASCII/full-width spaces in programme names.
            # Compare without whitespace so "釣りごろ　つられごろ" matches.
            compact_title = re.sub(r"\s+", "", title)
            if not any(re.sub(r"\s+", "", word) in compact_title
                       for word in EPG_TITLE_MATCHES[item["id"]]):
                continue
            key = (item["id"], start)
            if key in seen:
                continue
            seen.add(key)
            name = item["tvg_name"]
            if item["id"] == "keibajou_no_tatsujin":
                name = "競馬場の達人セレクション" if "セレクション" in title else "競馬場の達人"
            elif item["id"] == "keiba_wanderer":
                match_name = re.search(r"(?:新・)?競馬ワンダラー[0-9０-９]*", title)
                name = match_name.group(0) if match_name else "競馬ワンダラー"
            found.append({
                "id": item["id"], "slug": slug, "start": start,
                "tvg_name": name, "logo": item["logo"],
                "title": f"📼 {name} {local:%m/%d %H:%M}｜{title.replace(chr(34), chr(39))}",
            })
    return found



def tatsujin_episode_key(item):
    """Identify a Tatsujin instalment across its original and repeat airings."""
    detail = item["title"].partition("｜")[2]
    kind = "selection" if "セレクション" in item["tvg_name"] or "セレクション" in detail else "regular"
    guest = re.search(r"競馬場の達人(?:セレクション)?[（(]([^）)]+)[）)]", detail)
    if not guest:
        guest = re.search(r"#\s*\d+\s+([^\s]+)", detail)
    if guest:
        return kind, guest.group(1).strip()
    number = re.search(r"#\s*(\d+)", detail)
    return kind, number.group(1) if number else detail.strip()


def format_vod_display(item):
    """Show the challenged game FIRST for blog-series GCCX replays only.

    Some IPTV clients prefer tvg-name while others show the text after the
    EXTINF comma, so both labels must start with the software title.
    The stored programme metadata, EPG matching, replay URL and group stay
    untouched; this is a presentation-only change.
    """
    title, tvg_name = item["title"], item["tvg_name"]
    if item["id"] != "gccx_one":
        return title, tvg_name

    detail = title.partition("｜")[2].strip()
    if not detail:
        return title, tvg_name

    archive = "アーカイブス" in detail
    series = "ゲームセンターCX アーカイブス" if archive else "ゲームセンターCX"
    broadcast = datetime.fromtimestamp(int(item["start"]), ZoneInfo("Asia/Tokyo"))
    date = broadcast.strftime("%m/%d %H:%M")
    episode = re.search(r"#\s*(\d+)", detail)
    quoted_game = re.search(r"「([^」]+)」", detail)
    if quoted_game:
        game = quoted_game.group(1).strip()
        if not game:
            return title, tvg_name
        first = game + (f" #{episode.group(1)}" if episode else "")
        # Preserve the programme subtitle, but move it after the key title.
        subtitle = re.sub(r"^ゲームセンターCX\s*(?:有野の挑戦\s*アーカイブス)?\s*", "", detail)
        if episode:
            subtitle = subtitle.replace(episode.group(0), "", 1)
        subtitle = subtitle.replace(quoted_game.group(0), "", 1)
        subtitle = subtitle.strip(" \u3000:：-―")
        if subtitle in ("に挑戦", "に挑戦！"):
            subtitle = ""
    else:
        # Specials and travel segments do not have a challenged game. Put
        # their specific episode subject first, not a guessed game title.
        first = re.sub(r"^ゲームセンターCX\s*", "", detail).strip()
        if not first:
            return title, tvg_name
        subtitle = ""

    display = f"📼 {first}｜{series} {date}"
    if subtitle:
        display += "｜" + subtitle
    tvg_display = f"{first}｜{series}"
    return display, tvg_display


def vod_payload(now_epoch=None):
    """Publish approved replays using each channel\u0027s rolling retention window."""
    if not VOD_REPLAYS.is_file():
        return VOD_START + "\n" + VOD_END
    records = json.loads(VOD_REPLAYS.read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("newblog VOD registry must be a list")
    templates = replay_templates()
    now_epoch = int(time.time()) if now_epoch is None else int(now_epoch)
    records.extend(discover_registered_replays(now_epoch, records))
    # The same weekly programme airs on SUN then KBS. Publish one copy:
    # prefer KBS whenever its catch-up template and programme both exist.
    chosen = {}
    ordinary = []
    for item in records:
        if not isinstance(item, dict):
            raise ValueError("Malformed newblog VOD item")
        if item.get("id") not in BIG_FISHING_IDS:
            ordinary.append(item)
            continue
        slug, start = item["slug"], int(item["start"])
        if not 0 <= now_epoch - start < replay_retention_seconds(slug) or slug not in templates:
            continue
        week = datetime.fromtimestamp(start, ZoneInfo("Asia/Tokyo")).strftime("%G-W%V")
        old = chosen.get(week)
        if old is None or (slug == "kbs" and old["slug"] != "kbs") or (slug == old["slug"] and start > int(old["start"])):
            chosen[week] = item
    records = ordinary + sorted(chosen.values(), key=lambda row: -int(row["start"]))
    # Keep each programme together, newest broadcast first. Put the newblog
    # GCCX episodes last so the adjacent VOD5 GCCX catalog follows them.
    programme_order = {
        "nogizaka_koujichuu": 0,
        "knight_scoop": 1,
        "homeru_chan": 2,
        "bakobako_kbs": 3, "bakobako_sun": 3,
        "tsurigoro": 4,
        "big_fishing_kbs": 5, "big_fishing_sun": 5,
        "keibajou_no_tatsujin": 6,
        "keiba_wanderer": 7,
        "gccx_one": 8,
    }
    records.sort(key=lambda item: (
        programme_order.get(item["id"], 99), -int(item["start"])
    ))
    entries = []
    seen = set()
    seen_tatsujin = set()
    for item in records:
        if not isinstance(item, dict) or item.get("id") not in APPROVED_REPLAY_SLUGS:
            raise ValueError("Unapproved newblog VOD item")
        slug = APPROVED_REPLAY_SLUGS[item["id"]]
        if item.get("slug") != slug:
            raise ValueError("newblog VOD slug mismatch")
        start = int(item["start"])
        if not 0 <= now_epoch - start < replay_retention_seconds(slug) or slug not in templates:
            continue
        # The current requested range begins on October 10, JST (inclusive).
        if datetime.fromtimestamp(start, ZoneInfo("Asia/Tokyo")).strftime("%Y-%m-%d") < "2026-10-10":
            continue
        key = (item["id"], start)
        if key in seen:
            continue
        if item["id"] == "keibajou_no_tatsujin":
            episode = tatsujin_episode_key(item)
            if episode in seen_tatsujin:
                continue
            seen_tatsujin.add(episode)
        seen.add(key)
        uri = templates[slug].replace("$" + "{start}", str(start))
        display_title, display_name = format_vod_display(item)
        extinf = (
            '#EXTINF:-1 tvg-id="newblog.vod.' + item["id"] + "." + str(start)
            + '" tvg-name="' + display_name + '" tvg-logo="' + item["logo"]
            + '" group-title="blog系VOD",' + display_title
        )
        entries.extend([extinf, uri])
    return "\n".join([VOD_START, *entries, VOD_END])


def strip_generated_vod_entries(text):
    """Remove prior replay rows even if a section normalizer stripped markers."""
    lines = text.splitlines()
    kept = []
    i = 0
    while i < len(lines):
        if (lines[i].startswith("#EXTINF:")
                and re.search(r'tvg-id="newblog\.vod\.[^"]+"', lines[i])):
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i < len(lines) and not lines[i].lstrip().startswith("#"):
                i += 1
            continue
        kept.append(lines[i])
        i += 1
    return "\n".join(kept)




def replace_vod_block(text):
    text = strip_generated_vod_entries(text)
    payload = vod_payload()
    pattern = re.compile(r"(?m)^" + re.escape(VOD_START) + r"\n.*?^"
                         + re.escape(VOD_END) + r"(?:\n|$)", re.S)
    if pattern.search(text):
        return pattern.sub(payload + "\n", text, count=1)
    return text.rstrip() + "\n\n" + payload + "\n"


def catchup_attributes(slug: str, templates: dict[str, str]) -> str:
    """Expose source-specific rewind metadata for each approved newblog channel.

    These attributes reference upstream recordings, not locally downloaded
    videos. A playlist limit does not guarantee archive availability.
    """
    url = templates.get(slug)
    if not url:
        raise ValueError("Missing validated newblog catchup template: " + slug)
    return (' catchup="default" catchup-days="' + str(REPLAY_DAYS_BY_SLUG.get(slug, REPLAY_DAYS))
            + '" catchup-source="' + url + '"')


def get_source():
    metadata = json.loads(CATALOG.read_text(encoding="utf-8"))
    lines = SOURCE.read_text(encoding="utf-8-sig").splitlines()
    out = []
    for i, inf in enumerate(lines):
        if not inf.startswith("#EXTINF:"):
            continue
        if i + 1 >= len(lines):
            raise ValueError("Incomplete source")
        url = lines[i + 1].strip()
        p = urlsplit(url)
        m = re.fullmatch(r"/stream/jp/([\w+\-]+)/stream-output\.m3u8", p.path)
        if (p.scheme != "https" or p.hostname != "0i4neux01.charandom.blog"
                or not m or not parse_qs(p.query).get("ac_tk")):
            raise ValueError("Unexpected newblog URL")
        slug = m.group(1)
        if slug not in metadata or any(r[0] == slug for r in out):
            raise ValueError("Unknown or duplicate newblog station: " + slug)
        out.append((slug, metadata[slug], url))
    if len(out) != COUNT or set(r[0] for r in out) != set(metadata):
        raise ValueError("newblog 101-station registry mismatch")
    return out

def apply(text):
    raise RuntimeError('newblog moved to yovi: use newblog/sync_yovi.py')
    lines = text.splitlines()
    kept = []
    i = 0
    while i < len(lines):
        if lines[i].startswith("#EXTINF:") and LABEL in lines[i]:
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i >= len(lines) or lines[i].startswith("#"):
                raise ValueError("Incomplete old newblog entry")
            i += 1
            continue
        kept.append(lines[i])
        i += 1
    lines = kept
    templates = replay_templates()
    if len(templates) != COUNT:
        raise ValueError("newblog catchup templates incomplete")
    for slug, meta, uri in get_source():
        cat = "グリーンCh" if slug == "green_channel" else meta["category"]
        # Group labels are a protected user-facing FreeWiFi setting.
        # A source refresh must never merge newblog back into PH/5002 groups.
        group_title = ("今日の開催場" if cat == "グリーンCh" else
                       f"{cat} newblog系" if cat in {"地上波", "BS", "CS", "その他"} else cat)
        if cat == "Rch":
            continue
        start = {"地上波":"## 地上波", "BS":"## BS",
                 "グリーンCh":"# === GREEN_CHANNEL_PERSISTENT_START ===",
                 "CS":"## CS", "その他":"## CS"}[cat]
        end = {"地上波":"## BS", "BS":"# === GREEN_CHANNEL_PERSISTENT_START ===",
               "グリーンCh":"# === GREEN_CHANNEL_PERSISTENT_END ==="}.get(cat)
        a = lines.index(start)
        b = lines.index(end) if end else len(lines)
        if b <= a:
            raise ValueError("Invalid section")
        matches = [j for j in range(a + 1, b)
                   if lines[j].startswith("#EXTINF:")
                   and ('tvg-id="' + meta["id"] + '"') in lines[j]]
        # Preserve the source order across hourly canonical rebuilds:
        # existing 5002/TVer -> newblog -> sinori.  A newblog refresh removes
        # its old row first, so inserting after the last same-id row would
        # otherwise move newblog behind the saved sinori backup.
        sinori = [j for j in matches
                  if "（sinori）" in lines[j].lower()
                  or re.search(r'group-title="[^"]* sinori"', lines[j])]
        # Keep YoiTV after newblog even when this script rebuilds the sources.
        yoitv = [j for j in matches if re.search(r'group-title="[^"]* YoiTV"', lines[j])]
        at = sinori[0] if sinori else (yoitv[0] if yoitv else (matches[-1] + 2 if matches else b))
        inf = ('#EXTINF:-1 tvg-id="' + meta["id"] + '" tvg-logo="'
               + meta["logo"] + '" group-title="' + group_title + '"'
               + catchup_attributes(slug, templates) + ','
               + meta["name"].replace(" (Arva)", "").replace("（Arva）", "") + LABEL)
        lines[at:at] = ["", inf, uri]
    result = re.sub(r"\n{4,}", "\n\n\n", "\n".join(lines)).rstrip() + "\n"
    if result.count(LABEL) != COUNT - 2:
        raise ValueError("newblog row count incorrect")
    if "haru.charandom.blog" in result or ":9394/stream/" in result:
        raise ValueError("Retired HARUKA returned")
    return replace_vod_block(result)

def inject_rch(body: str) -> str:
    raise RuntimeError('newblog Rch moved to yovi: use newblog/sync_yovi.py')
    """Place the 2 newblog Rch streams directly after their existing sources."""
    import re
    rows = {slug: (meta, uri) for slug, meta, uri in get_source()
            if slug in {"pigoo_nsfw", "nouvelle_paradise"}}
    if len(rows) != 2:
        raise ValueError("Missing newblog Rch records")
    templates = replay_templates()
    if len(templates) != COUNT:
        raise ValueError("newblog catchup templates incomplete")
    ls = body.splitlines()
    kept = []
    i = 0
    while i < len(ls):
        if ls[i].startswith("#EXTINF:") and LABEL in ls[i]:
            i += 1
            while i < len(ls) and not ls[i].strip():
                i += 1
            if i >= len(ls) or ls[i].startswith("#"):
                raise ValueError("Incomplete newblog Rch record")
            i += 1
            continue
        kept.append(ls[i])
        i += 1
    ls = kept
    for slug in ("pigoo_nsfw", "nouvelle_paradise"):
        meta, uri = rows[slug]
        matches = [j for j, line in enumerate(ls)
                   if line.startswith("#EXTINF:")
                   and ('tvg-id="' + meta["id"] + '"') in line]
        # Pigoo normally follows its YoiTV source. Nouvelle Paradise's
        # discontinued Arva source was removed, so its newblog row can
        # be appended without an existing same-id anchor.
        insert = matches[-1] + 2 if matches else len(ls)
        inf = ('#EXTINF:-1 tvg-id="' + meta["id"] + '" tvg-logo="'
               + meta["logo"] + '" group-title="Rch"'
               + catchup_attributes(slug, templates) + ','
               + meta["name"].replace(" (Arva)", "").replace("（Arva）", "") + LABEL)
        ls[insert:insert] = ["", inf, uri]
    return re.sub(r"\n{4,}", "\n\n\n", "\n".join(ls)).strip() + "\n\n"

def main():
    raise RuntimeError('Retired FreeWiFi importer. Run newblog/sync_yovi.py')
    current = TV.read_text(encoding="utf-8-sig")
    updated = apply(current)
    if current != updated:
        TV.write_text(updated, encoding="utf-8")
        print("newblog: restored all 101 sources into canonical TV")
    else:
        print("newblog: sources already current")

if __name__ == "__main__":
    main()
