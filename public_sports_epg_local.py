from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone, time
from html.parser import HTMLParser
import html as html_lib
import http.cookiejar
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

import keirin_epg_direct as keirin_direct
import autorace_epg_direct as auto_direct

OUT = Path('public_sports_epg_local.xml')
VERIFIED = Path('verified_daily_status.json')
JST = timezone(timedelta(hours=9))
DAYS = 3
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152.0 Safari/537.36'
FULLWIDTH = str.maketrans('0123456789', '０１２３４５６７８９')

KEIRIN_IDS = dict(keirin_direct.KEIRIN_IDS)
KEIRIN_SCHEDULE_URL = 'https://keirin.jp/pc/raceschedule?scym={month}&scyy={year}'
KEIRIN_GRADE_BY_SRC = {
    'ico_f1.png': 'F1', 'ico_f2.png': 'F2', 'ico_g1.png': 'G1',
    'ico_g2.png': 'G2', 'ico_g3.png': 'G3',
}
KEIRIN_TYPE_BY_SRC = {
    'ico_kaisai_3.png': ('night', 'ナイター'),
    'ico_kaisai_5.png': ('midnight', 'ミッドナイト'),
    'ico_kaisai_8.png': ('morning', 'モーニング'),
}
KEIRIN_PROVISIONAL = {
    'morning': ('10:00', '14:00'),
    'day': ('10:30', '17:00'),
    'night': ('15:00', '21:00'),
    'midnight': ('20:30', '23:30'),
}

NAR = {
    '帯広': ('03', 'chihou.obihiro'), '門別': ('36', 'chihou.mombetsu'),
    '盛岡': ('10', 'chihou.morioka'), '水沢': ('11', 'chihou.mizusawa'),
    '浦和': ('18', 'chihou.urawa'), '船橋': ('19', 'chihou.funabashi'),
    '大井': ('20', 'chihou.oi'), '川崎': ('21', 'chihou.kawasaki_keiba'),
    '金沢': ('22', 'chihou.kanazawa'), '笠松': ('23', 'chihou.kasamatsu'),
    '名古屋': ('24', 'chihou.nagoya_keiba'), '園田': ('27', 'chihou.sonoda'),
    '姫路': ('28', 'chihou.himeji'), '高知': ('31', 'chihou.kochi_keiba'),
    '佐賀': ('32', 'chihou.saga'),
}
NAR_URL = (
    'https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo/RaceList'
    '?k_babaCode={code}&k_raceDate={date}'
)

BOAT = {
    '01': ('桐生', 'boat.kiryu'), '02': ('戸田', 'boat.toda'),
    '03': ('江戸川', 'boat.edogawa'), '04': ('平和島', 'boat.heiwajima'),
    '05': ('多摩川', 'boat.tamagawa'), '06': ('浜名湖', 'boat.hamanako'),
    '07': ('蒲郡', 'boat.gamagori'), '08': ('常滑', 'boat.tokoname'),
    '09': ('津', 'boat.tsu'), '10': ('三国', 'boat.mikuni'),
    '11': ('びわこ', 'boat.biwako'), '12': ('住之江', 'boat.suminoe'),
    '13': ('尼崎', 'boat.amagasaki'), '14': ('鳴門', 'boat.naruto'),
    '15': ('丸亀', 'boat.marugame'), '16': ('児島', 'boat.kojima'),
    '17': ('宮島', 'boat.miyajima'), '18': ('徳山', 'boat.tokuyama'),
    '19': ('下関', 'boat.shimonoseki'), '20': ('若松', 'boat.wakamatsu'),
    '21': ('芦屋', 'boat.ashiya'), '22': ('福岡', 'boat.fukuoka'),
    '23': ('唐津', 'boat.karatsu'), '24': ('大村', 'boat.omura'),
}
BOAT_INDEX = 'https://www.boatrace.jp/owpc/pc/race/index?hd={date}'
BOAT_RACE = 'https://www.boatrace.jp/owpc/pc/race/raceindex?hd={date}&jcd={code}'

