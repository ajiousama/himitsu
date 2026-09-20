from pathlib import Path
import json
import re

RAW = 'https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/youtube/'
SOURCES = [
    Path('general_youtube_sources.json'),
    Path('general_youtube_sources_ports.json'),
    Path('general_youtube_sources_airports.json'),
]
TARGETS = [Path('general_youtube.m3u'), Path('freewifi')]
SKIP_IDS = {'jra.official', 'youtube.narita_t1', 'youtube.kobe_waterfront2'}


def safe_slug(cid):
    slug = cid.split('.', 1)[-1]
    slug = re.sub(r'[^a-zA-Z0-9_]+', '_', slug).strip('_')
    return slug or 'youtube'


def canonical():
    rows = []
    for path in SOURCES:
        if not path.exists():
            continue
        for item in json.loads(path.read_text(encoding='utf-8')):
            cid = str(item.get('id') or '').strip()
            if not cid or cid in SKIP_IDS or not item.get('enabled', True):
                continue
            rows.append(item)
    return {
        str(item['id']): RAW + f"yt43_{idx:02d}_{safe_slug(str(item['id']))}_illustration.png"
        for idx, item in enumerate(rows, start=1)
    }


def patch_sources(wanted):
    total = 0
    for path in SOURCES:
        if not path.exists():
            continue
        items = json.loads(path.read_text(encoding='utf-8'))
        changed = 0
        for item in items:
            cid = str(item.get('id') or '').strip()
            logo = wanted.get(cid)
            if logo and item.get('logo') != logo:
                item['logo'] = logo
                changed += 1
        if changed:
            path.write_text(json.dumps(items, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(path, 'source logos changed:', changed)
        total += changed
    return total


def patch_file(path, wanted):
    if not path.exists():
        return 0
    text = path.read_text(encoding='utf-8-sig', errors='replace')
    out = []
    changed = 0
    for line in text.splitlines():
        old = line
        if line.startswith('#EXTINF:'):
            m = re.search(r'tvg-id="([^"]+)"', line)
            if m and m.group(1) in wanted:
                logo = wanted[m.group(1)]
                if re.search(r'tvg-logo="[^"]*"', line):
                    line = re.sub(r'tvg-logo="[^"]*"', f'tvg-logo="{logo}"', line, count=1)
                elif ' group-title=' in line:
                    line = line.replace(' group-title=', f' tvg-logo="{logo}" group-title=', 1)
        changed += int(line != old)
        out.append(line)
    path.write_text('\n'.join(out).rstrip() + '\n', encoding='utf-8')
    print(path, 'playlist logo lines changed:', changed)
    return changed


def verify(path, wanted):
    if not path.exists():
        return
    bad = []
    seen = 0
    for line in path.read_text(encoding='utf-8-sig', errors='replace').splitlines():
        if not line.startswith('#EXTINF:'):
            continue
        m = re.search(r'tvg-id="([^"]+)"', line)
        if not m or m.group(1) not in wanted:
            continue
        seen += 1
        if f'tvg-logo="{wanted[m.group(1)]}"' not in line:
            bad.append(m.group(1))
    if bad:
        raise SystemExit(f'{path}: wrong canonical logo mapping: {bad}')
    print(path, 'canonical mappings verified:', seen)


def main():
    wanted = canonical()
    if len(wanted) != 70:
        raise SystemExit(f'expected 70 canonical YouTube logos, got {len(wanted)}')
    print('canonical YouTube mappings:', len(wanted))
    patch_sources(wanted)
    for path in TARGETS:
        patch_file(path, wanted)
        verify(path, wanted)


if __name__ == '__main__':
    main()
