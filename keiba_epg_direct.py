from pathlib import Path
from datetime import datetime, timezone, timedelta, time
import html
import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

GUIDES = Path('guides.xml')
VERIFIED = Path('verified_daily_status.json')
JST = timezone(timedelta(hours=9))

VENUE_CODES = {
    '帯広': '03', '盛岡': '10', '水沢': '11', '浦和': '18', '船橋': '19',
    '大井': '20', '川崎': '21', '金沢': '22', '笠松': '23', '名古屋': '24',
    '園田': '27', '姫路': '28', '高知': '31', '佐賀': '32', '門別': '36',
}
TVG_IDS = {
    '帯広': 'chihou.obihiro', '門別': 'chihou.mombetsu', '盛岡': 'chihou.morioka',
    '水沢': 'chihou.mizusawa', '浦和': 'chihou.urawa', '船橋': 'chihou.funabashi',
    '大井': 'chihou.oi', '川崎': 'chihou.kawasaki_keiba', '金沢': 'chihou.kanazawa',
    '名古屋': 'chihou.nagoya_keiba', '笠松': 'chihou.kasamatsu', '園田': 'chihou.sonoda',
    '姫路': 'chihou.himeji', '高知': 'chihou.kochi_keiba', '佐賀': 'chihou.saga',
}
RACE_LIST_URL = (
    'https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo/RaceList'
    '?k_babaCode={code}&k_raceDate={date}'
)
FULLWIDTH = str.maketrans('0123456789', '０１２３４５６７８９')


def fetch_text(url, label):
    req = urllib.request.Request(url, headers={
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'ja-JP,ja;q=0.9',
        'Referer': 'https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo/TodayRaceInfoTop',
        'Cache-Control': 'no-cache',
    })
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
        for enc in ('utf-8', 'cp932', 'shift_jis'):
            try:
                return raw.decode(enc)
            except Exception:
                pass
        return raw.decode('utf-8', errors='replace')
    except Exception as e:
        print(f'NAR {label}: fetch failed: {e}')
        return ''


def plain_text(source):
    source = re.sub(r'(?is)<script.*?</script>', ' ', source or '')
    source = re.sub(r'(?is)<style.*?</style>', ' ', source)
    source = re.sub(r'(?s)<[^>]+>', ' ', source)
    source = html.unescape(source)
    return re.sub(r'\s+', ' ', source).strip()


def load_verified_venues(today):
    try:
        cfg = json.loads(VERIFIED.read_text(encoding='utf-8-sig'))
    except Exception as e:
        raise SystemExit(f'Cannot read verified_daily_status.json: {e}')
    if cfg.get('date') != today.isoformat():
        raise SystemExit(f'Verified schedule date mismatch: {cfg.get("date")} != {today.isoformat()}')
    return (cfg.get('public_sports') or {}).get('地方競馬') or []


def parse_races(source, venue):
    text = plain_text(source)
    if venue not in text or '当日メニュー' not in text:
        return []

    row_re = re.compile(
        r'\b(\d{1,2})R\b\s+([0-2]?\d:[0-5]\d)\s+(.*?)'
        r'(?=\s+\d{1,2}R\s+[0-2]?\d:[0-5]\d|\s+重賞競走優勝馬検索|\Z)',
        flags=re.S,
    )
    races = {}
    for m in row_re.finditer(text):
        n = int(m.group(1))
        if not 1 <= n <= 12:
            continue
        hhmm = m.group(2)
        if len(hhmm) == 4:
            hhmm = '0' + hhmm
        tail = re.sub(r'\s+', ' ', m.group(3)).strip()
        name = re.split(
            r'\s+(?:右|左|直線)\d+m|\s+オッズ\b|\s+映像\b|\s+成績\b',
            tail,
            maxsplit=1,
        )[0].strip()
        races[n] = {'race': n, 'time': hhmm, 'name': name or '競走'}
    return [races[n] for n in sorted(races)]


def parse_xmltv(value):
    m = re.match(r'^(\d{14})\s*([+-]\d{4})?', str(value or '').strip())
    if not m:
        return None
    base = datetime.strptime(m.group(1), '%Y%m%d%H%M%S')
    off = m.group(2)
    if not off:
        return base.replace(tzinfo=JST)
    sign = 1 if off[0] == '+' else -1
    tz = timezone(sign * timedelta(hours=int(off[1:3]), minutes=int(off[3:5])))
    return base.replace(tzinfo=tz).astimezone(JST)