AUTO = {
    '川口': ('auto.kawaguchi', 'kawaguchi'),
    '伊勢崎': ('auto.isesaki', 'isesaki'),
    '浜松': ('auto.hamamatsu', 'hamamatsu'),
    '飯塚': ('auto.iizuka', 'iizuka'),
    '山陽': ('auto.sanyo', 'sanyou'),
}

JRA_STREAMS = {'JRA EAST': 'jra.east', 'JRA WEST': 'jra.west', 'JRA HOKKAIDO': 'jra.hokkaido'}
JRA_VENUE_STREAM = {
    '東京': 'JRA EAST', '中山': 'JRA EAST', '新潟': 'JRA EAST', '福島': 'JRA EAST',
    '京都': 'JRA WEST', '阪神': 'JRA WEST', '中京': 'JRA WEST', '小倉': 'JRA WEST',
    '札幌': 'JRA HOKKAIDO', '函館': 'JRA HOKKAIDO',
}


def fetch_text(url, label='URL', timeout=30, headers=None):
    h = {
        'User-Agent': UA,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ja-JP,ja;q=0.9',
        'Cache-Control': 'no-cache',
    }
    if headers:
        h.update(headers)
    try:
        req = urllib.request.Request(url, headers=h)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            ctype = r.headers.get('Content-Type', '')
        encs = []
        m = re.search(r'charset=([A-Za-z0-9_\-]+)', ctype, re.I)
        if m:
            encs.append(m.group(1))
        encs += ['utf-8', 'cp932', 'shift_jis', 'euc_jp']
        best = ''
        for enc in dict.fromkeys(encs):
            try:
                text = raw.decode(enc)
                if not best or text.count('レース') + text.count('競輪') > best.count('レース') + best.count('競輪'):
                    best = text
            except Exception:
                pass
        return best or raw.decode('utf-8', errors='replace')
    except Exception as e:
        print(f'{label}: fetch failed: {e}')
        return ''


def plain_text(source):
    source = re.sub(r'(?is)<script.*?</script>', ' ', source or '')
    source = re.sub(r'(?is)<style.*?</style>', ' ', source)
    source = re.sub(r'(?s)<[^>]+>', ' ', source)
    source = html_lib.unescape(source)
    return re.sub(r'\s+', ' ', source).strip()


def fmt(dt):
    return dt.astimezone(JST).strftime('%Y%m%d%H%M%S +0900')


def parse_hhmm(day, value):
    h, m = map(int, str(value).split(':'))
    add, h = divmod(h, 24)
    return datetime.combine(day + timedelta(days=add), time(h, m), tzinfo=JST)


def ensure_channel(root, cid, name):
    if cid in {ch.get('id') for ch in root.findall('channel')}:
        return
    ch = ET.Element('channel', {'id': cid})
    ET.SubElement(ch, 'display-name').text = name
    root.append(ch)


def add_programme(root, cid, start, stop, title, desc=''):
    if stop <= start:
        return
    p = ET.Element('programme', {'channel': cid, 'start': fmt(start), 'stop': fmt(stop)})
    ET.SubElement(p, 'title', {'lang': 'ja'}).text = title
    if desc:
        ET.SubElement(p, 'desc', {'lang': 'ja'}).text = desc
    root.append(p)


def add_race_grid(root, cid, name, day, races, icon, mode_label, category, switch_after=3):
    if not races:
        return
    dts = []
    for race in races:
        try:
            dts.append((race, parse_hhmm(day, race['time'])))
        except Exception:
            pass
    if not dts:
        return
    day_start = datetime.combine(day, time(8, 0), tzinfo=JST)
    end_limit = datetime.combine(day + timedelta(days=1), time(1, 30), tzinfo=JST)
    for i, (race, dt) in enumerate(dts):
        start = day_start if i == 0 else dts[i - 1][1] + timedelta(minutes=switch_after)
        stop = dt + timedelta(minutes=switch_after)
        if stop <= start:
            stop = dt + timedelta(minutes=5)
        rn = str(race.get('race', i + 1)).translate(FULLWIDTH)
        rname = (race.get('name') or '競走').strip()
        title = f'【{rn}Ｒ】 {race["time"]}発走  {icon}【{rname} {icon}】'
        desc = f'{category} {name}\n開催区分: {mode_label}\n発走予定: {race["time"]}\n{rname}'
        add_programme(root, cid, start, min(stop, end_limit), title, desc)
    finish = dts[-1][1] + timedelta(minutes=switch_after)
    if finish < end_limit:
        add_programme(root, cid, finish, end_limit, f'🏁 本日の開催は終了しました {name}（{category}）', f'{name}の本日の開催は終了しました。')


