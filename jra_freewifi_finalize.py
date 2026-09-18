from pathlib import Path
import re

FREEWIFI = Path('freewifi')
LEGACY_IDS = {'jra.official', 'jra.gch.free'}
LEGACY_BLOCKS = (
    ('# === JRA_OFFICIAL_YOUTUBE_START ===', '# === JRA_OFFICIAL_YOUTUBE_END ==='),
    ('# === JRA_GCH_FREE_A_START ===', '# === JRA_GCH_FREE_A_END ==='),
    ('# === JRA_GCH_FREE_B_START ===', '# === JRA_GCH_FREE_B_END ==='),
    ('# === JRA_GCH_FREE_START ===', '# === JRA_GCH_FREE_END ==='),
)


def strip_legacy(text: str) -> str:
    for start, end in LEGACY_BLOCKS:
        text = re.sub(re.escape(start) + r'.*?' + re.escape(end) + r'\n?', '', text, flags=re.S)
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.search(r'tvg-id="([^"]+)"', line) if line.startswith('#EXTINF:') else None
        if m and m.group(1) in LEGACY_IDS:
            i += 1
            while i < len(lines) and not lines[i].startswith(('#EXTINF:', '## ', '# ===')):
                i += 1
            continue
        out.append(line)
        i += 1
    return '\n'.join(out).rstrip() + '\n'



def main():
    if not FREEWIFI.exists():
        raise SystemExit('freewifi not found')
    text = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    FREEWIFI.write_text(strip_legacy(text), encoding='utf-8')
    print('Legacy JRA free A/B entries removed; earphone HQ/LQ set is canonical')


if __name__ == '__main__':
    main()
