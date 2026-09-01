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

KEIRIN_IDS = {
    '函館': 'keirin.hakodate', '青森': 'keirin.aomori', 'いわき平': 'keirin.iwakitaira',
    '弥彦': 'keirin.yahiko', '前橋': 'keirin.maebashi', '取手': 'keirin.toride',
    '宇都宮': 'keirin.utsunomiya', '大宮': 'keirin.omiya', '西武園': 'keirin.seibuen',
    '京王閣': 'keirin.keiogatsu', '立川': 'keirin.tachikawa', '松戸': 'keirin.matsudo',
    '川崎': 'keirin.kawasaki', '平塚': 'keirin.hiratsuka', '小田原': 'keirin.odawara',
    '伊東': 'keirin.ito', '静岡': 'keirin.shizuoka', '名古屋': 'keirin.nagoya',
    '岐阜': 'keirin.gifu', '大垣': 'keirin.ogaki', '豊橋': 'keirin.toyohashi',
    '富山': 'keirin.toyama', '松阪': 'keirin.matsusaka', '四日市': 'keirin.yokkaichi',
    '福井': 'keirin.fukui', '奈良': 'keirin.nara', '向日町': 'keirin.mukomachi',
    '和歌山': 'keirin.wakayama', '岸和田': 'keirin.kishiwada', '玉野': 'keirin.tamano',
    '広島': 'keirin.hiroshima', '防府': 'keirin.hofu', '高松': 'keirin.takamatsu',
    '小松島': 'keirin.komatsushima', '高知': 'keirin.kochi', '松山': 'keirin.matsuyama',
    '小倉': 'keirin.kokura', '久留米': 'keirin.kurume', '武雄': 'keirin.takeo',
    '佐世保': 'keirin.sasebo', '別府': 'keirin.beppu', '熊本': 'keirin.kumamoto',
}

VENUE_CODE = {
    '函館': '11', '青森': '12', 'いわき平': '13',
    '弥彦': '21', '前橋': '22', '取手': '23', '宇都宮': '24',
    '大宮': '25', '西武園': '26', '京王閣': '27', '立川': '28',
    '松戸': '31', '千葉': '32', '川崎': '34', '平塚': '35',
    '小田原': '36', '伊東': '37', '静岡': '38',
    '名古屋': '42', '岐阜': '43', '大垣': '44', '豊橋': '45',
    '富山': '46', '松阪': '47', '四日市': '48',
    '福井': '51', '奈良': '53', '向日町': '54', '和歌山': '55',
    '岸和田': '56', '玉野': '61', '広島': '62', '防府': '63',
    '高松': '71', '小松島': '73', '高知': '74', '松山': '75',
    '小倉': '81', '久留米': '83', '武雄': '84', '佐世保': '85',
    '別府': '86', '熊本': '87',
}

MODE_LABEL = {
    'morning': 'モーニング', 'day': 'デイ', 'twilight': '薄暮',
    'night': 'ナイター', 'midnight': 'ミッドナイト', 'overnight': 'オーバーミッドナイト',
}
MODE_ICON = {
    'morning': '🌅', 'day': '☀️', 'twilight': '🌇',
    'night': '🌙', 'midnight': '⭐', 'overnight': '🌌',
}

RACE_URL = 'https://keirin.netkeiba.com/race/entry/?race_id={race_id}'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151.0 Safari/537.36'
FULLWIDTH = str.maketrans('0123456789', '０１２３４５６７８９')


def fetch(url, label):
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ja-JP,ja;q=0.9',
        'Referer': 'https://keirin.netkeiba.com/',
        'Cache-Control': 'no-cache',
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read().decode('utf-8', errors='replace')
    except Exception as e:
        print(f'{label}: fetch failed: {e}')
        return ''


def plain_text(source):
    source = re.sub(r'(?is)<script.*?</script>', ' ', source or '')
    source = re.sub(r'(?is)<style.*?</style>', ' ', source)
    source = re.sub(r'(?s)<[^>]+>', ' ', source)
    source = html.unescape(source)
    return re.sub(r'\s+', ' ', source).strip()


def clean(s):
    return re.sub(r'\s+', ' ', html.unescape(str(s or ''))).strip()


