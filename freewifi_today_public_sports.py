from pathlib import Path
from datetime import datetime, timezone, timedelta, time
import json
import re
import xml.etree.ElementTree as ET

FREEWIFI = Path('freewifi')
STATUS_JSON = Path('today_public_sports_status.json')
PUBLIC_M3U = Path('ganble')
PUBLIC_EPG = Path('public_sports_epg_local.xml')
START = '# === TODAY_PUBLIC_SPORTS_START ==='
END = '# === TODAY_PUBLIC_SPORTS_END ==='
GROUP = '今日の開催場'
JST = timezone(timedelta(hours=9))
TARGET_SECTIONS = {'競輪', '地方競馬', 'ボートレース', 'オートレース'}
NON_EVENT_WORDS = ('本日非開催','非開催','開催していません','開催予定はありません','本日開催なし','開催なし','次回開催','データ取得準備中','休止中','休止','準備中','現在準備中','本日の開催は終了しました')


def parse_m3u(text):
    entries = {}
    section = ''
    lines = text.splitlines(); i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('## '):
            section = line[3:].strip(); i += 1; continue
        if not line.startswith('#EXTINF:'):
            i += 1; continue
        block = [line]; j = i + 1
        while j < len(lines) and not lines[j].startswith('#EXTINF:') and not lines[j].startswith('## '):
            if lines[j].strip(): block.append(lines[j])
            j += 1
        m = re.search(r'tvg-id="([^"]+)"', line)
        if m and section in TARGET_SECTIONS:
            entries[m.group(1)] = (section, block)
        i = j
    return entries


def parse_xmltv_time(value):
    m = re.match(r'^(\d{14})\s*([+-]\d{4})?', str(value or '').strip())
    if not m: return None
    d, off = m.groups()
    try:
        if off:
            return datetime.strptime(f'{d} {off}', '%Y%m%d%H%M%S %z').astimezone(JST)
        return datetime.strptime(d, '%Y%m%d%H%M%S').replace(tzinfo=JST)
    except Exception:
        return None


def race_datetime(today, hhmm):
    try:
        hh, mm = map(int, hhmm.split(':'))
        if mm < 0 or mm > 59 or hh < 0:
            return None
        day_add, hour = divmod(hh, 24)
        return datetime.combine(today + timedelta(days=day_add), time(hour, mm), tzinfo=JST)
    except Exception:
        return None


def epg_state():
    if not PUBLIC_EPG.exists():
        raise SystemExit('public_sports_epg_local.xml missing')
    try:
        root = ET.parse(PUBLIC_EPG).getroot()
    except Exception as e:
        raise SystemExit(f'public_sports_epg_local.xml parse failed: {e}')

    now = datetime.now(JST); today = now.date()
    real = set(); modes = {}; next_race = {}
    bad = 0
    for p in root.findall('programme'):
        try:
            cid = p.get('channel') or ''
            if not cid:
                continue
            start = parse_xmltv_time(p.get('start'))
            if not start:
                bad += 1; continue
            # A 24:xx race is stored by XMLTV on the following calendar day.
            # Accept the current day's grid plus the immediate after-midnight
            # tail only when its title itself uses 24:xx or later.
            title = (p.findtext('title') or '').strip()
            desc = (p.findtext('desc') or '').strip()
            tm = re.search(r'([0-9]{1,2}:[0-5]\d)\s*発走', title)
            is_after_midnight_tail = bool(tm and int(tm.group(1).split(':')[0]) >= 24 and start.date() == today + timedelta(days=1))
            if start.date() != today and not is_after_midnight_tail:
                continue
            compact = ''.join(title.split())
            if not compact or any(x in compact for x in NON_EVENT_WORDS):
                continue
            real.add(cid)
            joined = title + ' ' + desc
            modes[cid] = ('overnight' if 'オーバーミッドナイト' in joined else 'midnight' if 'ミッドナイト' in joined else 'night' if 'ナイター' in joined else 'morning' if 'モーニング' in joined else 'day')
            m = re.search(r'(?:【\s*)?([０-９0-9]{1,2})\s*[ＲR](?:\s*】)?', title)
            if m and tm:
                trans = str.maketrans('０１２３４５６７８９','0123456789')
                dt = race_datetime(today, tm.group(1))
                if dt and dt >= now:
                    item = {'race': int(m.group(1).translate(trans)), 'start': tm.group(1), 'title': title, '_dt': dt}
                    if cid not in next_race or dt < next_race[cid]['_dt']:
                        next_race[cid] = item
        except Exception as e:
            bad += 1
            print(f'EPG row skipped: {e}')
            continue
    for v in next_race.values(): v.pop('_dt', None)
    print(f'EPG state: active={len(real)} next={len(next_race)} skipped={bad}')
    return real, modes, next_race