def mode_from_times(races, category=''):
    if not races:
        return 'day', 'デイ'
    vals = [str(x.get('time') or '') for x in races if x.get('time')]
    if not vals:
        return 'day', 'デイ'
    first = int(vals[0].split(':')[0])
    last_h, last_m = map(int, vals[-1].split(':'))
    if category == 'auto' and last_h * 60 + last_m + 30 > 23 * 60 + 40:
        return 'overnight', 'オーバーミッドナイト'
    if first >= 19:
        return 'midnight', 'ミッドナイト'
    if last_h >= 20 or first >= 14:
        return 'night', 'ナイター'
    if first < 10:
        return 'morning', 'モーニング'
    return 'day', 'デイ'


class KeirinScheduleParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.in_tr = False
        self.in_td = False
        self.rows = []
        self.row = []
        self.cell = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == 'tr':
            self.in_tr = True
            self.row = []
        elif tag == 'td' and self.in_tr:
            self.in_td = True
            try:
                colspan = max(1, int(a.get('colspan', '1') or '1'))
            except Exception:
                colspan = 1
            self.cell = {'text': [], 'imgs': [], 'colspan': colspan}
        elif tag == 'img' and self.in_td and self.cell is not None:
            self.cell['imgs'].append({'src': a.get('src', ''), 'alt': a.get('alt', ''), 'title': a.get('title', '')})

    def handle_data(self, data):
        if self.in_td and self.cell is not None:
            s = re.sub(r'\s+', ' ', data).strip()
            if s:
                self.cell['text'].append(s)

    def handle_endtag(self, tag):
        if tag == 'td' and self.in_td:
            self.in_td = False
            self.row.append(self.cell)
            self.cell = None
        elif tag == 'tr' and self.in_tr:
            self.in_tr = False
            if self.row:
                self.rows.append(self.row)
            self.row = []


def keirin_month(year, month):
    src = fetch_text(KEIRIN_SCHEDULE_URL.format(year=year, month=f'{month:02d}'), f'KEIRIN schedule {year}-{month:02d}')
    if not src:
        return {}
    p = KeirinScheduleParser(); p.feed(src)
    out = {}
    for row in p.rows:
        if len(row) < 2:
            continue
        first = re.sub(r'\s+', '', ' '.join(row[0].get('text', [])))
        venue = next((v for v in KEIRIN_IDS if v in first), '')
        if not venue:
            continue
        logical_day = 1
        for cell in row[1:]:
            span = max(1, int(cell.get('colspan', 1)))
            combined = ' '.join(cell.get('text', []) + [x.get('alt', '') for x in cell.get('imgs', [])] + [x.get('title', '') for x in cell.get('imgs', [])])
            grade = ''
            mode, label = 'day', 'デイ'
            if 'ミッドナイト' in combined:
                mode, label = 'midnight', 'ミッドナイト'
            elif 'モーニング' in combined:
                mode, label = 'morning', 'モーニング'
            elif 'ナイター' in combined:
                mode, label = 'night', 'ナイター'
            for img in cell.get('imgs', []):
                base = img.get('src', '').rsplit('/', 1)[-1]
                if base in KEIRIN_GRADE_BY_SRC:
                    grade = KEIRIN_GRADE_BY_SRC[base]
                if base in KEIRIN_TYPE_BY_SRC:
                    mode, label = KEIRIN_TYPE_BY_SRC[base]
            if grade:
                for off in range(span):
                    day_num = logical_day + off
                    if day_num <= 31:
                        key = f'{year:04d}{month:02d}{day_num:02d}'
                        out.setdefault(key, {})[venue] = {'grade': grade, 'mode': mode, 'label': label}
            logical_day += span
    return out


