from pathlib import Path
from datetime import datetime, timezone, timedelta
import json
import re
import urllib.request
import xml.etree.ElementTree as ET

FREEWIFI = Path('freewifi')
STATUS_JSON = Path('today_public_sports_status.json')
PUBLIC_M3U_URL = 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/public_sports.m3u'
PUBLIC_EPG_URL = 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/epg.xml'
GENERAL_YOUTUBE = Path('public_sports_youtube_fallback.m3u')

FALLBACK_ENTRIES = {
    'boat.kiryu': {
        'source_id': 'youtube.boat_kiryu',
        'section': 'ボートレース',
        'name': 'BOATRACE桐生',
        'logo': 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/public_sports_logos_github_43/boatrace_24_spaced_cut_1024/kiryu.png',
    },
    'boat.suminoe': {
        'source_id': 'youtube.boat_suminoe',
        'section': 'ボートレース',
        'name': 'BOATRACE住之江',
        'logo': 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/public_sports_logos_github_43/boatrace_24_spaced_cut_1024/suminoe.png',
    },
}

START = '# === TODAY_PUBLIC_SPORTS_START ==='
END = '# === TODAY_PUBLIC_SPORTS_END ==='
GROUP = '今日の開催場'
JST = timezone(timedelta(hours=9))
TARGET_SECTIONS = {'競輪', '地方競馬', 'ボートレース', 'オートレース'}
DISPLAY_NAMES = {'地方競馬': '地方競馬', '競輪': '競輪', 'ボートレース': 'ボート', 'オートレース': 'オート'}
NON_EVENT_WORDS = (
    '本日非開催', '非開催', '開催していません', '開催予定はありません',
    '本日開催なし', '開催なし', '次回開催', 'データ取得準備中',
    '休止中', '休止', '準備中', '現在準備中',
)


def fetch_text(url, timeout=30):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (FreeWiFi venue checker)'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8-sig', errors='replace')


def parse_m3u(text):
    entries = {}
    section = ''
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('## '):
            section = line[3:].strip()
            i += 1
            continue
        if line.startswith('#EXTINF:'):
            block = [lines[i]]
            j = i + 1
            while j < len(lines) and not lines[j].startswith('#EXTINF:') and not lines[j].startswith('## '):
                if lines[j].strip():
                    block.append(lines[j])
                j += 1
            m = re.search(r'tvg-id="([^"]+)"', line)
            if m and section in TARGET_SECTIONS:
                entries[m.group(1)] = (section, block)
            i = j
            continue
        i += 1
    return entries


def parse_all_entries(text):
    out = {}
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith('#EXTINF:'):
            i += 1
            continue
        block = [line]
        j = i + 1
        while j < len(lines) and not lines[j].startswith('#EXTINF:') and not lines[j].startswith('## ') and not lines[j].startswith('# ==='):
            if lines[j].strip():
                block.append(lines[j])
            j += 1
        m = re.search(r'tvg-id="([^"]+)"', line)
        if m:
            out[m.group(1)] = block
        i = j
    return out


def materialize_fallback(cid, sources):
    spec = FALLBACK_ENTRIES[cid]
    block = sources.get(spec['source_id'])
    if not block:
        return None
    b = block[:]
    line = b[0]
    line = re.sub(r'tvg-id="[^"]+"', f'tvg-id="{cid}"', line, count=1)
    if 'tvg-name=' in line:
        line = re.sub(r'tvg-name="[^"]*"', f'tvg-name="{spec["name"]}"', line, count=1)
    else:
        line = line.replace('#EXTINF:-1', f'#EXTINF:-1 tvg-name="{spec["name"]}"', 1)
    if 'tvg-logo=' in line:
        line = re.sub(r'tvg-logo="[^"]*"', f'tvg-logo="{spec["logo"]}"', line, count=1)
    else:
        line = line.replace(' group-title=', f' tvg-logo="{spec["logo"]}" group-title=', 1)
    line = re.sub(r',.*$', ',' + spec['name'], line, count=1)
    b[0] = line
    return b


def strip_tvg_ids(text, ids):
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('#EXTINF:') and any(f'tvg-id="{cid}"' in line for cid in ids):
            i += 1
            while i < len(lines) and not lines[i].startswith('#EXTINF:') and not lines[i].startswith('## ') and not lines[i].startswith('# ==='):
                i += 1
            continue
        out.append(line)
        i += 1
    return '\n'.join(out).rstrip() + '\n'


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


def epg_state(text):
    root = ET.fromstring(text)
    today = datetime.now(JST).date()
    now = datetime.now(JST)
    real = set()
    modes = {}
    next_race = {}

    for p in root.findall('programme'):
        cid = p.get('channel') or ''
        start = parse_xmltv_time(p.get('start'))
        if not start or start.astimezone(JST).date() != today:
            continue

        title = (p.findtext('title') or '').strip()
        compact = ''.join(title.split())
        if not compact or any(word in compact for word in NON_EVENT_WORDS):
            continue

        real.add(cid)
        sj = start.astimezone(JST)
        joined = title + ' ' + (p.findtext('desc') or '')
        modes[cid] = (
            'overnight' if 'オーバーミッドナイト' in joined
            else 'midnight' if 'ミッドナイト' in joined
            else 'night' if 'ナイター' in joined
            else modes.get(cid, 'day')
        )

        if sj >= now:
            m = re.search(r'(?<!\d)(\d{1,2})[RＲ](?!\w)', title, re.I)
            if m:
                item = {
                    'race': int(m.group(1)),
                    'start': sj.strftime('%H:%M'),
                    'title': title,
                    '_dt': sj,
                }
                if cid not in next_race or sj < next_race[cid]['_dt']:
                    next_race[cid] = item

    for value in next_race.values():
        value.pop('_dt', None)
    return real, modes, next_race


