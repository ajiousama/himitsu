from pathlib import Path
import re

P = Path('freewifi')
BASE = 'http://ha-ipip.f5.si:9394'

text = P.read_text(encoding='utf-8-sig', errors='replace')
lines = text.splitlines()
out = []
i = 0
added = 0

while i < len(lines):
    line = lines[i]
    out.append(line)
    if line.startswith('#EXTINF:') and i + 1 < len(lines):
        url = lines[i + 1].strip()
        out.append(lines[i + 1])
        if '(ハルカ2)' in line and re.search(r'/stream/[^\s]+', url):
            m = re.search(r'(/stream/[^\s]+)', url)
            if m:
                meta, name = line.rsplit(',', 1)
                name = re.sub(r'\s*\(ハルカ2\)\s*$', '', name).strip()
                out.append(f'{meta},{name} (ハルカ3)')
                out.append(BASE + m.group(1))
                added += 1
        i += 2
        continue
    i += 1

updated = '\n'.join(out).rstrip() + '\n'
if added == 0:
    raise RuntimeError('HARUKA3: no HARUKA2 entries found')
P.write_text(updated, encoding='utf-8')
print('HARUKA3 added:', added)