def build_keirin(root, target_days, verified):
    months = {}
    for day in target_days:
        months.setdefault((day.year, day.month), keirin_month(day.year, day.month))
    today = target_days[0]
    for day in target_days:
        schedule = months[(day.year, day.month)].get(day.strftime('%Y%m%d'), {})
        for venue, meta in schedule.items():
            cid = KEIRIN_IDS.get(venue)
            if not cid:
                continue
            ensure_channel(root, cid, venue)
            if day == today:
                races = keirin_direct.fetch_venue(venue, day.strftime('%Y%m%d'))
                if races:
                    mode, label = mode_from_times(races)
                    add_race_grid(root, cid, venue, day, races, '🚲', label, '競輪', switch_after=3)
                else:
                    mode, label = meta['mode'], meta['label']
                    s, e = KEIRIN_PROVISIONAL.get(mode, KEIRIN_PROVISIONAL['day'])
                    add_programme(root, cid, parse_hhmm(day, s), parse_hhmm(day, e), f'{venue} 【{meta["grade"]}】 {label} 開催予定（仮時間）', 'KEIRIN.JP公式開催表で開催確認済み。実時刻未取得のため仮時間です。')
                verified['public_sports']['競輪'].append(venue)
                verified['public_sports_modes']['競輪'][venue] = meta['mode'] if not races else mode
            else:
                s, e = KEIRIN_PROVISIONAL.get(meta['mode'], KEIRIN_PROVISIONAL['day'])
                add_programme(root, cid, parse_hhmm(day, s), parse_hhmm(day, e), f'{venue} 【{meta["grade"]}】 {meta["label"]} 開催予定（仮時間）', 'KEIRIN.JP公式開催表を基にした将来日の仮時間EPGです。')


def nar_races(day, venue, code):
    date_param = urllib.parse.quote(day.strftime('%Y/%m/%d'), safe='')
    src = fetch_text(NAR_URL.format(code=code, date=date_param), f'NAR {day} {venue}')
    text = plain_text(src)
    if venue not in text or '当日メニュー' not in text:
        return []
    row_re = re.compile(r'\b(\d{1,2})R\b\s+([0-2]?\d:[0-5]\d)\s+(.*?)(?=\s+\d{1,2}R\s+[0-2]?\d:[0-5]\d|\s+重賞競走優勝馬検索|\Z)', re.S)
    out = []
    for m in row_re.finditer(text):
        n = int(m.group(1))
        if not 1 <= n <= 12:
            continue
        tail = re.sub(r'\s+', ' ', m.group(3)).strip()
        name = re.split(r'\s+(?:右|左|直線)\d+m|\s+オッズ\b|\s+映像\b|\s+成績\b', tail, maxsplit=1)[0].strip()
        out.append({'race': n, 'time': m.group(2).zfill(5), 'name': name or '競走'})
    return out


def build_nar(root, target_days, verified):
    for day in target_days:
        for venue, (code, cid) in NAR.items():
            races = nar_races(day, venue, code)
            if not races:
                continue
            ensure_channel(root, cid, venue)
            mode, label = mode_from_times(races)
            add_race_grid(root, cid, venue, day, races, '🏇', label, '地方競馬', switch_after=3)
            if day == target_days[0]:
                verified['public_sports']['地方競馬'].append(venue)
                verified['public_sports_modes']['地方競馬'][venue] = mode


def boat_codes(day):
    src = fetch_text(BOAT_INDEX.format(date=day.strftime('%Y%m%d')), f'BOAT index {day}')
    return sorted(set(re.findall(r'(?:[?&]|&amp;)jcd=(\d{2})', src)))


def boat_races(day, code):
    src = fetch_text(BOAT_RACE.format(date=day.strftime('%Y%m%d'), code=code), f'BOAT {day} {code}')
    text = plain_text(src)
    found = {}
    for m in re.finditer(r'(?<!\d)(1[0-2]|[1-9])R\s+([0-2][0-9]:[0-5][0-9])', text):
        found.setdefault(int(m.group(1)), m.group(2))
    return [{'race': n, 'time': found[n], 'name': 'ボートレース'} for n in sorted(found)]


