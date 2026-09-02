from pathlib import Path
import re

PATH = Path('ganble')
LOCAL_EPG = 'https://raw.githubusercontent.com/ajiousama/himitsu/main/guides.xml'
EARPHONE = re.compile(r'https://raw\.githubusercontent\.com/earphone1981/public-sports-iptv/[^"\s]+', re.I)


def main():
    if not PATH.exists():
        raise SystemExit('ganble missing')
    text = PATH.read_text(encoding='utf-8-sig', errors='replace')
    lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    if lines and lines[0].startswith('#EXTM3U'):
        if 'url-tvg=' in lines[0]:
            lines[0] = re.sub(r'url-tvg="[^"]*"', f'url-tvg="{LOCAL_EPG}"', lines[0], count=1)
        else:
            lines[0] += f' url-tvg="{LOCAL_EPG}"'
    else:
        lines.insert(0, f'#EXTM3U url-tvg="{LOCAL_EPG}"')

    out = []
    removed_logos = 0
    for line in lines:
        if line.startswith('#EXTINF:') and 'tvg-logo=' in line and 'earphone1981/public-sports-iptv' in line:
            line2 = re.sub(r'\s+tvg-logo="[^"]*earphone1981/public-sports-iptv[^"]*"', '', line, flags=re.I)
            if line2 != line:
                removed_logos += 1
                line = line2
        # A bare earphone raw URL is never a valid stream entry in this master;
        # remove it instead of leaving an external runtime dependency.
        if not line.startswith('#') and EARPHONE.search(line):
            continue
        out.append(line)

    normalized = '\n'.join(out).rstrip() + '\n'
    PATH.write_text(normalized, encoding='utf-8')
    leftovers = [x for x in normalized.splitlines() if 'earphone1981/public-sports-iptv' in x]
    if leftovers:
        raise SystemExit(f'ganble still has {len(leftovers)} earphone references')
    print(f'ganble normalized: local EPG, removed external logos={removed_logos}')


if __name__ == '__main__':
    main()
