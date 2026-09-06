from pathlib import Path
import re

FREEWIFI = Path("freewifi")

REGIONS = {"関東", "関西", "BS", "CS"}
HARUKA2_HOST = "haruka-ipip.f5.si:9394/"
AKARIKO_HOST = "haru.charandom.blog/stream/jp/"

GROUP_RE = re.compile(r'group-title="([^"]+)"')


def base_region(group: str) -> str | None:
    candidates = [
        group,
        group.removeprefix("akariko"),
        group.removeprefix("haruka2 "),
        group.removeprefix("haruka2"),
    ]
    for candidate in candidates:
        candidate = candidate.strip()
        if candidate in REGIONS:
            return candidate
    return None


def replace_group(line: str, target: str) -> str:
    if GROUP_RE.search(line):
        return GROUP_RE.sub(f'group-title="{target}"', line, count=1)
    return line


def main() -> None:
    text = FREEWIFI.read_text(encoding="utf-8-sig", errors="strict")
    if not text.startswith("#EXTM3U"):
        raise RuntimeError("freewifi header missing")

    lines = text.splitlines()
    changed = {"akariko": 0, "haruka2": 0}
    seen = {"akariko": 0, "haruka2": 0}

    for i, line in enumerate(lines):
        if not line.startswith("#EXTINF:"):
            continue

        next_line = lines[i + 1].strip() if i + 1 < len(lines) else ""
        m = GROUP_RE.search(line)
        if not m:
            continue

        region = base_region(m.group(1))
        if region is None:
            continue

        lower = line.lower()
        is_akariko = "(akariko)" in lower or AKARIKO_HOST in next_line
        is_haruka2 = "(ハルカ2)" in line or HARUKA2_HOST in next_line

        if is_akariko:
            seen["akariko"] += 1
            target = f"akariko{region}"
            new_line = replace_group(line, target)
            if new_line != line:
                lines[i] = new_line
                changed["akariko"] += 1
            continue

        if is_haruka2:
            seen["haruka2"] += 1
            target = f"haruka2 {region}"
            new_line = replace_group(line, target)
            if new_line != line:
                lines[i] = new_line
                changed["haruka2"] += 1

    if seen["akariko"] == 0:
        raise RuntimeError("no Akariko entries found")
    if seen["haruka2"] == 0:
        raise RuntimeError("no Haruka2 entries found")

    out = "\n".join(lines).rstrip() + "\n"
    FREEWIFI.write_text(out, encoding="utf-8")

    print(
        "Grouped FreeWiFi sources: "
        f"akariko seen={seen['akariko']} changed={changed['akariko']}; "
        f"haruka2 seen={seen['haruka2']} changed={changed['haruka2']}"
    )


if __name__ == "__main__":
    main()
