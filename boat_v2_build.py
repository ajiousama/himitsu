from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import base64
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request

FREEWIFI = Path('freewifi')
STATUS = Path('today_boat_status.json')
STATE = Path('boat_v2_state.json')
SEED = Path('boat_stream_seed.m3u')
START = '# === TODAY_BOAT_START ==='
END = '# === TODAY_BOAT_END ==='
PUBLIC_START = '# === TODAY_PUBLIC_SPORTS_START ==='
PUBLIC_END = '# === TODAY_PUBLIC_SPORTS_END ==='
GROUP = '今日の開催場'
JST = timezone(timedelta(hours=9))
PRESTART_MINUTES = 30
GRACE_MINUTES = 30
API = 'https://boatraceopenapi.github.io/api/v1/{year}/{ymd}.json'
RESOLVER_BASE = 'https://ajiousama-radiko.onrender.com/boat'
RESOLVER = RESOLVER_BASE + '/{jcd}'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152 Safari/537.36'

VENUES = {
    '01': ('桐生', 'boat.kiryu', 'https://www.boatrace.jp/static/uploads/sites/8/01_N.jpg'),
    '02': ('戸田', 'boat.toda', 'https://www.boatrace.jp/static/uploads/sites/8/02_N-1.jpg'),
    '03': ('江戸川', 'boat.edogawa', 'https://www.boatrace.jp/static/uploads/sites/8/03_N-1.jpg'),
    '04': ('平和島', 'boat.heiwajima', 'https://www.boatrace.jp/static/uploads/sites/8/04_N-1.jpg'),
    '05': ('多摩川', 'boat.tamagawa', 'https://www.boatrace.jp/static/uploads/sites/8/05_N.jpg'),
    '06': ('浜名湖', 'boat.hamanako', 'https://www.boatrace.jp/static/uploads/sites/8/06_N.jpg'),
    '07': ('蒲郡', 'boat.gamagori', 'https://www.boatrace.jp/static/uploads/sites/8/07_N.jpg'),
    '08': ('常滑', 'boat.tokoname', 'https://www.boatrace.jp/static/uploads/sites/8/08_N.jpg'),
    '09': ('津', 'boat.tsu', 'https://www.boatrace.jp/static/uploads/sites/8/09_N-1-1.jpg'),
    '10': ('三国', 'boat.mikuni', 'https://www.boatrace.jp/static/uploads/sites/8/10_N-1-1.jpg'),
    '11': ('びわこ', 'boat.biwako', 'https://www.boatrace.jp/static/uploads/sites/8/11_N-1.jpg'),
    '12': ('住之江', 'boat.suminoe', 'https://www.boatrace.jp/static/uploads/sites/8/12_N-1-1.jpg'),
    '13': ('尼崎', 'boat.amagasaki', 'https://www.boatrace.jp/static/uploads/sites/8/13_N-1.jpg'),
    '14': ('鳴門', 'boat.naruto', 'https://www.boatrace.jp/static/uploads/sites/8/14_N-1.jpg'),
    '15': ('丸亀', 'boat.marugame', 'https://www.boatrace.jp/static/uploads/sites/8/15_N-1.jpg'),
    '16': ('児島', 'boat.kojima', 'https://www.boatrace.jp/static/uploads/sites/8/16_N-1.jpg'),
    '17': ('宮島', 'boat.miyajima', 'https://www.boatrace.jp/static/uploads/sites/8/17_N-1.jpg'),
    '18': ('徳山', 'boat.tokuyama', 'https://www.boatrace.jp/static/uploads/sites/8/18_N-1.jpg'),
    '19': ('下関', 'boat.shimonoseki', 'https://www.boatrace.jp/static/uploads/sites/8/19_N-1.jpg'),
    '20': ('若松', 'boat.wakamatsu', 'https://www.boatrace.jp/static/uploads/sites/8/20_N-1.jpg'),
    '21': ('芦屋', 'boat.ashiya', 'https://www.boatrace.jp/static/uploads/sites/8/21_N-1.jpg'),
    '22': ('福岡', 'boat.fukuoka', 'https://www.boatrace.jp/static/uploads/sites/8/22_N-1-1.jpg'),
    '23': ('唐津', 'boat.karatsu', 'https://www.boatrace.jp/static/uploads/sites/8/23_N-1.jpg'),
    '24': ('大村', 'boat.omura', 'https://www.boatrace.jp/static/uploads/sites/8/24_N-1.jpg'),
}