def build_boat(root, target_days, verified):
    for day in target_days:
        for code in boat_codes(day):
            if code not in BOAT:
                continue
            venue, cid = BOAT[code]
            races = boat_races(day, code)
            ensure_channel(root, cid, f'BOATRACE{venue}')
            if races:
                mode, label = mode_from_times(races)
                add_race_grid(root, cid, f'BOATRACE{venue}', day, races, '🚤', label, 'ボートレース', switch_after=3)
            else:
                mode, label = 'day', 'デイ'
                add_programme(root, cid, datetime.combine(day, time(10, 0), tzinfo=JST), datetime.combine(day, time(18, 0), tzinfo=JST), f'BOATRACE{venue} 開催予定／発走時刻確認待ち', 'BOAT RACE公式の開催一覧で開催確認済み。')
            if day == target_days[0]:
                verified['public_sports']['ボートレース'].append(venue)
                verified['public_sports_modes']['ボートレース'][venue] = mode


def auto_races(day, venue, slug, full=True):
    out = []
    nums = range(1, 13) if full else (1,)
    date = day.isoformat()
    for n in nums:
        race = None
        for template in auto_direct.PROGRAM_URLS:
            src = fetch_text(template.format(slug=slug, date=date, race_no=n), f'AUTO {day} {venue} {n}R', timeout=20, headers={'Referer': 'https://autorace.jp/race_info/'})
            race = auto_direct.parse_program(src, n)
            if race:
                break
        if race:
            out.append(race)
        elif not full:
            break
    return out


def build_auto(root, target_days, verified):
    for day in target_days:
        for venue, (cid, slug) in AUTO.items():
            races = auto_races(day, venue, slug, full=(day == target_days[0]))
            if not races:
                continue
            ensure_channel(root, cid, f'{venue}オート')
            if day == target_days[0]:
                mode, label = mode_from_times(races, 'auto')
                add_race_grid(root, cid, f'{venue}オート', day, races, '🏍️', label, 'オートレース', switch_after=3)
                verified['public_sports']['オートレース'].append(venue)
                verified['public_sports_modes']['オートレース'][venue] = mode
            else:
                mode, label = mode_from_times(races, 'auto')
                start = parse_hhmm(day, races[0]['time']) - timedelta(minutes=20)
                stop = parse_hhmm(day, races[-1]['time']) + timedelta(minutes=30)
                add_programme(root, cid, start, stop, f'{venue}オート {label} 開催予定', f'AutoRace.JP公式出走表で{day.isoformat()}の開催を確認。')


def jra_url(day):
    year = day.strftime('%Y'); month = str(int(day.strftime('%m'))); mmdd = day.strftime('%m%d')
    return f'https://www.jra.go.jp/keiba/calendar{year}/{year}/{month}/{mmdd}.html'