def fmt(dt):
    return dt.astimezone(JST).strftime('%Y%m%d%H%M%S +0900')


def add_programme(root, cid, start, stop, title, desc):
    if stop <= start:
        return
    p = ET.Element('programme', {'channel': cid, 'start': fmt(start), 'stop': fmt(stop)})
    ET.SubElement(p, 'title', {'lang': 'ja'}).text = title
    ET.SubElement(p, 'desc', {'lang': 'ja'}).text = desc
    root.append(p)


def race_title(race):
    marker = f"【{str(race['race']).translate(FULLWIDTH)}Ｒ】"
    return f"{marker}  {race['time']}発走  🏇【{race['name']} 🏇】  🔴📺 ただいま実況放送中！！！ 📺🔴"


def main():
    now = datetime.now(JST)
    today = now.date()
    venues = load_verified_venues(today)
    if not venues:
        raise SystemExit('No verified local horse racing venues for today')

    tree = ET.parse(GUIDES)
    root = tree.getroot()
    day_start = datetime.combine(today, time(8, 0), tzinfo=JST)
    day_end = datetime.combine(today + timedelta(days=1), time(0, 0), tzinfo=JST)

    repaired = []
    preserved = []
    for venue in venues:
        code = VENUE_CODES.get(venue)
        cid = TVG_IDS.get(venue)
        if not code or not cid:
            print(f'NAR {venue}: mapping missing; preserve existing EPG')
            preserved.append(venue)
            continue

        date_param = urllib.parse.quote(today.strftime('%Y/%m/%d'), safe='')
        source = fetch_text(RACE_LIST_URL.format(code=code, date=date_param), venue)
        races = parse_races(source, venue)
        if len(races) < 5:
            print(f'NAR {venue}: only {len(races)} races parsed; preserve existing EPG')
            preserved.append(venue)
            continue

        # Remove only today's programmes for this venue after successful official fetch.
        for p in list(root.findall('programme')):
            if p.get('channel') != cid:
                continue
            s = parse_xmltv(p.get('start'))
            e = parse_xmltv(p.get('stop'))
            if s and e and e > day_start and s < day_end:
                root.remove(p)

        race_dts = []
        for race in races:
            hh, mm = map(int, race['time'].split(':'))
            dt = datetime.combine(today, time(hh, mm), tzinfo=JST)
            race_dts.append((race, dt))

        first_race, first_dt = race_dts[0]
        first_start = day_start
        for idx, (race, race_dt) in enumerate(race_dts):
            # EPG shows the upcoming/current race continuously and switches 3 minutes after departure.
            start = first_start if idx == 0 else race_dts[idx - 1][1] + timedelta(minutes=3)
            stop = race_dt + timedelta(minutes=3)
            if stop <= start:
                stop = race_dt + timedelta(minutes=5)
            add_programme(
                root, cid, start, min(stop, day_end), race_title(race),
                f"🏇 地方競馬 {venue}\n⏰ 発走予定: {race['time']}\n📢 {race['name']}\n📅 {today.isoformat()}\n出典: 地方競馬情報サイト（NAR）",
            )

        finish = race_dts[-1][1] + timedelta(minutes=3)
        if finish < day_end:
            add_programme(
                root, cid, finish, day_end,
                f'🏁✨ 本日の開催は終了しました 🏇🌙 {venue}（地方競馬）',
                f'{venue}の本日の地方競馬は全レース終了しました。',
            )
        repaired.append(venue)
        print(f'NAR DIRECT {venue}: {len(races)}R {races[0]["time"]}-{races[-1]["time"]}')

    programmes = list(root.findall('programme'))
    for p in programmes:
        root.remove(p)
    programmes.sort(key=lambda p: (parse_xmltv(p.get('start')) or datetime.max.replace(tzinfo=JST), p.get('channel', '')))
    for p in programmes:
        root.append(p)

    ET.indent(tree, space='  ')
    tree.write(GUIDES, encoding='utf-8', xml_declaration=True)
    print(f'NAR direct EPG repaired={len(repaired)} preserved={len(preserved)}')
    print('repaired:', ', '.join(repaired) if repaired else 'none')
    print('preserved:', ', '.join(preserved) if preserved else 'none')


if __name__ == '__main__':
    main()
