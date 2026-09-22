from pathlib import Path
from datetime import datetime, timezone, timedelta, time
import html
import json
import re
import urllib.request
import xml.etree.ElementTree as ET

GUIDES = Path('guides.xml')
VERIFIED = Path('verified_daily_status.json')
JST = timezone(timedelta(hours=9))
TODAY = datetime.now(JST).date()
ISO_DATE = TODAY.strftime('%Y-%m-%d')
DISPLAY_DATE = TODAY.strftime('%Y年%m月%d日')

AUTO = {
    '川口': ('auto.kawaguchi', 'kawaguchi'),
    '伊勢崎': ('auto.isesaki', 'isesaki'),
    '浜松': ('auto.hamamatsu', 'hamamatsu'),
    '飯塚': ('auto.iizuka', 'iizuka'),
    '山陽': ('auto.sanyo', 'sanyou'),
}

PROGRAM_URLS = [
    'https://autorace.jp/race_info/Program/Web/{slug}/{date}_{race_no}',
    'https://autorace.jp/race_info/Program/{slug}/{date}_{race_no}',
]

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152.0 Safari/537.36'
FULLWIDTH = str.maketrans('0123456789', '０１２３４５６７８９')


def fetch(url, label):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ja-JP,ja;q=0.9,en;q=0.7',
        'Referer': 'https://autorace.jp/race_info/',
        'Cache-Control': 'no-cache',
    })
    try:
        with urllib.request.urlopen(req, timeout=25) as r:
            raw = r.read()
        for enc in ('utf-8', 'cp932', 'shift_jis'):
            try:
                return raw.decode(enc)
            except Exception:
                pass
        return raw.decode('utf-8', errors='ignore')
    except Exception as e:
        print(f'{label}: fetch failed: {e}')
        return ''


def plain_text(source):
    source = re.sub(r'(?is)<script.*?</script>', ' ', source or '')
    source = re.sub(r'(?is)<style.*?</style>', ' ', source)
    source = re.sub(r'(?s)<[^>]+>', ' ', source)
    source = html.unescape(source)
    return re.sub(r'\s+', ' ', source).strip()


def parse_program(source, race_no):
    if not source:
        return None
    p = plain_text(source)
    if '該当レースの開催は中止となりました' in p:
        return None

    race_ok = bool(re.search(rf'第\s*{race_no}\s*レース|(?<!\d){race_no}\s*R(?!\d)', p, re.I))
    if not race_ok:
        return None

    m = re.search(r'発走予定\s*([0-2]?\d)\s*[:：]\s*([0-5]\d)', p)
    if m:
        time_text = f'{int(m.group(1)):02d}:{m.group(2)}'
    else:
        m = re.search(r'発走予定\s*[:：]?\s*([0-2]?\d:[0-5]\d)', p)
        time_text = m.group(1).zfill(5) if m else ''

    if not time_text:
        m = re.search(r'電投締切\s*([0-2]?\d)\s*[:：]\s*([0-5]\d)', p)
        if m:
            t = datetime(2000, 1, 1, int(m.group(1)), int(m.group(2))) + timedelta(minutes=2)
            time_text = t.strftime('%H:%M')
    if not time_text:
        return None

    name = ''
    m = re.search(rf'第\s*{race_no}\s*レース\s*[|｜]?\s*([^|｜]{{1,40}})', p)
    if m:
        candidate = re.sub(r'\s+', ' ', m.group(1)).strip()
        if not re.fullmatch(r'20\d{2}年.*', candidate):
            name = candidate
    if not name:
        for word in ('優勝戦', '準決勝戦', '準決勝', '特別選抜戦', '選抜戦', '一般戦', '予選'):
            if word in p:
                name = word
                break
    if not name:
        name = 'オートレース'

    return {'race': race_no, 'time': time_text, 'name': name}


def get_races(venue, slug):
    races = []
    for n in range(1, 13):
        race = None
        for template in PROGRAM_URLS:
            url = template.format(slug=slug, date=ISO_DATE, race_no=n)
            source = fetch(url, f'AUTORACE {venue} {n}R')
            race = parse_program(source, n)
            if race:
                print(f"AUTORACE {venue} {n}R OK: {race['time']} via {url}")
                break
        if race:
            races.append(race)
    races.sort(key=lambda x: x['race'])
    return races


def race_datetime(time_text, previous=None):
    hh, mm = map(int, time_text.split(':'))
    day_add, hour = divmod(hh, 24)
    dt = datetime.combine(TODAY + timedelta(days=day_add), time(hour, mm), tzinfo=JST)
    if previous is not None and dt < previous - timedelta(hours=6):
        dt += timedelta(days=1)
    return dt


def day_type(venue, races):
    if not races:
        return 'デイ'
    first_h = int(races[0]['time'].split(':')[0])
    last_h, last_m = map(int, races[-1]['time'].split(':'))
    if last_h * 60 + last_m + 30 > 23 * 60 + 40:
        return 'オーバーミッドナイト'
    if venue == '伊勢崎' and first_h >= 17 and len(races) <= 8:
        return 'アフター5'
    if first_h >= 19:
        return 'ミッドナイト'
    if first_h >= 14:
        return 'ナイター'
    if first_h < 10:
        return 'モーニング'
    return 'デイ'


def fmt(dt):
    return dt.astimezone(JST).strftime('%Y%m%d%H%M%S +0900')


