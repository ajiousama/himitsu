from pathlib import Path
from datetime import datetime, timezone, timedelta
from urllib.parse import quote
import json
import re
import urllib.request
import xml.etree.ElementTree as ET

FREEWIFI = Path('freewifi')
STATUS_JSON = Path('today_jra_status.json')
PUBLIC_EPG_URL = 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/epg.xml'
RAW_BASE = 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main'
START = '# === TODAY_JRA_START ==='
END = '# === TODAY_JRA_END ==='
GROUP = 'グリーンCh'
JST = timezone(timedelta(hours=9))
SOURCE_IDS = ('jra.east', 'jra.west', 'jra.hokkaido')
LABELS = {'jra.east':'EAST', 'jra.west':'WEST', 'jra.hokkaido':'LOCAL/第三場'}
NON_EVENT_WORDS = (
    '非開催', '休止', '準備中', 'データ取得準備中',
    '開催情報確認待ち', '確認待ち', '開催・非開催をまだ確定していません',
    '本日の全レースは終了しました',
)
RACE_TITLE_RE = re.compile(r'(?:【\s*\d+\s*[ＲR]\s*】|(?<!\d)\d+\s*[ＲR](?!\w))', re.I)

# The custom-logo central-racing set created for public-sports-iptv.
# GCH is shown whenever at least one JRA regional feed is active.
# EAST / WEST / HOKKAIDO are each shown only when that feed is active.
JRA_ROUTES = {
    'jra.gch': [
        ('グリーンチャンネル（高画質）', 'gchmain.m3u8', 'gch.png'),
        ('グリーンチャンネル（低画質）', 'gchmain_LQ.m3u8', 'gch.png'),
    ],
    'jra.east': [
        ('JRA EAST（高画質）', 'EAST_test.m3u8', 'east_web3.png'),
        ('JRA EAST（低画質）', 'EAST_test_LQ.m3u8', 'east_web3.png'),
    ],
    'jra.west': [
        ('JRA WEST（高画質）', 'WEST_master .m3u8', 'west_web4.png'),
        ('JRA WEST（低画質）', 'WEST_master_LQ.m3u8', 'west_web4.png'),
    ],
    'jra.hokkaido': [
        ('JRA HOKKAIDO（高画質）', 'hokaido_master (1).m3u8', 'hokkaido_local.png'),
        ('JRA HOKKAIDO（低画質）', 'hokaido_master_LQ.m3u8', 'hokkaido_local.png'),
    ],
}
TVG_NAMES = {
    'jra.gch': 'グリーンチャンネル',
    'jra.east': 'JRA EAST',
    'jra.west': 'JRA WEST',
    'jra.hokkaido': 'JRA HOKKAIDO',
}


