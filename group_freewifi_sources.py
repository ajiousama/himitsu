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
    # Prefer 5002 direct as primary for every channel where it is registered.
    # Keep HARUKA as fallback; Naori test sources remain directly after HARUKA
    # for channels that lack 5002. This is a display preference, not a health claim.
    if "(5002直)" in lower:
        return 0
    if "(haruka" in lower or 'group-title="haruka bs"' in lower or 'group-title="haruka cs"' in lower:
        return 1
    if "(naori" in lower or 'group-title="naori bs"' in lower or 'group-title="naori cs"' in lower:
        return 2
    if "(primehomehd)" in lower:
        return 3
    if "(primehome)" in lower:
        return 4
    if "(jpnettv)" in lower:
        return 5
    if tvg_id(inf).startswith("tver_") or ",tver " in lower:
        return 6
    return 7


def rewrite_group_title(inf: str, group: str) -> str:
    if re.search(r'group-title="[^"]*"', inf):
        return re.sub(r'group-title="[^"]*"', f'group-title="{group}"', inf, count=1)
    return inf.replace(",", f' group-title="{group}",', 1)


def terrestrial_group_title(inf: str, url: str) -> str:
    lower = inf.lower()
    if "(haruka" in lower:
        return "地上波 haruka"
    if "(naori" in lower:
        return "地上波 naori"
    if "(primehomehd)" in lower:
        return "地上波 primehomeHD"
    if "(5002直)" in lower:
        return "地上波 5002直"
    if "(primehome)" in lower:
        return "地上波 primehome"
    if "(jpnettv)" in lower:
        return "地上波 jpnettv"
    if tvg_id(inf).startswith("tver_") or ",tver " in lower:
        return "地上波 TVer"
    return "地上波"


def normalize_terrestrial_entries(entries):
    # haru blog is retired. Strip any stale entries rather than reintroducing
    # them during automated source grouping.
    cleaned = [(inf, url, seq) for inf, url, seq in entries if not is_haru_blog(inf, url)]
    return [(rewrite_group_title(inf, terrestrial_group_title(inf, url)), url, seq)
            for inf, url, seq in cleaned]


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
    # player: 5002 -> HARUKA -> Naori -> primehomeHD -> primehome -> jpnettv -> TVer.
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


def validate_no_haru_blogs(text: str) -> None:
    entries = parse_entries(text)
    if any(is_haru_blog(inf, url) for inf, url, _seq in entries):
        raise RuntimeError("retired haru blog source found in FreeWiFi TV playlist")


def main() -> None:
    original = FREEWIFI.read_text(encoding="utf-8-sig", errors="strict")
    updated = normalize(original)

    validate_grouping(updated, "## 地上波\n", "## BS")
    validate_grouping(updated, "## BS\n", "# === GREEN_CHANNEL_PERSISTENT_START ===")
    validate_grouping(updated, "# === GREEN_CHANNEL_PERSISTENT_START ===\n", "# === GREEN_CHANNEL_PERSISTENT_END ===")
    validate_grouping(updated, "## CS\n", None)
    validate_no_haru_blogs(updated)

    if updated != original:
        FREEWIFI.write_text(updated, encoding="utf-8")
        print("Normalized TV order: 5002 -> HARUKA -> Naori -> primehomeHD -> primehome -> jpnettv -> TVer")
    else:
        print("TV playlist per-channel source order already normalized")


if __name__ == "__main__":
    main()