def race_numbers(source, date_str, code):
    prefix = f'{date_str}{code}'
    nums = set()
    for m in re.finditer(rf'race_id={re.escape(prefix)}(\d{{2}})', source or ''):
        n = int(m.group(1))
        if 1 <= n <= 12:
            nums.add(n)
    return sorted(nums)


def parse_race(source, venue, date_str, race_no):
    if not source:
        return None
    plain = plain_text(source)
    if venue not in plain:
        return None

    mt = re.search(r'発走\s*([0-2]?\d:[0-5]\d)', plain)
    if not mt:
        return None
    hhmm = mt.group(1).zfill(5)

    title_text = ''
    m = re.search(r'(?is)<title[^>]*>(.*?)</title>', source)
    if m:
        title_text = clean(plain_text(m.group(1)))

    race_name = ''
    event_name = ''
    race_class = ''
    if title_text:
        mr = re.search(
            rf'{re.escape(date_str[:4])}年{int(date_str[4:6]):02d}月{int(date_str[6:8]):02d}日\s*'
            rf'{race_no}R\s+(.+?)\s+出走表', title_text,
        )
        if mr:
            race_name = clean(mr.group(1))
        me = re.search(
            rf'{re.escape(venue)}競輪\s+(.+?)\s+(?:GP|G[1-3I]+|F[12I]+)\s+{re.escape(date_str[:4])}年',
            title_text, flags=re.I,
        )
        if me:
            event_name = clean(me.group(1))

    mc = re.search(
        r'([SＳAＡLＬ]級\s*[^ ]{1,12}(?:\s*[^ ]{1,12})?)\s+発走\s*[0-2]?\d:[0-5]\d',
        plain,
    )
    if mc:
        race_class = clean(mc.group(1))
    if not race_name and race_class:
        race_name = re.sub(r'^[SＳAＡLＬ]級\s*', '', race_class).strip()
    if not race_name:
        race_name = '競走'

    girls = bool(re.search(r'[LＬ]級|ガールズ', race_class + ' ' + race_name))
    return {
        'race': race_no, 'time': hhmm, 'name': race_name,
        'race_class': race_class or ('L級' if girls else '競輪'),
        'girls': girls, 'event_name': event_name,
    }


def fetch_venue(venue, date_str):
    code = VENUE_CODE.get(venue)
    if not code:
        print(f'KEIRIN {venue}: venue code missing')
        return []
    first_id = f'{date_str}{code}01'
    first = fetch(RACE_URL.format(race_id=first_id), f'KEIRIN {venue} 1R')
    if not first:
        return []
    nums = race_numbers(first, date_str, code)
    if 1 not in nums:
        nums.insert(0, 1)
    nums = sorted(set(n for n in nums if 1 <= n <= 12))
    if len(nums) <= 1:
        nums = list(range(1, 13))

    out = []
    misses = 0
    for n in nums:
        page = first if n == 1 else fetch(
            RACE_URL.format(race_id=f'{date_str}{code}{n:02d}'),
            f'KEIRIN {venue} {n}R',
        )
        race = parse_race(page, venue, date_str, n)
        if not race:
            misses += 1
            if misses >= 2 and len(nums) == 12:
                break
            continue
        misses = 0
        out.append(race)
    out.sort(key=lambda x: x['race'])
    print(f'KEIRIN DIRECT {venue}: {len(out)}R')
    return out


def parse_xmltv(v):
    m = re.match(r'^(\d{14})\s*([+-]\d{4})?', str(v or '').strip())
    if not m:
        return None
    d, off = m.groups()
    if off:
        return datetime.strptime(f'{d} {off}', '%Y%m%d%H%M%S %z').astimezone(JST)
    return datetime.strptime(d, '%Y%m%d%H%M%S').replace(tzinfo=JST)


def fmt(dt):
    return dt.astimezone(JST).strftime('%Y%m%d%H%M%S +0900')


def add_programme(root, cid, start, stop, title, desc):
    if stop <= start:
        return
    p = ET.Element('programme', {'channel': cid, 'start': fmt(start), 'stop': fmt(stop)})
    ET.SubElement(p, 'title', {'lang': 'ja'}).text = title
    ET.SubElement(p, 'desc', {'lang': 'ja'}).text = desc
    root.append(p)


def remove_today(root, cid, today):
    removed = 0
    for p in list(root.findall('programme')):
        if p.get('channel') != cid:
            continue
        s = parse_xmltv(p.get('start'))
        e = parse_xmltv(p.get('stop'))
        if not s:
            continue
        if s.date() == today or (e and s.date() < today <= e.date()):
            root.remove(p)
            removed += 1
    return removed


