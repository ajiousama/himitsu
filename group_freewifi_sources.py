from __future__ import annotations

from collections import OrderedDict
from pathlib import Path
import re

FREEWIFI = Path("tv/playlist.m3u")

TVER_PARENT = {
    "tver_tbs": "TBS_jp",
    "tver_ex": "テレビ朝日_jp",
    "tver_tx": "テレ東_jp",
    "tver_cx": "フジテレビ_jp",
    "tver_ntv": "日本テレビ_jp",
}

ABC_ID = "ABCテレビ_jp"
ABC_BLOG_URL = "https://haru.charandom.blog/stream/jp/abc/stream-output.m3u8?mode=hls"
ABC_BLOG_NAME = "ABCテレビ (haru blog)"


def parse_entries(body: str):
    lines = body.splitlines()
    result = []
    i = 0
    seq = 0
    while i < len(lines):
        inf = lines[i]
        if inf.startswith("#EXTINF:"):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and not lines[j].lstrip().startswith("#"):
                result.append((inf, lines[j].strip(), seq))
                seq += 1
                i = j + 1
                continue
        i += 1
    return result


def tvg_id(inf: str) -> str:
    match = re.search(r'tvg-id="([^"]+)"', inf)
    return match.group(1) if match else ""


def logical_channel(inf: str, seq: int) -> str:
    channel_id = tvg_id(inf)
    return TVER_PARENT.get(channel_id, channel_id or f"__entry_{seq}")


def is_haru_blog(inf: str, url: str = "") -> bool:
    lower = inf.lower()
    return (
        "haru.charandom.blog" in url.lower()
        or "(haru blog)" in lower
        or "(blog)" in lower
    )


def source_rank(inf: str) -> int:
    lower = inf.lower()
    if "(haruka" in lower or 'group-title="haruka bs"' in lower or 'group-title="haruka cs"' in lower:
        return 0
    if "(primehomehd)" in lower:
        return 1
    if "(5002直)" in lower:
        return 2
    if "(primehome)" in lower:
        return 3
    if "(haru blog)" in lower or "(blog)" in lower:
        return 4
    if tvg_id(inf).startswith("tver_") or ",tver " in lower:
        return 5
    return 6


def rewrite_group_title(inf: str, group: str) -> str:
    if re.search(r'group-title="[^"]*"', inf):
        return re.sub(r'group-title="[^"]*"', f'group-title="{group}"', inf, count=1)
    return inf.replace(",", f' group-title="{group}",', 1)


def terrestrial_group_title(inf: str, url: str) -> str:
    lower = inf.lower()
    if "(haruka" in lower:
        return "地上波 haruka"
    if "(primehomehd)" in lower:
        return "地上波 primehomeHD"
    if "(5002直)" in lower:
        return "地上波 5002直"
    if "(primehome)" in lower:
        return "地上波 primehome"
    if is_haru_blog(inf, url):
        return "地上波 haru blog"
    if tvg_id(inf).startswith("tver_") or ",tver " in lower:
        return "地上波 TVer"
    return "地上波"


def normalize_terrestrial_entries(entries):
    # haru blog is intentionally retained for ABC only.  Remove every legacy
    # blog row first, then recreate exactly one canonical ABC row so later
    # automatic syncs cannot silently drop it or resurrect other Kansai rows.
    template = next((inf for inf, _url, _seq in entries if tvg_id(inf) == ABC_ID), None)
    if template is None:
        raise RuntimeError("ABC source missing from terrestrial playlist")

    cleaned = [
        (inf, url, seq)
        for inf, url, seq in entries
        if not is_haru_blog(inf, url)
    ]

    next_seq = max((seq for _inf, _url, seq in cleaned), default=-1) + 1
    blog_inf = template.rsplit(",", 1)[0] + "," + ABC_BLOG_NAME
    cleaned.append((blog_inf, ABC_BLOG_URL, next_seq))

    relabelled = []
    for inf, url, seq in cleaned:
        group = terrestrial_group_title(inf, url)
        relabelled.append((rewrite_group_title(inf, group), url, seq))
    return relabelled


def group_by_channel(entries):
    groups = OrderedDict()
    for inf, url, seq in entries:
        groups.setdefault(logical_channel(inf, seq), []).append((inf, url, seq))
    out = []
    for rows in groups.values():
        rows.sort(key=lambda row: (source_rank(row[0]), row[2]))
        out.extend(rows)
    return out


