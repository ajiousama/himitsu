from pathlib import Path
import re

FREEWIFI = Path("freewifi")

REGIONS = {"関東", "関西", "BS", "CS"}
AKARIKO_HOST = "haru.charandom.blog/stream/jp/"
HARUKA_HOSTS = {
    "haruka1": "haruka-ip.f5.si:9394/",
    "haruka2": "haruka-ipip.f5.si:9394/",
    "haruka3": "ha-ipip.f5.si:9394/",
}
HARUKA_LABELS = {
    "haruka1": "(ハルカ1)",
    "haruka2": "(ハルカ2)",
    "haruka3": "(ハルカ3)",
}

GROUP_RE = re.compile(r'group-title="([^"]+)"')


def base_region(group: str) -> str | None:
    candidates = [group, group.removeprefix("akariko")]
    for source in HARUKA_HOSTS:
        candidates.append(group.removeprefix(f"{source} "))
        candidates.append(group.removeprefix(source))

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
    sources = ["akariko", *HARUKA_HOSTS]
    changed = {source: 0 for source in sources}
    seen = {source: 0 for source in sources}

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
        if "(akariko)" in lower or AKARIKO_HOST in next_line:
            seen["akariko"] += 1
            target = f"akariko{region}"
            new_line = replace_group(line, target)
            if new_line != line:
                lines[i] = new_line
                changed["akariko"] += 1
            continue

        for source, host in HARUKA_HOSTS.items():
            if HARUKA_LABELS[source] in line or host in next_line:
                seen[source] += 1
                target = f"{source} {region}"
                new_line = replace_group(line, target)
                if new_line != line:
                    lines[i] = new_line
                    changed[source] += 1
                break

    for source in sources:
        if seen[source] == 0:
            raise RuntimeError(f"no {source} entries found")

    out = "\n".join(lines).rstrip() + "\n"
    FREEWIFI.write_text(out, encoding="utf-8")

    summary = "; ".join(
        f"{source} seen={seen[source]} changed={changed[source]}"
        for source in sources
    )
    print(f"Grouped FreeWiFi sources: {summary}")


if __name__ == "__main__":
    main()