def load_verified(now):
    if not VERIFIED.exists():
        return [], {}
    try:
        cfg = json.loads(VERIFIED.read_text(encoding='utf-8-sig'))
    except Exception:
        return [], {}
    if cfg.get('date') != now.date().isoformat():
        return [], {}
    venues = (cfg.get('public_sports') or {}).get('競輪') or []
    modes = (cfg.get('public_sports_modes') or {}).get('競輪') or {}
    return venues, modes


def main():
    now = datetime.now(JST)
    venues, modes = load_verified(now)
    if not venues:
        print('KEIRIN DIRECT: no verified venues today')
        return

    tree = ET.parse(GUIDES)
    root = tree.getroot()
    date_str = now.strftime('%Y%m%d')
    today = now.date()
    rebuilt = 0
    races_total = 0

    for venue in venues:
        cid = KEIRIN_IDS.get(venue)
        if not cid:
            print(f'KEIRIN DIRECT {venue}: tvg-id missing')
            continue
        races = fetch_venue(venue, date_str)
        if not races:
            print(f'KEIRIN DIRECT {venue}: preserve upstream EPG')
            continue

        removed = remove_today(root, cid, today)
        mode = modes.get(venue, 'day')
        mode_label = MODE_LABEL.get(mode, 'デイ')
        mode_icon = MODE_ICON.get(mode, '☀️')
        day_start = datetime.combine(today, time(8, 0), tzinfo=JST)
        day_end = datetime.combine(today, time(23, 59), tzinfo=JST)

        race_dts = []
        for race in races:
            hh, mm = map(int, race['time'].split(':'))
            race_dts.append((race, datetime.combine(today, time(hh, mm), tzinfo=JST)))

        pre_start = max(day_start, race_dts[0][1] - timedelta(minutes=20))
        if day_start < pre_start:
            add_programme(
                root, cid, day_start, pre_start,
                f'⏳ 開催待ち {venue} {mode_icon}{mode_label} 1R {races[0]["time"]}発走予定',
                f'🚲 競輪 {venue}\n{mode_icon} 開催区分: {mode_label}\n1R発走予定 {races[0]["time"]}',
            )

        for idx, (race, dt) in enumerate(race_dts):
            start = max(pre_start, dt - timedelta(minutes=8))
            if idx + 1 < len(race_dts):
                stop = race_dts[idx + 1][1] - timedelta(minutes=8)
            else:
                stop = dt + timedelta(minutes=25)
            if stop <= start:
                stop = dt + timedelta(minutes=12)

            n = str(race['race']).translate(FULLWIDTH)
            icon = '💛' if race['girls'] else '🚲'
            race_name = race['name']
            title = f'【{n}Ｒ】 {race["time"]}発走  {icon}【{race_name} {icon}】'
            desc = (
                f'🚲 競輪 {venue}\n'
                f'{mode_icon} 開催区分: {mode_label}\n'
                f'⏰ 発走予定: {race["time"]}\n'
                f'🏷️ {race["race_class"]}'
            )
            if race.get('event_name'):
                desc += f'\n📢 開催名: {race["event_name"]}'
            add_programme(root, cid, start, min(stop, day_end), title, desc)

        finish = race_dts[-1][1] + timedelta(minutes=25)
        if finish < day_end:
            add_programme(
                root, cid, finish, day_end,
                f'🏁✨ 本日の開催は終了しました 🚲🌙 {venue}（競輪）',
                f'{venue}の本日の競輪は全て終了しました。',
            )

        rebuilt += 1
        races_total += len(races)
        print(f'KEIRIN DIRECT {venue}: replaced={removed} programmes, races={len(races)}')

    programmes = list(root.findall('programme'))
    for p in programmes:
        root.remove(p)
    programmes.sort(key=lambda p: (parse_xmltv(p.get('start')) or datetime.max.replace(tzinfo=JST), p.get('channel', '')))
    for p in programmes:
        root.append(p)

    ET.indent(tree, space='  ')
    tree.write(GUIDES, encoding='utf-8', xml_declaration=True)
    print(f'KEIRIN DIRECT complete: venues={rebuilt}/{len(venues)}, races={races_total}')


if __name__ == '__main__':
    main()