def entry_name(block):
    m = re.search(r'tvg-name="([^"]+)"', block[0])
    return m.group(1) if m else block[0].rsplit(',', 1)[-1].strip()


def rewrite_group(extinf):
    if 'group-title=' in extinf:
        return re.sub(r'group-title="[^"]*"', f'group-title="{GROUP}"', extinf, count=1)
    comma = extinf.find(',')
    return extinf[:comma] + f' group-title="{GROUP}"' + extinf[comma:] if comma >= 0 else extinf + f' group-title="{GROUP}"'


def replace_block(text, block):
    text = re.sub(re.escape(START) + r'.*?' + re.escape(END) + r'\n?', '', text, flags=re.S)
    anchor = '# === GENERAL_YOUTUBE_MANAGED_START ==='
    return text.replace(anchor, block + '\n\n' + anchor, 1) if anchor in text else text.rstrip() + '\n\n' + block + '\n'


def next_race_sort_key(nr, name):
    if nr and re.fullmatch(r'\d{2}:\d{2}', nr.get('start', '')):
        hour, minute = map(int, nr['start'].split(':'))
        return (hour * 60 + minute, name)
    # 本日開催終了、または次レース時刻を取得できない場は最後。
    return (24 * 60 + 1, name)


def main():
    now = datetime.now(JST)
    base = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    base = strip_tvg_ids(base, {x['source_id'] for x in FALLBACK_ENTRIES.values()})

    entries = parse_m3u(fetch_text(PUBLIC_M3U_URL))
    epg_real, epg_modes, next_race = epg_state(fetch_text(PUBLIC_EPG_URL))

    counts = {section: 0 for section in TARGET_SECTIONS}
    status = {}
    rows = []

    for tvg, (section, block) in entries.items():
        if tvg not in epg_real:
            continue
        name = entry_name(block)
        nr = next_race.get(tvg)
        b = block[:]
        b[0] = rewrite_group(b[0])
        rows.append({'id': tvg, 'name': name, 'block': b, 'next_race': nr})
        counts[section] += 1
        status[tvg] = {
            'section': section,
            'name': name,
            'mode': epg_modes.get(tvg, 'day'),
            'source': 'earphone1981 verified EPG',
            'epg_available': True,
            'next_race': nr,
            'next_race_text': f"次は {nr['race']}R {nr['start']}発走" if nr else '本日開催終了',
        }

    fallback_sources = parse_all_entries(
        GENERAL_YOUTUBE.read_text(encoding='utf-8-sig', errors='replace')
    ) if GENERAL_YOUTUBE.exists() else {}

    for cid, spec in FALLBACK_ENTRIES.items():
        if cid not in epg_real or cid in status:
            continue
        block = materialize_fallback(cid, fallback_sources)
        if not block:
            print(f'Fallback LIVE missing: {cid}')
            continue
        block[0] = rewrite_group(block[0])
        nr = next_race.get(cid)
        rows.append({'id': cid, 'name': spec['name'], 'block': block, 'next_race': nr})
        section = spec['section']
        counts[section] += 1
        status[cid] = {
            'section': section,
            'name': spec['name'],
            'mode': epg_modes.get(cid, 'night'),
            'source': 'official YouTube fallback',
            'epg_available': True,
            'next_race': nr,
            'next_race_text': f"次は {nr['race']}R {nr['start']}発走" if nr else '本日開催終了',
        }

    rows.sort(key=lambda row: next_race_sort_key(row['next_race'], row['name']))

    selected = []
    for row in rows:
        selected.extend(row['block'])
        selected.append('')

    ordered_status = {row['id']: status[row['id']] for row in rows}
    body = '\n'.join(selected).rstrip()
    managed = START + '\n## 今日の開催場\n' + body + ('\n' if body else '') + END
    FREEWIFI.write_text(replace_block(base, managed).rstrip() + '\n', encoding='utf-8')
    STATUS_JSON.write_text(
        json.dumps({'generated_at': now.isoformat(), 'channels': ordered_status}, ensure_ascii=False, indent=2) + '\n',
        encoding='utf-8',
    )

    print('Today public sports synced:', sum(counts.values()))
    print('Order: next race time ascending; ended/unknown last')
    for row in rows:
        nr = row['next_race']
        print(f"  {(nr['start'] if nr else '--:--')} {row['name']}")
    for section in ('地方競馬', '競輪', 'ボートレース', 'オートレース'):
        print(f'{DISPLAY_NAMES[section]}: {counts.get(section, 0)}')


if __name__ == '__main__':
    main()