def render(entries) -> str:
    return "\n\n".join(f"{inf}\n{url}" for inf, url, _seq in entries) + "\n\n"


def replace_section(text: str, start: str, end: str | None, prefix: str = "", terrestrial: bool = False) -> str:
    a = text.index(start) + len(start)
    b = text.index(end, a) if end is not None else len(text)
    entries = parse_entries(text[a:b])
    if terrestrial:
        entries = normalize_terrestrial_entries(entries)
    entries = group_by_channel(entries)
    return text[:a] + "\n" + prefix + render(entries) + text[b:]


def normalize(text: str) -> str:
    # Terrestrial channels are channel-first, with source groups exposed in the
    # player: haruka -> primehomeHD -> 5002 -> primehome -> haru blog -> TVer.
    text = replace_section(text, "## 地上波\n", "## BS", terrestrial=True)
    text = replace_section(text, "## BS\n", "# === GREEN_CHANNEL_PERSISTENT_START ===")

    gs = "# === GREEN_CHANNEL_PERSISTENT_START ===\n"
    ge = "# === GREEN_CHANNEL_PERSISTENT_END ==="
    a = text.index(gs) + len(gs)
    b = text.index(ge, a)
    text = text[:a] + "## グリーンCh\n\n" + render(group_by_channel(parse_entries(text[a:b]))) + text[b:]

    text = replace_section(text, "## CS\n", None)

    while "\n\n\n\n" in text:
        text = text.replace("\n\n\n\n", "\n\n\n")
    return text.rstrip() + "\n"


def validate_grouping(text: str, start: str, end: str | None) -> None:
    a = text.index(start) + len(start)
    b = text.index(end, a) if end is not None else len(text)
    entries = parse_entries(text[a:b])

    seen = set()
    current = None
    current_ranks = []
    for inf, _url, seq in entries:
        key = logical_channel(inf, seq)
        if key != current:
            if current is not None:
                if current in seen:
                    raise RuntimeError(f"channel group split: {current}")
                if current_ranks != sorted(current_ranks):
                    raise RuntimeError(f"source order invalid for {current}: {current_ranks}")
                seen.add(current)
            current = key
            current_ranks = []
        current_ranks.append(source_rank(inf))
    if current is not None:
        if current in seen:
            raise RuntimeError(f"channel group split: {current}")
        if current_ranks != sorted(current_ranks):
            raise RuntimeError(f"source order invalid for {current}: {current_ranks}")


def validate_abc_blog(text: str) -> None:
    a = text.index("## 地上波\n") + len("## 地上波\n")
    b = text.index("## BS", a)
    entries = parse_entries(text[a:b])
    blogs = [(inf, url) for inf, url, _seq in entries if is_haru_blog(inf, url)]
    if len(blogs) != 1:
        raise RuntimeError(f"expected exactly one haru blog source, found {len(blogs)}")
    inf, url = blogs[0]
    if tvg_id(inf) != ABC_ID or url != ABC_BLOG_URL or ABC_BLOG_NAME not in inf:
        raise RuntimeError(f"unexpected haru blog source: {inf} {url}")
    if 'group-title="地上波 haru blog"' not in inf:
        raise RuntimeError("ABC haru blog source group label missing")


def main() -> None:
    original = FREEWIFI.read_text(encoding="utf-8-sig", errors="strict")
    updated = normalize(original)

    validate_grouping(updated, "## 地上波\n", "## BS")
    validate_grouping(updated, "## BS\n", "# === GREEN_CHANNEL_PERSISTENT_START ===")
    validate_grouping(updated, "# === GREEN_CHANNEL_PERSISTENT_START ===\n", "# === GREEN_CHANNEL_PERSISTENT_END ===")
    validate_grouping(updated, "## CS\n", None)
    validate_abc_blog(updated)

    if updated != original:
        FREEWIFI.write_text(updated, encoding="utf-8")
        print("Normalized TV order: haruka -> primehomeHD -> 5002 -> primehome -> haru blog -> TVer")
    else:
        print("TV playlist per-channel source order already normalized")


if __name__ == "__main__":
    main()