def load_verified_auto():
    if not VERIFIED.exists():
        return []
    try:
        cfg = json.loads(VERIFIED.read_text(encoding='utf-8-sig'))
    except Exception:
        return []
    if cfg.get('date') != TODAY.isoformat():
        return []
    return [v for v in ((cfg.get('public_sports') or {}).get('オートレース') or []) if v in AUTO]


def ensure_channel(root, cid, venue):
    for ch in root.findall('channel'):
        if ch.get('id') == cid:
            dn = ch.find('display-name')
            if dn is None:
                dn = ET.SubElement(ch, 'display-name')
            dn.text = f'{venue}オート'
            return
    ch = ET.Element('channel', {'id': cid})
    ET.SubElement(ch, 'display-name').text = f'{venue}オート'
    root.insert(0, ch)


def remove_today_programmes(root, cid):
    start_window = datetime.combine(TODAY, time(0, 0), tzinfo=JST)
    end_window = start_window + timedelta(days=1, hours=2)
    for p in list(root.findall('programme')):
        if p.get('channel') != cid:
            continue
        raw = p.get('start') or ''
        m = re.match(r'^(\d{14})', raw)
        if not m:
            continue
        dt = datetime.strptime(m.group(1), '%Y%m%d%H%M%S').replace(tzinfo=JST)
        if start_window <= dt < end_window:
            root.remove(p)


def add_programme(root, cid, start, stop, title, desc):
    if stop <= start:
        return
    p = ET.Element('programme', {'channel': cid, 'start': fmt(start), 'stop': fmt(stop)})
    ET.SubElement(p, 'title', {'lang': 'ja'}).text = title
    ET.SubElement(p, 'desc', {'lang': 'ja'}).text = desc
    root.append(p)


def rebuild_auto(root, venue, cid, races):
    ensure_channel(root, cid, venue)
    remove_today_programmes(root, cid)

    dtype = day_type(venue, races)
    race_dts = []
    prev = None
    for race in races:
        dt = race_datetime(race['time'], prev)
        race_dts.append((race, dt))
        prev = dt

    first_race, first_dt = race_dts[0]
    wait_start = max(datetime.combine(TODAY, time(8, 0), tzinfo=JST), first_dt - timedelta(hours=1))
    wait_stop = first_dt - timedelta(minutes=10)
    if wait_start < wait_stop:
        add_programme(
            root, cid, wait_start, wait_stop,
            f'{venue}オート 開催待ち／1R {first_race["time"]}発走',
            f'オートレース {venue}。開催区分: {dtype}。{DISPLAY_DATE}。',
        )

    for i, (race, dt) in enumerate(race_dts):
        start = dt - timedelta(minutes=10)
        if i + 1 < len(race_dts):
            stop = race_dts[i + 1][1] - timedelta(minutes=10)
        else:
            stop = dt + timedelta(minutes=30)
        if stop <= start:
            stop = dt + timedelta(minutes=12)
        marker = str(race['race']).translate(FULLWIDTH)
        detail = race['name']
        deco = f'🏆【{detail}】🏆' if '優勝' in detail or '決勝' in detail else (f'🔥【{detail}】🔥' if '準決' in detail else f'🏍️【{detail} 🏍️】')
        add_programme(
            root, cid, start, stop,
            f'【{marker}Ｒ】 {race["time"]}発走  {deco}',
            f'オートレース {venue}\n開催区分: {dtype}\n発走予定: {race["time"]}\n{detail}\n{DISPLAY_DATE}',
        )

    finish = race_dts[-1][1] + timedelta(minutes=30)
    end_limit = datetime.combine(TODAY + timedelta(days=1), time(1, 30), tzinfo=JST)
    if finish < end_limit:
        add_programme(
            root, cid, finish, end_limit,
            f'{venue}オート 本日の全レース終了',
            f'{venue}の本日のオートレースは全て終了しました。',
        )
    print(f'AUTORACE FreeWiFi direct: {venue} {len(races)}R / {dtype}')


def main():
    if not GUIDES.exists():
        raise SystemExit('guides.xml not found')
    active = load_verified_auto()
    if not active:
        print('AUTORACE FreeWiFi direct: no verified active venues today')
        return

    tree = ET.parse(GUIDES)
    root = tree.getroot()
    repaired = []
    for venue in active:
        cid, slug = AUTO[venue]
        races = get_races(venue, slug)
        if not races:
            print(f'AUTORACE FreeWiFi direct: {venue} official race pages unavailable; existing EPG preserved')
            continue
        rebuild_auto(root, venue, cid, races)
        repaired.append(venue)

    programmes_by_id = {}
    for p in root.findall('programme'):
        programmes_by_id.setdefault(p.get('channel'), 0)
        programmes_by_id[p.get('channel')] += 1
    missing = [venue for venue in active if programmes_by_id.get(AUTO[venue][0], 0) == 0]
    if missing:
        raise SystemExit(f'AUTORACE FreeWiFi direct validation failed: no EPG for {missing}')

    channels = [x for x in list(root) if x.tag == 'channel']
    programmes = [x for x in list(root) if x.tag == 'programme']
    other = [x for x in list(root) if x.tag not in ('channel', 'programme')]
    programmes.sort(key=lambda x: (x.get('start', ''), x.get('channel', '')))
    for x in list(root):
        root.remove(x)
    for x in channels + other + programmes:
        root.append(x)

    ET.indent(tree, space='  ')
    tree.write(GUIDES, encoding='utf-8', xml_declaration=True)
    print('AUTORACE FreeWiFi direct repaired:', ', '.join(repaired) if repaired else 'none')


if __name__ == '__main__':
    main()
