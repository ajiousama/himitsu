from pathlib import Path
import re

FREEWIFI = Path('freewifi')
GENERAL = Path('general_youtube.m3u')
START = '# === JRA_OFFICIAL_YOUTUBE_START ==='
END = '# === JRA_OFFICIAL_YOUTUBE_END ==='
JRA_ID = 'jra.official'


def extract_jra_entry(text):
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith('#EXTINF:') and f'tvg-id="{JRA_ID}"' in line:
            if i + 1 < len(lines) and lines[i + 1].strip().startswith(('http://', 'https://')):
                return line.strip(), lines[i + 1].strip()
    return None


def remove_jra_from_managed(text):
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('#EXTINF:') and f'tvg-id="{JRA_ID}"' in line:
            i += 2
            if i < len(lines) and not lines[i].strip():
                i += 1
            continue
        out.append(line)
        i += 1
    return '\n'.join(out).rstrip() + '\n'


def main():
    if not FREEWIFI.exists():
        raise SystemExit('freewifi not found')

    base = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    general = GENERAL.read_text(encoding='utf-8-sig', errors='replace') if GENERAL.exists() else ''
    entry = extract_jra_entry(general)

    # Remove a previously managed JRA block first. If today's LIVE is absent,
    # the JRA item simply disappears instead of leaving an expired HLS URL.
    managed_pat = re.compile(re.escape(START) + r'.*?' + re.escape(END) + r'\n?', re.S)
    had_managed = bool(managed_pat.search(base))
    base = managed_pat.sub('', base)

    # The general YouTube managed area must not contain a duplicate JRA entry.
    base = remove_jra_from_managed(base)

    if entry:
        extinf, url = entry
        # Preserve the old FreeWiFi race-section position: replace the legacy
        # Green Channel free-version entry on the first successful JRA LIVE.
        legacy = re.compile(
            r'#EXTINF:[^\n]*グリーンチャンネル\(無料版\)[^\n]*\n[^\n]*\n?', re.M
        )
        block = f'{START}\n{extinf}\n{url}\n{END}\n'
        if legacy.search(base):
            base = legacy.sub(block, base, count=1)
        else:
            # After the first replacement, insert back into the race section.
            race_header = '## 競馬\n'
            if race_header in base:
                base = base.replace(race_header, race_header + '\n' + block, 1)
            else:
                base = base.rstrip() + '\n\n' + block
        print('JRA official YouTube LIVE installed in FreeWiFi race section')
    elif had_managed:
        print('JRA official YouTube is not LIVE; expired managed entry removed')
    else:
        print('JRA official YouTube is not LIVE yet; legacy free-version entry kept until first successful LIVE')

    FREEWIFI.write_text(base.rstrip() + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