def fetch_snapshot(day):
    url = API.format(year=day.strftime('%Y'), ymd=day.strftime('%Y%m%d'))
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json', 'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode('utf-8'))


def parse_closed(value, day):
    value = str(value or '').strip()
    if not value:
        return None
    for fmt in ('%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S'):
        try:
            dt = datetime.strptime(value[:19], fmt).replace(tzinfo=JST)
            if dt.date() == day:
                return dt
        except Exception:
            pass
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=JST)
        else:
            dt = dt.astimezone(JST)
        return dt if dt.date() == day else None
    except Exception:
        return None


def cards_from_snapshot(data, day):
    stadiums = (((data or {}).get('programs') or {}).get('stadiums') or {})
    out = {}
    for raw_code, stadium in stadiums.items():
        try:
            jcd = f'{int(raw_code):02d}'
        except Exception:
            continue
        if jcd not in VENUES:
            continue
        races = []
        for rkey, race in ((stadium or {}).get('races') or {}).items():
            race = race or {}
            try:
                rno = int(race.get('race_number') or rkey)
            except Exception:
                continue
            if not 1 <= rno <= 12:
                continue
            dt = parse_closed(race.get('closed_at'), day)
            if dt:
                races.append((rno, dt))
        races.sort(key=lambda x: x[0])
        if len(races) >= 10:
            out[jcd] = races
    return out


def token_expired(url):
    try:
        token = (urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get('token') or [None])[0]
        if not token or token.count('.') < 2:
            return False
        payload = token.split('.')[1]
        payload += '=' * (-len(payload) % 4)
        obj = json.loads(base64.urlsafe_b64decode(payload.encode()).decode('utf-8'))
        exp = int(obj.get('exp') or 0)
        return bool(exp and exp <= int(time.time()) + 300)
    except Exception:
        return False


def seed_urls():
    if not SEED.exists():
        return {}
    text = SEED.read_text(encoding='utf-8-sig', errors='replace')
    out = {}
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if not line.startswith('#EXTINF:'):
            continue
        m = re.search(r'tvg-id="([^"]+)"', line)
        if not m:
            continue
        for j in range(i + 1, min(i + 5, len(lines))):
            u = lines[j].strip()
            if u.startswith(('http://', 'https://')):
                if not token_expired(u):
                    out[m.group(1)] = u
                break
            if u.startswith('#EXTINF:'):
                break
    return out


def resolver_ready():
    # 05 is only a route existence probe. A 503 means the route exists but the
    # upstream stream is unavailable; only 404/connection failure means deploy
    # has not reached Render yet.
    url = RESOLVER.format(jcd='05') + '?debug=1'
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Cache-Control': 'no-cache'})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            return True, int(getattr(r, 'status', 200))
    except urllib.error.HTTPError as e:
        return e.code != 404, e.code
    except Exception:
        return False, 0


def strip_boat_from_public(text):
    m = re.search(re.escape(PUBLIC_START) + r'(.*?)' + re.escape(PUBLIC_END), text, re.S)
    if not m:
        return text
    lines = m.group(1).splitlines()
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('#EXTINF:') and re.search(r'tvg-id="boat\.[^"]+"', line):
            i += 1
            while i < len(lines) and not lines[i].startswith('#EXTINF:') and not lines[i].startswith('## ') and not lines[i].startswith('# ==='):
                i += 1
            continue
        out.append(line)
        i += 1
    replacement = PUBLIC_START + '\n'.join(out) + PUBLIC_END
    return text[:m.start()] + replacement + text[m.end():]


def replace_managed(text, payload):
    pat = re.compile(re.escape(START) + r'.*?' + re.escape(END) + r'\n?', re.S)
    if pat.search(text):
        return pat.sub(payload + '\n', text, count=1)
    anchor = PUBLIC_START
    if anchor in text:
        return text.replace(anchor, payload + '\n\n' + anchor, 1)
    return text.rstrip() + '\n\n' + payload + '\n'


def next_race(races, now):
    for rno, dt in races:
        if dt >= now:
            return {'race': rno, 'start': dt.strftime('%H:%M')}
    return None


def mode(races):
    first = races[0][1].hour
    last = races[-1][1].hour
    if last >= 20:
        return 'night'
    if first < 9:
        return 'morning'
    return 'day'


