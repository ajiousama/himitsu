from pathlib import Path
import re

FREEWIFI = Path('freewifi')
GROUP = 'グリーンCh'

# GCH viewing entries only. JRA EAST/WEST/HOKKAIDO remain in today's venue group.
GCH_IDS = {
    'グリーンチャンネル_jp',
    'jra.official',
    'jra.gch.free',
}
GCH_NAME_MARKERS = (
    'グリーンチャンネル',
    'グリーン チャンネル',
    'GCH無料版',
    'GCH Web',
    'GREEN CHANNEL',
)


def tvg_id(line: str) -> str:
    m = re.search(r'tvg-id="([^"]+)"', line)
    return m.group(1) if m else ''


def is_gch_entry(line: str) -> bool:
    if not line.startswith('#EXTINF:'):
        return False
    if tvg_id(line) in GCH_IDS:
        return True
    return any(marker.lower() in line.lower() for marker in GCH_NAME_MARKERS)


def set_group(line: str) -> str:
    if re.search(r'group-title="[^"]*"', line):
        return re.sub(r'group-title="[^"]*"', f'group-title="{GROUP}"', line, count=1)
    comma = line.find(',')
    if comma >= 0:
        return line[:comma] + f' group-title="{GROUP}"' + line[comma:]
    return line + f' group-title="{GROUP}"'


def main() -> None:
    if not FREEWIFI.exists():
        raise SystemExit('freewifi not found')

    lines = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace').splitlines()
    changed = 0
    matched = 0
    out = []
    for line in lines:
        if is_gch_entry(line):
            matched += 1
            new_line = set_group(line)
            if new_line != line:
                changed += 1
            line = new_line
        out.append(line)

    FREEWIFI.write_text('\n'.join(out).rstrip() + '\n', encoding='utf-8')
    print(f'Green Channel grouping normalized: matched={matched} changed={changed} group={GROUP}')


if __name__ == '__main__':
    main()
