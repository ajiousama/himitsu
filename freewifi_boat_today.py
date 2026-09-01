from pathlib import Path
from datetime import datetime, timezone, timedelta
import base64
import html
import json
import re
import time
import urllib.request
from urllib.parse import parse_qs, urlsplit

FREEWIFI = Path('freewifi')
STATUS_JSON = Path('today_boat_status.json')
FALLBACK_M3U = Path('public_sports_youtube_fallback.m3u')
START = '# === TODAY_BOAT_START ==='
END = '# === TODAY_BOAT_END ==='
PUBLIC_START = '# === TODAY_PUBLIC_SPORTS_START ==='
PUBLIC_END = '# === TODAY_PUBLIC_SPORTS_END ==='
GROUP = '今日の開催場'
JST = timezone(timedelta(hours=9))
FINISH_GRACE_MINUTES = 10
END_CHECK_HOURS = {9, 12, 17, 21}

VENUES = [
    ('01','桐生','01kiryu','boat.kiryu','kiryu','https://www.boatrace.jp/static/uploads/sites/8/01_N.jpg'),
    ('02','戸田','02toda','boat.toda','toda','https://www.boatrace.jp/static/uploads/sites/8/02_N-1.jpg'),
    ('03','江戸川','03edogawa','boat.edogawa','edogawa','https://www.boatrace.jp/static/uploads/sites/8/03_N-1.jpg'),
    ('04','平和島','04heiwajima','boat.heiwajima','heiwajima','https://www.boatrace.jp/static/uploads/sites/8/04_N-1.jpg'),
    ('05','多摩川','05tamagawa','boat.tamagawa','tamagawa','https://www.boatrace.jp/static/uploads/sites/8/05_N-1.jpg'),
    ('06','浜名湖','06hamanako','boat.hamanako','hamanako','https://www.boatrace.jp/static/uploads/sites/8/06_N-1.jpg'),
    ('07','蒲郡','07gamagori','boat.gamagori','gamagori','https://www.boatrace.jp/static/uploads/sites/8/07_N-1.jpg'),
    ('08','常滑','08tokoname','boat.tokoname','tokoname','https://www.boatrace.jp/static/uploads/sites/8/08_N-1.jpg'),
    ('09','津','09tsu','boat.tsu','tsu','https://www.boatrace.jp/static/uploads/sites/8/09_N-1-1.jpg'),
    ('10','三国','10mikuni','boat.mikuni','mikuni','https://www.boatrace.jp/static/uploads/sites/8/10_N-1-1.jpg'),
    ('11','びわこ','11biwako','boat.biwako','biwako','https://www.boatrace.jp/static/uploads/sites/8/11_N-1.jpg'),
    ('12','住之江','12suminoe','boat.suminoe','suminoe','https://www.boatrace.jp/static/uploads/sites/8/12_N-1-1.jpg'),
    ('13','尼崎','13amagasaki','boat.amagasaki','amagasaki','https://www.boatrace.jp/static/uploads/sites/8/13_N-1.jpg'),
    ('14','鳴門','14naruto','boat.naruto','naruto','https://www.boatrace.jp/static/uploads/sites/8/14_N-1.jpg'),
    ('15','丸亀','15marugame','boat.marugame','marugame','https://www.boatrace.jp/static/uploads/sites/8/15_N-1.jpg'),
    ('16','児島','16kojima','boat.kojima','kojima','https://www.boatrace.jp/static/uploads/sites/8/16_N-1.jpg'),
    ('17','宮島','17miyajima','boat.miyajima','miyajima','https://www.boatrace.jp/static/uploads/sites/8/17_N-1.jpg'),
    ('18','徳山','18tokuyama','boat.tokuyama','tokuyama','https://www.boatrace.jp/static/uploads/sites/8/18_N-1.jpg'),
    ('19','下関','19shimonoseki','boat.shimonoseki','shimonoseki','https://www.boatrace.jp/static/uploads/sites/8/19_N-1.jpg'),
    ('20','若松','20wakamatsu','boat.wakamatsu','wakamatsu','https://www.boatrace.jp/static/uploads/sites/8/20_N-1.jpg'),
    ('21','芦屋','21ashiya','boat.ashiya','ashiya','https://www.boatrace.jp/static/uploads/sites/8/21_N-1.jpg'),
    ('22','福岡','22fukuoka','boat.fukuoka','fukuoka','https://www.boatrace.jp/static/uploads/sites/8/22_N-1-1.jpg'),
    ('23','唐津','23karatsu','boat.karatsu','karatsu','https://www.boatrace.jp/static/uploads/sites/8/23_N-1.jpg'),
    ('24','大村','24omura','boat.omura','omura','https://www.boatrace.jp/static/uploads/sites/8/24_N-1.jpg'),
]

UA = 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/151 Safari/537.36'
WEB_HEADERS = {'User-Agent': UA}
PLAYER_HEADERS = {'User-Agent': UA, 'Origin': 'https://front.player.boatrace-cdn.jp', 'Referer': 'https://front.player.boatrace-cdn.jp/'}