def make_entry(name, tvg_id, logo, url):
    return [
        f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="BOATRACE{name}" tvg-logo="{logo}" group-title="{GROUP}",BOATRACE{name}',
        url,
    ]


def main():
    if not FREEWIFI.exists():
        raise SystemExit('freewifi not found')

    now = datetime.now(JST)
    day = now.date()
    try:
        cards = cards_from_snapshot(fetch_snapshot(day), day)
    except Exception as e:
        raise SystemExit(f'BOAT v2 schedule fetch failed: {type(e).__name__}: {e}')
    if not cards:
        raise SystemExit('BOAT v2 schedule returned no complete cards')

    render_ready, render_status = resolver_ready()
    seeds = seed_urls()
    rows = []
    venues_status = {}
    ended = []
    waiting = []
    active_window = []

    for jcd, races in sorted(cards.items()):
        name, tvg_id, logo = VENUES[jcd]
        first_dt = races[0][1]
        last_dt = races[-1][1]
        show_from = first_dt - timedelta(minutes=PRESTART_MINUTES)
        remove_after = last_dt + timedelta(minutes=GRACE_MINUTES)
        nr = next_race(races, now)
        in_window = show_from <= now < remove_after
        item = {
            'jcd': jcd,
            'name': name,
            'held': True,
            'visible': False,
            'first_race': first_dt.strftime('%H:%M'),
            'show_from': show_from.isoformat(),
            'last_race': last_dt.strftime('%H:%M'),
            'remove_after': remove_after.isoformat(),
            'mode': mode(races),
            'next_race': nr,
        }
        if now < show_from:
            item['scheduled'] = True
            item['stream_window'] = 'waiting'
            waiting.append(name)
        elif now >= remove_after:
            item['ended'] = True
            item['stream_window'] = 'ended'
            ended.append(name)
        else:
            active_window.append(name)
            item['stream_window'] = 'live_or_vtr'
            if render_ready:
                url = RESOLVER.format(jcd=jcd)
                source = 'ajiousama Render on-demand resolver'
            else:
                url = seeds.get(tvg_id, '')
                source = 'temporary valid seed while Render deploy is pending' if url else 'resolver pending / no safe fallback'
            if url:
                item['visible'] = True
                item['url'] = url
                item['source'] = source
                rows.append({'name': name, 'tvg_id': tvg_id, 'block': make_entry(name, tvg_id, logo, url), 'next': nr})
            else:
                item['source'] = source
        venues_status[tvg_id] = item

    def sort_key(row):
        nr = row['next']
        if nr:
            h, m = map(int, nr['start'].split(':'))
            return (0, h * 60 + m, row['name'])
        return (1, 9999, row['name'])

    rows.sort(key=sort_key)
    body = []
    for row in rows:
        body.extend(row['block'])
        body.append('')
    managed = START + '\n## 今日の開催場 / BOAT v2 resolver\n' + '\n'.join(body).rstrip() + ('\n' if body else '') + END

    text = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    text = strip_boat_from_public(text)
    text = replace_managed(text, managed)
    FREEWIFI.write_text(text.rstrip() + '\n', encoding='utf-8')

    held_count = len(active_window)
    visible_count = len(rows)
    status = {
        'system': 'boat-v2-resolver',
        'generated_at': now.isoformat(),
        'date': day.isoformat(),
        'schedule_source': 'https://boatraceopenapi.github.io/api/v1/',
        'resolver_base': RESOLVER_BASE,
        'resolver_ready': render_ready,
        'resolver_probe_status': render_status,
        'prestart_minutes': PRESTART_MINUTES,
        'grace_minutes': GRACE_MINUTES,
        'card_count': len(cards),
        'held_count': held_count,
        'visible_count': visible_count,
        'active_window': active_window,
        'scheduled_waiting': waiting,
        'ended_removed': ended,
        'venues': venues_status,
    }
    STATUS.write_text(json.dumps(status, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    STATE.write_text(json.dumps(status, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'BOAT v2: cards={len(cards)} active={held_count} visible={visible_count} render_ready={render_ready} probe={render_status}')
    print('BOAT v2 active:', ', '.join(active_window))
    if waiting:
        print('BOAT v2 waiting:', ', '.join(waiting))
    if ended:
        print('BOAT v2 removed:', ', '.join(ended))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