def fetch_text(url, timeout=60):
    req = urllib.request.Request(url, headers={'User-Agent': 'FreeWiFi-JRA-Daily/2.0', 'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8-sig', errors='replace')


def raw_url(filename):
    return f'{RAW_BASE}/{quote(filename)}'


def parse_xmltv_time(s):
    if not s:
        return None
    m = re.match(r'^(\d{14})\s*([+-]\d{4})?', s.strip())
    if not m:
        return None
    base = datetime.strptime(m.group(1), '%Y%m%d%H%M%S')
    off = m.group(2)
    if off:
        sign = 1 if off[0] == '+' else -1
        tz = timezone(sign * timedelta(hours=int(off[1:3]), minutes=int(off[3:5])))
        return base.replace(tzinfo=tz)
    return base.replace(tzinfo=JST)


def rewrite_group(extinf):
    if 'group-title=' in extinf:
        return re.sub(r'group-title="[^"]*"', f'group-title="{GROUP}"', extinf, count=1)
    comma = extinf.find(',')
    return extinf[:comma] + f' group-title="{GROUP}"' + extinf[comma:] if comma >= 0 else extinf + f' group-title="{GROUP}"'


def is_real_jra_program(title, desc):
    joined = f'{title} {desc}'
    if not title or any(w in joined for w in NON_EVENT_WORDS):
        return False
    if 'JRA中央競馬' in title and 'お送りします' in title:
        return True
    return bool(RACE_TITLE_RE.search(title))


def active_jra_ids(epg_text):
    root = ET.fromstring(epg_text)
    today = datetime.now(JST).date(); now = datetime.now(JST)
    active = set(); last_stop = {}
    for p in root.findall('programme'):
        cid = p.get('channel') or ''
        if cid not in SOURCE_IDS:
            continue
        start = parse_xmltv_time(p.get('start')); stop = parse_xmltv_time(p.get('stop'))
        if not start or start.astimezone(JST).date() != today:
            continue
        title = (p.findtext('title') or '').strip()
        desc = (p.findtext('desc') or '').strip()
        if not is_real_jra_program(title, desc):
            continue
        active.add(cid)
        if stop:
            ls = stop.astimezone(JST)
            if cid not in last_stop or ls > last_stop[cid]:
                last_stop[cid] = ls
    for cid, stop in list(last_stop.items()):
        if now >= stop:
            active.discard(cid)
    return active, last_stop


def extract_special_entries(base):
    found = []; lines = base.splitlines(); i = 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith('#EXTINF:'):
            i += 1; continue
        block = [line]; j = i + 1
        while j < len(lines) and not lines[j].startswith('#EXTINF:') and not lines[j].startswith('## '):
            block.append(lines[j]); j += 1
        low = line.lower()
        if 'tvg-id="jra.official"' in low or 'tvg-id="jra.gch.free"' in low or 'グリーンチャンネル無料版' in line:
            found.append(block)
        i = j
    return found


def strip_jra_entries(base):
    managed = re.compile(re.escape(START) + r'.*?' + re.escape(END) + r'\n?', re.S)
    base = managed.sub('', base)
    managed_ids = set(SOURCE_IDS) | {'jra.gch', 'jra.official', 'jra.gch.free'}
    lines = base.splitlines(); out = []; i = 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith('#EXTINF:'):
            out.append(line); i += 1; continue
        block = [line]; j = i + 1
        while j < len(lines) and not lines[j].startswith('#EXTINF:') and not lines[j].startswith('## '):
            block.append(lines[j]); j += 1
        low = line.lower()
        remove = any(f'tvg-id="{cid}"' in low for cid in managed_ids) or 'グリーンチャンネル無料版' in line
        if not remove:
            out.extend(block)
        i = j
    return '\n'.join(out).rstrip() + '\n'


def route_blocks(active):
    selected = []
    if not active:
        return selected

    ids = ['jra.gch'] + [cid for cid in SOURCE_IDS if cid in active]
    for cid in ids:
        for display_name, playlist_file, logo_file in JRA_ROUTES[cid]:
            extinf = (
                f'#EXTINF:-1 tvg-id="{cid}" tvg-name="{TVG_NAMES[cid]}" '
                f'tvg-logo="{raw_url(logo_file)}" group-title="{GROUP}",{display_name}'
            )
            selected.extend([extinf, raw_url(playlist_file), ''])
    return selected


def insert_block(base, block):
    anchor = '# === GENERAL_YOUTUBE_MANAGED_START ==='
    return base.replace(anchor, block + '\n\n' + anchor, 1) if anchor in base else base.rstrip() + '\n\n' + block + '\n'


def main():
    now = datetime.now(JST)
    base = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    special = extract_special_entries(base)
    clean = strip_jra_entries(base)
    active, last_stop = active_jra_ids(fetch_text(PUBLIC_EPG_URL))

    selected = route_blocks(active)
    if active:
        seen = set()
        for block in special:
            if block[0] in seen:
                continue
            seen.add(block[0])
            b = block[:]
            b[0] = rewrite_group(b[0])
            selected.extend(b); selected.append('')

    body = '\n'.join(selected).rstrip()
    managed = START + '\n## グリーンCh（JRA開催日）\n' + body + ('\n' if body else '') + END
    FREEWIFI.write_text(insert_block(clean, managed).rstrip() + '\n', encoding='utf-8')

    status = {
        'generated_at': now.isoformat(),
        'active_count': len(active),
        'active_ids': [cid for cid in SOURCE_IDS if cid in active],
        'active_labels': [LABELS[cid] for cid in SOURCE_IDS if cid in active],
        'special_entries': len(special) if active else 0,
        'channels': {
            cid: {'label': LABELS[cid], 'active': cid in active, 'last_stop': last_stop.get(cid).isoformat() if last_stop.get(cid) else None}
            for cid in SOURCE_IDS
        }
    }
    STATUS_JSON.write_text(json.dumps(status, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    route_count = 2 + 2 * len(active) if active else 0
    print('JRA active:', ', '.join(status['active_labels']) or 'none')
    print('JRA custom-logo GreenCh routes:', route_count)
    print('JRA special entries:', status['special_entries'])


if __name__ == '__main__':
    main()
