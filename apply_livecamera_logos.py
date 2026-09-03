from pathlib import Path
import json
import re

SOURCES = [Path('general_youtube_sources_ports.json'), Path('general_youtube_sources_airports.json')]
TARGETS = [Path('general_youtube.m3u'), Path('freewifi')]


def logo_map():
    result = {}
    for p in SOURCES:
        if not p.exists():
            continue
        for item in json.loads(p.read_text(encoding='utf-8')):
            tvg = (item.get('id') or '').strip()
            logo = (item.get('logo') or '').strip()
            if tvg and logo:
                result[tvg] = logo
    return result


def patch_line(line, wanted):
    if not line.startswith('#EXTINF:'):
        return line, False
    m = re.search(r'tvg-id="([^"]+)"', line)
    if not m:
        return line, False
    logo = wanted.get(m.group(1))
    if not logo:
        return line, False

    old = line
    if re.search(r'tvg-logo="[^"]*"', line):
        line = re.sub(r'tvg-logo="[^"]*"', f'tvg-logo="{logo}"', line, count=1)
    elif ' group-title=' in line:
        line = line.replace(' group-title=', f' tvg-logo="{logo}" group-title=', 1)
    else:
        comma = line.find(',')
        if comma >= 0:
            line = line[:comma] + f' tvg-logo="{logo}"' + line[comma:]
    return line, line != old


def patch_file(path, wanted):
    if not path.exists():
        print('skip missing', path)
        return 0
    text = path.read_text(encoding='utf-8-sig', errors='replace')
    out = []
    changed = 0
    for line in text.splitlines():
        line, hit = patch_line(line, wanted)
        changed += int(hit)
        out.append(line)
    path.write_text('\n'.join(out).rstrip() + '\n', encoding='utf-8')
    print(path, 'logo lines changed:', changed)
    return changed


def main():
    wanted = logo_map()
    print('dedicated logo mappings:', len(wanted))
    for path in TARGETS:
        patch_file(path, wanted)


if __name__ == '__main__':
    main()
