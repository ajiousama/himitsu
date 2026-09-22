from pathlib import Path
import re

M3U = Path(__file__).resolve().parent / 'public_sports.m3u'
RAW = 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main'
LOGO_BASE = RAW + '/public_sports_logos_github_43/jra_quality'

SERVICES = {
    'jra.gch': {
        'name': 'グリーンチャンネル',
        'hq_logo': 'gch_hq.png',
        'lq_logo': 'gch_lq.png',
    },
    'jra.east': {
        'name': 'JRA EAST',
        'hq_logo': 'east_hq.png',
        'lq_logo': 'east_lq.png',
    },
    'jra.west': {
        'name': 'JRA WEST',
        'hq_logo': 'west_hq.png',
        'lq_logo': 'west_lq.png',
    },
    'jra.hokkaido': {
        'name': 'JRA LOCAL',
        'output_base': 'jra.local',
        'hq_logo': 'local_hq.png',
        'lq_logo': 'local_lq.png',
    },
    'jra.local': {
        'name': 'JRA LOCAL',
        'output_base': 'jra.local',
        'hq_logo': 'local_hq.png',
        'lq_logo': 'local_lq.png',
    },
}


def set_attr(line, name, value):
    if re.search(rf'\b{re.escape(name)}="[^"]*"', line):
        return re.sub(
            rf'\b{re.escape(name)}="[^"]*"',
            f'{name}="{value}"',
            line,
            count=1,
        )
    marker = ' group-title='
    if marker in line:
        return line.replace(marker, f' {name}="{value}"{marker}', 1)
    comma = line.find(',')
    if comma >= 0:
        return line[:comma] + f' {name}="{value}"' + line[comma:]
    return line + f' {name}="{value}"'


def ext_id(line):
    m = re.search(r'tvg-id="([^"]+)"', line)
    return m.group(1) if m else ''


def main():
    if not M3U.exists():
        raise SystemExit('public_sports.m3u not found')

    text = M3U.read_text(encoding='utf-8-sig')
    lines = text.splitlines()
    changed = 0

    for i, line in enumerate(lines):
        if not line.startswith('#EXTINF:'):
            continue

        tid = ext_id(line)
        base = tid
        existing_quality = None
        if tid.endswith('.hq'):
            base = tid[:-3]
            existing_quality = 'hq'
        elif tid.endswith('.lq'):
            base = tid[:-3]
            existing_quality = 'lq'

        if base not in SERVICES:
            continue

        url = ''
        for j in range(i + 1, min(i + 4, len(lines))):
            if lines[j].strip() and not lines[j].startswith('#'):
                url = lines[j].strip()
                break

        quality = existing_quality or ('lq' if '_LQ' in url or '_lq' in url else 'hq')
        label = 'HQ' if quality == 'hq' else 'LQ'
        svc = SERVICES[base]
        logo = svc[f'{quality}_logo']

        new = line
        output_base = svc.get('output_base', base)
        new = set_attr(new, 'tvg-id', f'{output_base}.{quality}')
        new = set_attr(new, 'tvg-name', f"{svc['name']} {label}")
        new = set_attr(new, 'tvg-logo', f'{LOGO_BASE}/{logo}')

        comma = new.find(',')
        if comma >= 0:
            display = f"{svc['name']}（{'高画質' if quality == 'hq' else '低画質'}）"
            new = new[:comma + 1] + display

        if new != line:
            lines[i] = new
            changed += 1

    M3U.write_text('\n'.join(lines) + ('\n' if text.endswith('\n') else ''), encoding='utf-8')
    print(f'JRA M3U quality split complete: changed={changed}')


if __name__ == '__main__':
    main()
