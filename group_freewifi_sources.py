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
    if tvg_id(inf).startswith("tver_") or ",tver " in lower:
        return 4
    return 5


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


def replace_section(text: str, start: str, end: str | None, prefix: str = "") -> str:
    a = text.index(start) + len(start)
    b = text.index(end, a) if end is not None else len(text)
    entries = group_by_channel(parse_entries(text[a:b]))
    return text[:a] + "\n" + prefix + render(entries) + text[b:]


def normalize(text: str) -> str:
    # Every TV section is channel-first, then source-first inside that channel:
    # haruka -> primehomeHD -> primehome -> TVer/other.
    # No stream URL is generated here; existing URLs and logos are preserved.
    text = replace_section(text, "## 地上波\n", "## BS")
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


def main() -> None:
    original = FREEWIFI.read_text(encoding="utf-8-sig", errors="strict")
    updated = normalize(original)

    validate_grouping(updated, "## 地上波\n", "## BS")
    validate_grouping(updated, "## BS\n", "# === GREEN_CHANNEL_PERSISTENT_START ===")
    validate_grouping(updated, "# === GREEN_CHANNEL_PERSISTENT_START ===\n", "# === GREEN_CHANNEL_PERSISTENT_END ===")
    validate_grouping(updated, "## CS\n", None)

    if "haru.charandom.blog" in updated or "(blog)" in updated:
        raise RuntimeError("legacy blog source returned to TV playlist")

    if updated != original:
        FREEWIFI.write_text(updated, encoding="utf-8")
        print("Normalized TV order per channel: haruka -> primehomeHD -> primehome -> TVer/other")
    else:
        print("TV playlist per-channel source order already normalized")


if __name__ == "__main__":
    main()
