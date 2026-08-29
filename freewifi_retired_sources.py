from pathlib import Path

FREEWIFI = Path('freewifi')
RETIRED_MARKERS = (
    'akariko-bck1.sankuria.sbs',
    'akariko backup',
)


def main():
    text = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    lines = text.splitlines()
    out = []
    removed = 0
    i = 0
    while i < len(lines):
        if lines[i].startswith('#EXTINF:'):
            j = i + 1
            while j < len(lines) and not lines[j].startswith('#EXTINF:') and not lines[j].startswith('## ') and not lines[j].startswith('### ') and not lines[j].startswith('# ==='):
                j += 1
            block = lines[i:j]
            low = '\n'.join(block).lower()
            if any(marker in low for marker in RETIRED_MARKERS):
                removed += 1
                i = j
                continue
            out.extend(block)
            i = j
            continue
        out.append(lines[i])
        i += 1

    result = '\n'.join(out).rstrip() + '\n'
    FREEWIFI.write_text(result, encoding='utf-8')
    print(f'Retired Akariko sub entries removed: {removed}')


if __name__ == '__main__':
    main()
