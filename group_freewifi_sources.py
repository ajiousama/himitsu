from __future__ import annotations

from pathlib import Path

FREEWIFI = Path("freewifi")


def parse_entries(body: str):
    lines = body.splitlines()
    entries = []
    i = 0
    seq = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("#EXTINF:"):
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines) and not lines[j].lstrip().startswith("#"):
                entries.append((line, lines[j].strip(), seq))
                seq += 1
                i = j + 1
                continue
        i += 1
    return entries


def source_rank(inf: str) -> int:
    lower = inf.lower()
    if "(haruka" in lower or 'group-title="haruka bs"' in lower or 'group-title="haruka cs"' in lower:
        return 0
    if ",tver " in lower:
        return 1
    if "(primehomehd)" in lower:
        return 2
    if "(primehome)" in lower:
        return 3
    return 1


def sorted_entries(body: str) -> list[tuple[str, str, int]]:
    return sorted(parse_entries(body), key=lambda row: (source_rank(row[0]), row[2]))


def render(entries) -> str:
    return "\n\n".join(f"{inf}\n{url}" for inf, url, _seq in entries) + "\n\n"


def replace_sorted(text: str, start: str, end: str, prefix: str = "") -> str:
    a = text.index(start) + len(start)
    b = text.index(end, a)
    body = prefix + render(sorted_entries(text[a:b]))
    return text[:a] + body + text[b:]


def validate_order(text: str, start: str, end: str) -> None:
    a = text.index(start) + len(start)
    b = text.index(end, a)
    ranks = [source_rank(inf) for inf, _url, _seq in parse_entries(text[a:b])]
    if ranks != sorted(ranks):
        raise RuntimeError(f"source order invalid between {start!r} and {end!r}: {ranks}")


def normalize(text: str) -> str:
    # Source order is intentionally identical in terrestrial, BS and CS:
    # haruka -> neutral/TVer -> primehomeHD -> primehome.
    # This script never creates stream URLs, so dead legacy sources cannot
    # return merely because the normalizer ran.
    text = replace_sorted(text, "## 地上波\n", "## BS")
    text = replace_sorted(text, "## BS\n", "# === PRIMEHOME_EXTRA_BS_START ===")

    gs = "# === GREEN_CHANNEL_PERSISTENT_START ===\n"
    ge = "# === GREEN_CHANNEL_PERSISTENT_END ==="
    a = text.index(gs) + len(gs)
    b = text.index(ge, a)
    text = text[:a] + "## グリーンCh\n\n" + render(sorted_entries(text[a:b])) + text[b:]

    text = replace_sorted(text, "## CS\n", "# === PRIMEHOME_EXTRA_CS_END ===")
    while "\n\n\n\n" in text:
        text = text.replace("\n\n\n\n", "\n\n\n")
    return text.rstrip() + "\n"


def main() -> None:
    original = FREEWIFI.read_text(encoding="utf-8-sig", errors="strict")
    updated = normalize(original)

    validate_order(updated, "## 地上波\n", "## BS")
    validate_order(updated, "## BS\n", "# === PRIMEHOME_EXTRA_BS_START ===")
    validate_order(updated, "# === GREEN_CHANNEL_PERSISTENT_START ===\n", "# === GREEN_CHANNEL_PERSISTENT_END ===")
    validate_order(updated, "## CS\n", "# === PRIMEHOME_EXTRA_CS_END ===")

    if "(blog)" in updated or "haru.charandom.blog" in updated:
        raise RuntimeError("legacy blog source returned to FreeWiFi")

    if updated != original:
        FREEWIFI.write_text(updated, encoding="utf-8")
        print("Normalized FreeWiFi source order: haruka -> TVer/other -> primehomeHD -> primehome")
    else:
        print("FreeWiFi source order already normalized")


if __name__ == "__main__":
    main()