def fetch_jra(day):
    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    headers = {'User-Agent': UA, 'Accept-Language': 'ja-JP,ja;q=0.9', 'Cache-Control': 'no-cache'}
    try:
        try:
            opener.open(urllib.request.Request('https://www.jra.go.jp/', headers=headers), timeout=20).read(1)
        except Exception:
            pass
        req = urllib.request.Request(jra_url(day), headers={**headers, 'Referer': 'https://www.jra.go.jp/keiba/calendar/'})
        with opener.open(req, timeout=30) as r:
            raw = r.read()
        best = ''
        for enc in ('utf-8', 'cp932', 'shift_jis', 'euc_jp'):
            try:
                s = raw.decode(enc)
                if not best or sum(s.count(x) for x in JRA_VENUE_STREAM) > sum(best.count(x) for x in JRA_VENUE_STREAM):
                    best = s
            except Exception:
                pass
        text = plain_text(best or raw.decode('utf-8', errors='replace'))
    except Exception as e:
        print(f'JRA {day}: fetch failed: {e}')
        return {}
    meeting_re = re.compile(r'(\d+)\s*回\s*(東京|中山|新潟|福島|京都|阪神|中京|小倉|札幌|函館)\s*(\d+)\s*日')
    heads = list(meeting_re.finditer(text)); out = {}
    for i, m in enumerate(heads):
        venue = m.group(2)
        section = text[m.end(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        races = []
        for r in re.finditer(r'(\d{1,2})\s*レース\s+(.*?)\s+([0-2]?\d)\s*時\s*([0-5]\d)\s*分', section, re.S):
            n = int(r.group(1))
            if 1 <= n <= 12:
                races.append({'race': n, 'time': f'{int(r.group(3)):02d}:{r.group(4)}', 'name': re.sub(r'\s+', ' ', r.group(2)).strip()[:160] or 'JRA競走'})
        if len(races) >= 5:
            out[venue] = races
    return out


def build_jra(root, target_days, verified):
    for day in target_days:
        meetings = fetch_jra(day)
        grouped = {k: [] for k in JRA_STREAMS}
        for venue, races in meetings.items():
            stream = JRA_VENUE_STREAM.get(venue)
            if stream:
                grouped[stream].extend((venue, r) for r in races)
        for stream, cid in JRA_STREAMS.items():
            flat = grouped[stream]
            if not flat:
                continue
            ensure_channel(root, cid, stream)
            rows = []
            for venue, race in flat:
                rows.append((parse_hhmm(day, race['time']), venue, race))
            rows.sort(key=lambda x: x[0])
            day_start = datetime.combine(day, time(8, 0), tzinfo=JST)
            for i, (dt, venue, race) in enumerate(rows):
                start = day_start if i == 0 else rows[i - 1][0] + timedelta(minutes=3)
                stop = dt + timedelta(minutes=3)
                title = f'【{str(race["race"]).translate(FULLWIDTH)}Ｒ】 {race["time"]}発走  🏇【{venue} {race["name"]} 🏇】'
                add_programme(root, cid, start, stop, title, f'JRA {venue}\n発走予定: {race["time"]}\n{race["name"]}')
            if day == target_days[0]:
                verified['jra_active_ids'].append(cid)


def sort_xml(root):
    channels = [x for x in list(root) if x.tag == 'channel']
    programmes = [x for x in list(root) if x.tag == 'programme']
    programmes.sort(key=lambda p: (p.get('start', ''), p.get('channel', '')))
    for x in list(root):
        root.remove(x)
    seen = set()
    for ch in channels:
        if ch.get('id') in seen:
            continue
        seen.add(ch.get('id')); root.append(ch)
    for p in programmes:
        root.append(p)


def main():
    now = datetime.now(JST)
    days = [now.date() + timedelta(days=i) for i in range(DAYS)]
    root = ET.Element('tv', {'generator-info-name': 'ajiousama/himitsu local public sports EPG'})
    verified = {
        'date': now.date().isoformat(),
        'checked_at': now.isoformat(),
        'public_sports': {'競輪': [], '地方競馬': [], 'ボートレース': [], 'オートレース': []},
        'public_sports_modes': {'競輪': {}, '地方競馬': {}, 'ボートレース': {}, 'オートレース': {}},
        'jra_active_ids': [],
        'source': 'ajiousama/himitsu direct official acquisition',
    }

    build_keirin(root, days, verified)
    build_nar(root, days, verified)
    build_boat(root, days, verified)
    build_auto(root, days, verified)
    build_jra(root, days, verified)

    for section in verified['public_sports']:
        verified['public_sports'][section] = list(dict.fromkeys(verified['public_sports'][section]))
    verified['jra_active_ids'] = list(dict.fromkeys(verified['jra_active_ids']))

    sort_xml(root)
    tree = ET.ElementTree(root); ET.indent(tree, space='  ')
    tree.write(OUT, encoding='utf-8', xml_declaration=True)
    VERIFIED.write_text(json.dumps(verified, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    print('LOCAL PUBLIC SPORTS EPG:', OUT, 'programmes=', len(root.findall('programme')))
    for section, venues in verified['public_sports'].items():
        print(section, len(venues), ', '.join(venues))
    print('JRA', len(verified['jra_active_ids']), verified['jra_active_ids'])


if __name__ == '__main__':
    main()