def entry_name(block):
    m = re.search(r'tvg-name="([^"]+)"', block[0])
    return m.group(1) if m else block[0].rsplit(',',1)[-1].strip()


def sanitize_extinf(line):
    line = re.sub(r'\s+tvg-logo="[^"]*earphone1981[^"]*"', '', line, flags=re.I)
    if 'group-title=' in line:
        line = re.sub(r'group-title="[^"]*"', f'group-title="{GROUP}"', line, count=1)
    else:
        pos = line.find(',')
        line = line[:pos] + f' group-title="{GROUP}"' + line[pos:] if pos >= 0 else line
    return line


def strip_ids(text, ids):
    lines = text.splitlines(); out=[]; i=0
    while i < len(lines):
        line = lines[i]
        if line.startswith('#EXTINF:'):
            m = re.search(r'tvg-id="([^"]+)"', line)
            if m and m.group(1) in ids:
                i += 1
                while i < len(lines) and not lines[i].startswith('#EXTINF:') and not lines[i].startswith('## ') and not lines[i].startswith('# ==='): i += 1
                continue
        out.append(line); i += 1
    return '\n'.join(out).rstrip() + '\n'


def replace_block(text, payload):
    pat = re.compile(re.escape(START)+r'.*?'+re.escape(END)+r'\n?', re.S)
    if pat.search(text): return pat.sub(lambda _m: payload+'\n', text, count=1)
    anchor = '# === GENERAL_YOUTUBE_MANAGED_START ==='
    return text.replace(anchor, payload+'\n\n'+anchor, 1) if anchor in text else text.rstrip()+'\n\n'+payload+'\n'


def main():
    if not FREEWIFI.exists() or not PUBLIC_M3U.exists():
        raise SystemExit('freewifi/ganble missing')
    real, modes, next_race = epg_state()
    entries = parse_m3u(PUBLIC_M3U.read_text(encoding='utf-8-sig', errors='replace'))
    if not entries:
        raise SystemExit('ganble has no public-sports master entries')
    rows=[]; status={}
    for cid, (section, block) in entries.items():
        if cid not in real: continue
        try:
            item_block = block[:]
            item_block[0] = sanitize_extinf(item_block[0])
            name = entry_name(item_block); nr = next_race.get(cid)
            rows.append({'id':cid,'name':name,'block':item_block,'next_race':nr})
            status[cid] = {'section':section,'name':name,'mode':modes.get(cid,'day'),'source':'ajiousama local direct EPG','epg_available':True,'next_race':nr,'next_race_text':f"次は {nr['race']}R {nr['start']}発走" if nr else '本日開催／次レースなし'}
        except Exception as e:
            print(f'M3U row skipped {cid}: {e}')
    rows.sort(key=lambda r: ((int(r['next_race']['start'][:2])*60+int(r['next_race']['start'][3:])) if r['next_race'] else 2000, r['name']))
    body=[]
    for r in rows: body += r['block'] + ['']
    managed = START+'\n## 今日の開催場\n'+'\n'.join(body).rstrip()+('\n' if body else '')+END
    base = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    base = strip_ids(base, set(entries))
    FREEWIFI.write_text(replace_block(base, managed).rstrip()+'\n', encoding='utf-8')
    STATUS_JSON.write_text(json.dumps({'generated_at':datetime.now(JST).isoformat(),'channels':{r['id']:status[r['id']] for r in rows}}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('Today public sports local:', len(rows))

if __name__ == '__main__': main()
