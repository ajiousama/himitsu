from pathlib import Path
from datetime import datetime, timezone, timedelta
import json
import re
import xml.etree.ElementTree as ET

FREEWIFI = Path('freewifi')
STATUS_JSON = Path('today_public_sports_status.json')
LOCAL_EPG = Path('public_sports_epg_local.xml')
START = '# === TODAY_PUBLIC_SPORTS_START ==='
END = '# === TODAY_PUBLIC_SPORTS_END ==='
JST = timezone(timedelta(hours=9))
NON_EVENT_WORDS = (
    '本日非開催', '非開催', '開催していません', '開催予定はありません',
    '本日開催なし', '開催なし', '次回開催', 'データ取得準備中',
    '休止中', '休止', '準備中', '現在準備中',
    '本日の開催は終了しました', '開催は終了しました', '開催終了', '終了しました',
)


def parse_xmltv_time(value):
    if not value:
        return None
    m = re.match(r'^(\d{14})\s*([+-]\d{4})?', value.strip())
    if not m:
        return None
    base = datetime.strptime(m.group(1), '%Y%m%d%H%M%S')
    off = m.group(2)
    if off:
        sign = 1 if off[0] == '+' else -1
        tz = timezone(sign * timedelta(hours=int(off[1:3]), minutes=int(off[3:5])))
        return base.replace(tzinfo=tz)
    return base.replace(tzinfo=JST)


def actual_race_dt(title, today, fallback):
    m = re.search(r'(?<!\d)(\d{1,2})[：:](\d{2})\s*発走', title)
    if not m:
        return fallback
    hour = int(m.group(1))
    minute = int(m.group(2))
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return fallback
    return datetime(today.year, today.month, today.day, hour, minute, tzinfo=JST)


def epg_state(text, now):
    root = ET.fromstring(text)
    today = now.date()
    state = {}
    for p in root.findall('programme'):
        cid = p.get('channel') or ''
        start = parse_xmltv_time(p.get('start'))
        stop = parse_xmltv_time(p.get('stop'))
        if not cid or not start or start.astimezone(JST).date() != today:
            continue
        title = (p.findtext('title') or '').strip()
        compact = ''.join(title.split())
        if not compact or any(word in compact for word in NON_EVENT_WORDS):
            continue
        sj = start.astimezone(JST)
        ej = stop.astimezone(JST) if stop else None
        s = state.setdefault(cid, {'last_stop': None, 'next_race': None, 'has_today': False})
        s['has_today'] = True
        if ej and (s['last_stop'] is None or ej > s['last_stop']):
            s['last_stop'] = ej

        race_m = re.search(r'(?<!\d)(\d{1,2})[RＲ](?!\w)', title, re.I)
        race_dt = actual_race_dt(title, today, sj)
        if race_m and race_dt >= now:
            if s['next_race'] is None or race_dt < s['next_race']['_dt']:
                s['next_race'] = {
                    'race': int(race_m.group(1)),
                    'start': race_dt.strftime('%H:%M'),
                    'title': title,
                    '_dt': race_dt,
                }
    return state


def parse_managed_entries(text):
    m = re.search(re.escape(START) + r'(.*?)' + re.escape(END), text, re.S)
    if not m:
        return [], None
    body = m.group(1)
    lines = body.splitlines()
    entries = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith('#EXTINF:'):
            i += 1
            continue
        block = [line]
        j = i + 1
        while j < len(lines) and not lines[j].startswith('#EXTINF:'):
            if lines[j].strip() and not lines[j].startswith('## '):
                block.append(lines[j])
            j += 1
        mid = re.search(r'tvg-id="([^"]+)"', line)
        if mid:
            name_m = re.search(r'tvg-name="([^"]+)"', line)
            name = name_m.group(1) if name_m else line.rsplit(',', 1)[-1].strip()
            entries.append({'id': mid.group(1), 'name': name, 'block': block})
        i = j
    return entries, m


def sort_key(item):
    nr = item.get('next_race')
    if nr and re.fullmatch(r'\d{2}:\d{2}', nr.get('start', '')):
        h, m = map(int, nr['start'].split(':'))
        return (0, h * 60 + m, item['name'])
    return (1, 0, item['name'])


def main():
    now = datetime.now(JST)
    if not FREEWIFI.exists():
        raise SystemExit('freewifi not found')
    if not LOCAL_EPG.exists() or LOCAL_EPG.stat().st_size == 0:
        raise SystemExit('public_sports_epg_local.xml missing or empty')

    text = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    entries, match = parse_managed_entries(text)
    if match is None:
        print('Today public sports managed block not found')
        return 0

    state = epg_state(LOCAL_EPG.read_text(encoding='utf-8-sig', errors='replace'), now)
    old_status = {}
    if STATUS_JSON.exists():
        try:
            old_status = json.loads(STATUS_JSON.read_text(encoding='utf-8-sig'))
        except Exception:
            old_status = {}
    old_channels = old_status.get('channels') or {}

    kept = []
    removed = []
    channels = {}
    for entry in entries:
        cid = entry['id']
        s = state.get(cid)
        # Local EPGの実レース番組だけを基準にし、最終stopを過ぎたら終了確定。
        if s and s.get('has_today') and s.get('last_stop') and now >= s['last_stop']:
            removed.append((cid, entry['name'], s['last_stop'].strftime('%H:%M')))
            continue

        nr = None
        if s and s.get('next_race'):
            nr = dict(s['next_race'])
            nr.pop('_dt', None)
        entry['next_race'] = nr
        kept.append(entry)

        meta = dict(old_channels.get(cid) or {})
        meta.setdefault('name', entry['name'])
        meta['next_race'] = nr
        if nr:
            meta['next_race_text'] = f"次は {nr['race']}R {nr['start']}発走"
        elif s and s.get('has_today'):
            meta['next_race_text'] = '本日開催中／次レース時刻確認待ち'
        channels[cid] = meta

    kept.sort(key=sort_key)

    body = []
    for entry in kept:
        body.extend(entry['block'])
        body.append('')
    payload = '\n'.join(body).rstrip()
    managed = START + '\n## 今日の開催場\n' + payload + ('\n' if payload else '') + END
    text = text[:match.start()] + managed + text[match.end():]
    FREEWIFI.write_text(text.rstrip() + '\n', encoding='utf-8')

    result = dict(old_status)
    result['generated_at'] = now.isoformat()
    result['end_check_at'] = now.isoformat()
    result['end_check_source'] = 'public_sports_epg_local.xml'
    result['end_check_removed'] = [cid for cid, _, _ in removed]
    result['channels'] = channels
    STATUS_JSON.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    print('Final venue end check:', now.strftime('%H:%M JST'))
    print('End check source: public_sports_epg_local.xml')
    print('Removed ended venues:', len(removed))
    for cid, name, stop in removed:
        print(f'  REMOVE {stop} {name} [{cid}]')
    print('Remaining venues:', len(kept))
    print('Order: actual next race start ascending; unknown times after known times')
    for entry in kept:
        nr = entry.get('next_race')
        print(f"  {(nr['start'] if nr else '--:--')} {entry['name']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