def fetch_text(url, headers=None, timeout=20):
    req = urllib.request.Request(url, headers=headers or WEB_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8', errors='replace')

def fetch_json(url, headers=None, timeout=20):
    return json.loads(fetch_text(url, headers=headers, timeout=timeout))

def html_to_text(raw):
    raw = re.sub(r'<script[\s\S]*?</script>', ' ', raw, flags=re.I)
    raw = re.sub(r'<style[\s\S]*?</style>', ' ', raw, flags=re.I)
    raw = re.sub(r'<[^>]+>', ' ', raw)
    return re.sub(r'\s+', ' ', html.unescape(raw)).strip()

def race_times(jcd, ymd):
    url = f'https://www.boatrace.jp/owpc/pc/race/raceindex?hd={ymd}&jcd={jcd}'
    try:
        text = html_to_text(fetch_text(url))
    except Exception as e:
        return {}, f'raceindex:{type(e).__name__}'
    found = {}
    for m in re.finditer(r'(?<!\d)(1[0-2]|[1-9])R\s+([0-2][0-9]:[0-5][0-9])', text):
        found.setdefault(int(m.group(1)), m.group(2))
    return found, None

def playback_url(code, ymd):
    url = 'https://playback.api.streaks.jp/v1/projects/cp-boatrace-prod/' + f'medias/ref:lm-br-{code}-tokyo-{ymd}?audio_only=false'
    try:
        data = fetch_json(url, headers=PLAYER_HEADERS)
        sources = data.get('sources') or []
        src = sources[0].get('src') if sources and isinstance(sources[0], dict) else None
        return (src or '').strip(), None
    except Exception as e:
        return '', f'playback:{type(e).__name__}'

def parse_m3u_by_id(text):
    out = {}; lines = text.splitlines(); i = 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith('#EXTINF:'):
            i += 1; continue
        block = [line]; j = i + 1
        while j < len(lines) and not lines[j].startswith('#EXTINF:') and not lines[j].startswith('## ') and not lines[j].startswith('# ==='):
            if lines[j].strip(): block.append(lines[j].strip())
            j += 1
        m = re.search(r'tvg-id="([^"]+)"', line)
        if m: out[m.group(1)] = block
        i = j
    return out

def extract_managed_entries(text):
    m = re.search(re.escape(START) + r'(.*?)' + re.escape(END), text, re.S)
    return parse_m3u_by_id(m.group(1)) if m else {}

def block_url(block):
    for line in block[1:]:
        if line.startswith(('http://', 'https://')):
            return line
    return ''

def url_expired(url):
    try:
        token = (parse_qs(urlsplit(url).query).get('token') or [None])[0]
        if not token or token.count('.') < 2:
            return False
        part = token.split('.')[1]
        payload = part + '=' * (-len(part) % 4)
        obj = json.loads(base64.urlsafe_b64decode(payload.encode()).decode('utf-8'))
        exp = int(obj.get('exp') or 0)
        return bool(exp and exp <= int(time.time()) + 600)
    except Exception:
        return False

def reusable_old_block(old_entries, tvg_id):
    block = old_entries.get(tvg_id) or []
    url = block_url(block)
    if not block or not url or url_expired(url):
        return None
    return block

def fallback_url(slug):
    if not FALLBACK_M3U.exists(): return ''
    entries = parse_m3u_by_id(FALLBACK_M3U.read_text(encoding='utf-8-sig', errors='replace'))
    block = entries.get(f'youtube.boat_{slug}') or []
    for line in block[1:]:
        if line.startswith(('http://','https://')): return line
    return ''

def parse_hhmm(value, day):
    h, m = map(int, value.split(':'))
    return datetime(day.year, day.month, day.day, h, m, tzinfo=JST)

def mode_for(times):
    vals = [times[k] for k in sorted(times)]
    if not vals: return 'day'
    first_h = int(vals[0].split(':')[0]); last_h = int(vals[-1].split(':')[0])
    if last_h >= 20: return 'night'
    if first_h < 9: return 'morning'
    return 'day'

def next_race_info(times, now):
    future = []
    for rno, hhmm in times.items():
        dt = parse_hhmm(hhmm, now.date())
        if dt >= now: future.append((dt, rno, hhmm))
    if future:
        _, rno, hhmm = min(future)
        return {'race': rno, 'start': hhmm}, False
    if not times: return None, False
    last_dt = max(parse_hhmm(x, now.date()) for x in times.values())
    return None, now >= last_dt + timedelta(minutes=FINISH_GRACE_MINUTES)

def strip_boat_from_public(text):
    m = re.search(re.escape(PUBLIC_START) + r'(.*?)' + re.escape(PUBLIC_END), text, re.S)
    if not m:
        return text
    body = m.group(1).splitlines()
    out = []
    i = 0
    while i < len(body):
        line = body[i]
        if line.startswith('#EXTINF:') and re.search(r'tvg-id="boat\.[^"]+"', line):
            i += 1
            while i < len(body) and not body[i].startswith('#EXTINF:') and not body[i].startswith('## '):
                i += 1
            continue
        out.append(line)
        i += 1
    replacement = PUBLIC_START + '\n'.join(out) + PUBLIC_END
    return text[:m.start()] + replacement + text[m.end():]

def replace_block(text, managed):
    pat = re.compile(re.escape(START) + r'.*?' + re.escape(END) + r'\n?', re.S)
    if pat.search(text): return pat.sub(managed + '\n', text, count=1)
    anchor = '# === TODAY_PUBLIC_SPORTS_START ==='
    if anchor in text: return text.replace(anchor, managed + '\n\n' + anchor, 1)
    anchor = '# === GENERAL_YOUTUBE_MANAGED_START ==='
    if anchor in text: return text.replace(anchor, managed + '\n\n' + anchor, 1)
    return text.rstrip() + '\n\n' + managed + '\n'

def make_block(tvg_id, name, logo, url):
    return [f'#EXTINF:-1 tvg-id="{tvg_id}" tvg-name="BOATRACE{name}" tvg-logo="{logo}" group-title="{GROUP}",BOATRACE{name}', url]

def main():
    if not FREEWIFI.exists(): raise SystemExit('freewifi not found')
    now = datetime.now(JST); ymd = now.strftime('%Y%m%d'); status = {}; rows = []
    existing_text = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    existing_text = strip_boat_from_public(existing_text)
    old_entries = extract_managed_entries(existing_text)
    end_check = now.hour in END_CHECK_HOURS
    for jcd, name, code, tvg_id, slug, logo in VENUES:
        times, schedule_error = race_times(jcd, ymd)
        if not times:
            status[tvg_id] = {'name': name, 'held': False, 'live': False, 'source': 'BOAT RACE official raceindex', 'error': schedule_error}
            print(f'BOAT {name}: non-event / schedule unavailable')
            continue
        nr, ended = next_race_info(times, now); mode = mode_for(times)
        if ended:
            if end_check:
                status[tvg_id] = {'name': name, 'held': True, 'live': False, 'ended': True, 'mode': mode, 'last_race': times[max(times)], 'source': 'BOAT RACE official raceindex'}
                print(f'BOAT {name}: ended -> removed at scheduled end check')
                continue
            old = reusable_old_block(old_entries, tvg_id)
            if old:
                status[tvg_id] = {'name': name, 'held': True, 'live': True, 'ended_pending_check': True, 'mode': mode, 'last_race': times[max(times)], 'source': 'previous playable URL until scheduled end check'}
                rows.append({'name': name, 'next_race': None, 'block': old})
                print(f'BOAT {name}: ended / kept until next scheduled end check')
            else:
                status[tvg_id] = {'name': name, 'held': True, 'live': False, 'ended_pending_check': True, 'mode': mode, 'last_race': times[max(times)], 'source': 'BOAT RACE official raceindex'}
                print(f'BOAT {name}: ended / no reusable URL')
            continue
        url, playback_error = playback_url(code, ymd); source = 'BOAT RACE playback API'
        if not url:
            url = fallback_url(slug)
            if url:
                source = 'official YouTube fallback'
        old_block = None
        if not url:
            old_block = reusable_old_block(old_entries, tvg_id)
            if old_block:
                url = block_url(old_block)
                source = 'previous playable URL'
        item = {'name': name, 'held': True, 'live': bool(url), 'ended': False, 'mode': mode, 'first_race': times[min(times)], 'last_race': times[max(times)], 'next_race': nr, 'next_race_text': f"次は {nr['race']}R {nr['start']}発走" if nr else '開催中／最終R終了確認待ち', 'source': source if url else 'BOAT RACE official raceindex'}
        if playback_error: item['playback_error'] = playback_error
        status[tvg_id] = item
        if url:
            rows.append({'name': name, 'next_race': nr, 'block': old_block if old_block else make_block(tvg_id, name, logo, url)})
            print(f"BOAT {name}: live URL OK / {item['next_race_text']}")
        else:
            print(f"BOAT {name}: held / stream waiting / {item['next_race_text']}")
    def sort_key(row):
        nr = row.get('next_race')
        if nr and re.fullmatch(r'\d{2}:\d{2}', nr.get('start','')):
            h, m = map(int, nr['start'].split(':')); return (h*60+m, row['name'])
        return (24*60+1, row['name'])
    rows.sort(key=sort_key)
    body = []
    for row in rows: body.extend(row['block']); body.append('')
    payload = '\n'.join(body).rstrip()
    managed = START + '\n## 今日の開催場（ボート独立）\n' + payload + ('\n' if payload else '') + END
    FREEWIFI.write_text(replace_block(existing_text, managed).rstrip() + '\n', encoding='utf-8')
    held_count = sum(1 for x in status.values() if x.get('held') and not x.get('ended'))
    STATUS_JSON.write_text(json.dumps({'generated_at': now.isoformat(), 'date': now.date().isoformat(), 'visible_count': len(rows), 'held_count': held_count, 'scheduled_end_check': end_check, 'channels': status}, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'BOAT independent update: visible={len(rows)} held={held_count}')

if __name__ == '__main__': main()
