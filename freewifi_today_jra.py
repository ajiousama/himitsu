from pathlib import Path
from datetime import datetime, timezone, timedelta
import json
import re
import urllib.request
import xml.etree.ElementTree as ET

FREEWIFI = Path('freewifi')
STATUS_JSON = Path('today_jra_status.json')
PUBLIC_M3U_URL = 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/public_sports.m3u'
PUBLIC_EPG_URL = 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/epg.xml'
START = '# === TODAY_JRA_START ==='
END = '# === TODAY_JRA_END ==='
GROUP = '今日の開催場'
JST = timezone(timedelta(hours=9))
SOURCE_IDS = ('jra.east', 'jra.west', 'jra.hokkaido')
LABELS = {'jra.east':'EAST', 'jra.west':'WEST', 'jra.hokkaido':'LOCAL/第三場'}


def fetch_text(url, timeout=60):
    req = urllib.request.Request(url, headers={'User-Agent': 'FreeWiFi-JRA-Daily/1.0', 'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8-sig', errors='replace')


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


def parse_entries(text):
    out = {}
    lines = text.splitlines(); i = 0
    while i < len(lines):
        if not lines[i].startswith('#EXTINF:'):
            i += 1; continue
        block = [lines[i]]; j = i + 1
        while j < len(lines) and not lines[j].startswith('#EXTINF:') and not lines[j].startswith('## '):
            if lines[j].strip(): block.append(lines[j])
            j += 1
        m = re.search(r'tvg-id="([^"]+)"', lines[i])
        if m: out[m.group(1)] = block
        i = j
    return out


def rewrite_group(extinf):
    if 'group-title=' in extinf:
        return re.sub(r'group-title="[^"]*"', f'group-title="{GROUP}"', extinf, count=1)
    comma = extinf.find(',')
    return extinf[:comma] + f' group-title="{GROUP}"' + extinf[comma:] if comma >= 0 else extinf + f' group-title="{GROUP}"'


def active_jra_ids(epg_text):
    root = ET.fromstring(epg_text)
    today = datetime.now(JST).date(); now = datetime.now(JST)
    active = set(); last_stop = {}
    for p in root.findall('programme'):
        cid = p.get('channel') or ''
        if cid not in SOURCE_IDS: continue
        start = parse_xmltv_time(p.get('start')); stop = parse_xmltv_time(p.get('stop'))
        if not start or start.astimezone(JST).date() != today: continue
        title = (p.findtext('title') or '').strip()
        if not title or any(w in title for w in ('非開催','休止','準備中','データ取得準備中')): continue
        active.add(cid)
        if stop:
            ls = stop.astimezone(JST)
            if cid not in last_stop or ls > last_stop[cid]: last_stop[cid] = ls
    for cid, stop in list(last_stop.items()):
        if now >= stop: active.discard(cid)
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
        if 'tvg-id="jra.official"' in low or 'グリーンチャンネル無料版' in line: found.append(block)
        i = j
    return found


def strip_jra_entries(base):
    managed = re.compile(re.escape(START) + r'.*?' + re.escape(END) + r'\n?', re.S)
    base = managed.sub('', base)
    lines = base.splitlines(); out = []; i = 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith('#EXTINF:'):
            out.append(line); i += 1; continue
        block = [line]; j = i + 1
        while j < len(lines) and not lines[j].startswith('#EXTINF:') and not lines[j].startswith('## '):
            block.append(lines[j]); j += 1
        low = line.lower()
        remove = any(f'tvg-id="{cid}"' in low for cid in SOURCE_IDS) or 'tvg-id="jra.official"' in low or 'グリーンチャンネル無料版' in line
        if not remove: out.extend(block)
        i = j
    return '\n'.join(out).rstrip() + '\n'


def insert_block(base, block):
    anchor = '# === GENERAL_YOUTUBE_MANAGED_START ==='
    return base.replace(anchor, block + '\n\n' + anchor, 1) if anchor in base else base.rstrip() + '\n\n' + block + '\n'


def main():
    now = datetime.now(JST)
    base = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    special = extract_special_entries(base); clean = strip_jra_entries(base)
    public_entries = parse_entries(fetch_text(PUBLIC_M3U_URL))
    active, last_stop = active_jra_ids(fetch_text(PUBLIC_EPG_URL))

    selected = []
    for cid in SOURCE_IDS:
        if cid not in active: continue
        block = public_entries.get(cid)
        if not block: continue
        b = block[:]; b[0] = rewrite_group(b[0]); selected.extend(b); selected.append('')

    if active:
        seen = set()
        for block in special:
            if block[0] in seen: continue
            seen.add(block[0]); b = block[:]; b[0] = rewrite_group(b[0]); selected.extend(b); selected.append('')

    body = '\n'.join(selected).rstrip()
    managed = START + '\n## JRA\n' + body + ('\n' if body else '') + END
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
    print('JRA active:', ', '.join(status['active_labels']) or 'none')
    print('JRA special entries:', status['special_entries'])


if __name__ == '__main__':
    main()
