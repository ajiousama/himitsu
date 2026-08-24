from pathlib import Path
from datetime import datetime, timezone, timedelta
import re
import urllib.request
import xml.etree.ElementTree as ET

FREEWIFI = Path('freewifi')
PUBLIC_M3U_URL = 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/public_sports.m3u'
PUBLIC_EPG_URL = 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/epg.xml'
START = '# === TODAY_PUBLIC_SPORTS_START ==='
END = '# === TODAY_PUBLIC_SPORTS_END ==='
JST = timezone(timedelta(hours=9))
NON_EVENT_WORDS = ('本日非開催', '非開催', '開催していません', '開催予定はありません', '開催なし', '次回開催', '準備中', '休止')


def fetch_text(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (FreeWiFi keirin repair)'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8-sig', errors='replace')


def parse_time(s):
    m = re.match(r'^(\d{14})\s*([+-]\d{4})?', (s or '').strip())
    if not m:
        return None
    dt = datetime.strptime(m.group(1), '%Y%m%d%H%M%S')
    off = m.group(2)
    if off:
        sign = 1 if off[0] == '+' else -1
        tz = timezone(sign * timedelta(hours=int(off[1:3]), minutes=int(off[3:5])))
        return dt.replace(tzinfo=tz)
    return dt.replace(tzinfo=JST)


def active_keirin_ids(epg_text):
    today = datetime.now(JST).date()
    root = ET.fromstring(epg_text)
    ids = set()
    for p in root.findall('programme'):
        cid = p.get('channel') or ''
        if not cid.startswith('keirin.'):
            continue
        start = parse_time(p.get('start'))
        if not start or start.astimezone(JST).date() != today:
            continue
        title = (p.findtext('title') or '').strip()
        if title and not any(w in title for w in NON_EVENT_WORDS):
            ids.add(cid)
    return ids


def keirin_blocks(m3u_text, wanted):
    blocks = []
    section = ''
    lines = m3u_text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('## '):
            section = line[3:].strip()
            i += 1
            continue
        if line.startswith('#EXTINF:'):
            block = [line]
            j = i + 1
            while j < len(lines) and not lines[j].startswith('#EXTINF:') and not lines[j].startswith('## '):
                if lines[j].strip():
                    block.append(lines[j])
                j += 1
            m = re.search(r'tvg-id="([^"]+)"', line)
            if section == '競輪' and m and m.group(1) in wanted:
                block[0] = re.sub(r'group-title="[^"]*"', 'group-title="今日の開催場"', block[0])
                blocks.append((m.group(1), block))
            i = j
            continue
        i += 1
    return blocks


def main():
    text = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    m = re.search(re.escape(START) + r'(.*?)' + re.escape(END), text, re.S)
    if not m:
        print('Keirin repair skipped: managed block not found')
        return

    active = active_keirin_ids(fetch_text(PUBLIC_EPG_URL))
    blocks = keirin_blocks(fetch_text(PUBLIC_M3U_URL), active)
    body = m.group(1)

    # Remove stale keirin entries from the managed block first.
    body_lines = body.splitlines()
    out = []
    i = 0
    while i < len(body_lines):
        line = body_lines[i]
        if line.startswith('#EXTINF:') and 'tvg-id="keirin.' in line:
            i += 1
            while i < len(body_lines) and not body_lines[i].startswith('#EXTINF:'):
                i += 1
            continue
        out.append(line)
        i += 1

    cleaned = '\n'.join(out).rstrip()
    add = []
    for _, block in blocks:
        add.extend(block)
        add.append('')
    repaired = cleaned + ('\n' if cleaned else '') + '\n'.join(add).rstrip() + ('\n' if add else '')
    new_block = START + repaired + END
    text = text[:m.start()] + new_block + text[m.end():]
    FREEWIFI.write_text(text.rstrip() + '\n', encoding='utf-8')
    print(f'Keirin fallback repaired: {len(blocks)} venues')


if __name__ == '__main__':
    main()
