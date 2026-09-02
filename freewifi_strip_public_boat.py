from pathlib import Path
import re

FREEWIFI = Path('freewifi')
START = '# === TODAY_PUBLIC_SPORTS_START ==='
END = '# === TODAY_PUBLIC_SPORTS_END ==='


def strip_boat(body):
    lines = body.splitlines()
    out = []
    i = 0
    removed = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('#EXTINF:') and re.search(r'tvg-id="boat\.[^"]+"', line):
            removed += 1
            i += 1
            while i < len(lines) and not lines[i].startswith('#EXTINF:') and not lines[i].startswith('## ') and not lines[i].startswith('# ==='):
                i += 1
            continue
        out.append(line)
        i += 1
    return '\n'.join(out), removed


def main():
    if not FREEWIFI.exists():
        raise SystemExit('freewifi not found')
    text = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    m = re.search(re.escape(START) + r'(.*?)' + re.escape(END), text, re.S)
    if not m:
        print('No TODAY_PUBLIC_SPORTS block; BOAT V2 untouched')
        return 0
    body, removed = strip_boat(m.group(1))
    replacement = START + body + END
    if removed:
        text = text[:m.start()] + replacement + text[m.end():]
        FREEWIFI.write_text(text.rstrip() + '\n', encoding='utf-8')
    print(f'General FreeWiFi BOAT entries removed={removed}; BOAT V2 block preserved')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
