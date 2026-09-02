from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, time
from pathlib import Path
import json
import re
import subprocess

import public_sports_epg_local as b

# Keep one slow endpoint from stalling the entire daily refresh.
_original_fetch_text = b.fetch_text
_original_jra = b.fetch_jra


def capped_fetch_text(url, label='URL', timeout=30, headers=None):
    return _original_fetch_text(url, label, timeout=min(timeout, 8), headers=headers)


b.fetch_text = capped_fetch_text

# keirin_epg_direct has its own network helper; cap that too.
def keirin_fetch(url, label):
    return b.fetch_text(url, label, timeout=8, headers={'Referer': 'https://keirin.netkeiba.com/'})


b.keirin_direct.fetch = keirin_fetch


def build_keirin_fast(root, target_days, verified):
    months = {}
    for day in target_days:
        months.setdefault((day.year, day.month), b.keirin_month(day.year, day.month))
    today = target_days[0]
    today_schedule = months[(today.year, today.month)].get(today.strftime('%Y%m%d'), {})
    today_races = {}
    with ThreadPoolExecutor(max_workers=6) as ex:
        futs = {ex.submit(b.keirin_direct.fetch_venue, venue, today.strftime('%Y%m%d')): venue for venue in today_schedule}
        for fut in as_completed(futs):
            venue = futs[fut]
            try:
                today_races[venue] = fut.result()
            except Exception as e:
                print(f'KEIRIN FAST {venue}: {e}')
                today_races[venue] = []

    for day in target_days:
        schedule = months[(day.year, day.month)].get(day.strftime('%Y%m%d'), {})
        for venue, meta in schedule.items():
            cid = b.KEIRIN_IDS.get(venue)
            if not cid:
                continue
            b.ensure_channel(root, cid, venue)
            races = today_races.get(venue, []) if day == today else []
            if races:
                mode, label = b.mode_from_times(races)
                b.add_race_grid(root, cid, venue, day, races, '🚲', label, '競輪', switch_after=3)
            else:
                mode, label = meta['mode'], meta['label']
                s, e = b.KEIRIN_PROVISIONAL.get(mode, b.KEIRIN_PROVISIONAL['day'])
                title = f'{venue} 【{meta["grade"]}】 {label} 開催予定（仮時間）'
                desc = 'KEIRIN.JP公式開催表を基にした仮時間EPGです。'
                b.add_programme(root, cid, b.parse_hhmm(day, s), b.parse_hhmm(day, e), title, desc)
            if day == today:
                verified['public_sports']['競輪'].append(venue)
                verified['public_sports_modes']['競輪'][venue] = (b.mode_from_times(races)[0] if races else meta['mode'])


def build_nar_fast(root, target_days, verified):
    tasks = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        for day in target_days:
            for venue, (code, cid) in b.NAR.items():
                tasks.append((ex.submit(b.nar_races, day, venue, code), day, venue, cid))
        for fut, day, venue, cid in tasks:
            try:
                races = fut.result()
            except Exception as e:
                print(f'NAR FAST {day} {venue}: {e}')
                races = []
            if not races:
                continue
            b.ensure_channel(root, cid, venue)
            mode, label = b.mode_from_times(races)
            b.add_race_grid(root, cid, venue, day, races, '🏇', label, '地方競馬', switch_after=3)
            if day == target_days[0]:
                verified['public_sports']['地方競馬'].append(venue)
                verified['public_sports_modes']['地方競馬'][venue] = mode


def _load_today_boat_fallback(today):
    path = Path('today_boat_status.json')
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding='utf-8-sig'))
    except Exception as e:
        print(f'BOAT fallback JSON unreadable: {e}')
        return {}
    generated = str(data.get('generated_at') or '')
    if generated[:10] != today.isoformat():
        return {}
    channels = data.get('channels') or {}
    return channels if isinstance(channels, dict) else {}


def _add_boat_status_fallback(root, today, verified, channels):
    used = 0
    for code, (venue, cid) in b.BOAT.items():
        item = channels.get(cid) or {}
        if not item.get('held'):
            continue
        b.ensure_channel(root, cid, f'BOATRACE{venue}')
        nr = item.get('next_race') or {}
        first = item.get('first_race') or '10:00'
        last = item.get('last_race') or '18:00'
        try:
            start = b.parse_hhmm(today, first) - timedelta(minutes=20)
            stop = b.parse_hhmm(today, last) + timedelta(minutes=15)
        except Exception:
            start = datetime.combine(today, time(10, 0), tzinfo=b.JST)
            stop = datetime.combine(today, time(18, 30), tzinfo=b.JST)
        title = f'BOATRACE{venue} 開催中／公式raceindex再取得待ち'
        if nr.get('race') and nr.get('start'):
            title = f'BOATRACE{venue} 次は {nr["race"]}R {nr["start"]}発走'
        b.add_programme(root, cid, start, stop, title, 'ajiousama内の直前BOATRACE公式取得結果を一時利用。次回更新でraceindexを再取得します。')
        mode = item.get('mode') or 'day'
        verified['public_sports']['ボートレース'].append(venue)
        verified['public_sports_modes']['ボートレース'][venue] = mode
        used += 1
    return used


def build_boat_fast(root, target_days, verified):
    # Do not depend on the single BOAT index page.  Probe all 24 official
    # raceindex endpoints in parallel; one broken index response can no longer
    # erase every venue from the local EPG.
    jobs = []
    results = {}
    with ThreadPoolExecutor(max_workers=18) as ex:
        for day in target_days:
            for code in b.BOAT:
                jobs.append((ex.submit(b.boat_races, day, code), day, code))
        for fut, day, code in jobs:
            try:
                results[(day, code)] = fut.result()
            except Exception as e:
                print(f'BOAT FAST {day} {code}: {e}')
                results[(day, code)] = []

    today = target_days[0]
    today_count = 0
    for day in target_days:
        held_codes = [code for code in b.BOAT if results.get((day, code))]
        print(f'BOAT FAST {day}: direct held venues={len(held_codes)}')
        for code in held_codes:
            venue, cid = b.BOAT[code]
            races = results[(day, code)]
            b.ensure_channel(root, cid, f'BOATRACE{venue}')
            mode, label = b.mode_from_times(races)
            b.add_race_grid(root, cid, f'BOATRACE{venue}', day, races, '🚤', label, 'ボートレース', switch_after=3)
            if day == today:
                today_count += 1
                verified['public_sports']['ボートレース'].append(venue)
                verified['public_sports_modes']['ボートレース'][venue] = mode

    # If every direct request failed at once, retain only venues previously
    # verified today by the independent ajiousama BOAT updater.  Never invent
    # all 24 venues as provisional events.
    if today_count == 0:
        channels = _load_today_boat_fallback(today)
        used = _add_boat_status_fallback(root, today, verified, channels)
        print(f'BOAT FAST {today}: fallback verified venues={used}')


def build_auto_fast(root, target_days, verified):
    jobs = []
    with ThreadPoolExecutor(max_workers=8) as ex:
        for day in target_days:
            for venue, (cid, slug) in b.AUTO.items():
                jobs.append((ex.submit(b.auto_races, day, venue, slug, day == target_days[0]), day, venue, cid))
        for fut, day, venue, cid in jobs:
            try:
                races = fut.result()
            except Exception as e:
                print(f'AUTO FAST {day} {venue}: {e}')
                races = []
            if not races:
                continue
            b.ensure_channel(root, cid, f'{venue}オート')
            mode, label = b.mode_from_times(races, 'auto')
            if day == target_days[0]:
                b.add_race_grid(root, cid, f'{venue}オート', day, races, '🏍️', label, 'オートレース', switch_after=3)
                verified['public_sports']['オートレース'].append(venue)
                verified['public_sports_modes']['オートレース'][venue] = mode
            else:
                start = b.parse_hhmm(day, races[0]['time']) - timedelta(minutes=20)
                stop = b.parse_hhmm(day, races[-1]['time']) + timedelta(minutes=30)
                b.add_programme(root, cid, start, stop, f'{venue}オート {label} 開催予定', f'AutoRace.JP公式出走表で{day.isoformat()}の開催を確認。')


def _decode_bytes(raw):
    best = ''
    venues = tuple(b.JRA_VENUE_STREAM)
    for enc in ('utf-8', 'cp932', 'shift_jis', 'euc_jp'):
        try:
            s = raw.decode(enc)
        except Exception:
            continue
        if not best or sum(s.count(x) for x in venues) > sum(best.count(x) for x in venues):
            best = s
    return best or raw.decode('utf-8', errors='replace')


def _parse_jra_official(source):
    text = b.plain_text(source)
    meeting_re = re.compile(r'(\d+)\s*回\s*(東京|中山|新潟|福島|京都|阪神|中京|小倉|札幌|函館)\s*(\d+)\s*日')
    heads = list(meeting_re.finditer(text))
    out = {}
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


def _parse_jra_netkeiba(source):
    text = b.plain_text(source)
    heading = re.compile(r'(?:\d+\s*回\s*)?(東京|中山|新潟|福島|京都|阪神|中京|小倉|札幌|函館)\s*(?:\d+\s*日目?)?')
    heads = list(heading.finditer(text))
    out = {}
    for i, m in enumerate(heads):
        venue = m.group(1)
        section = text[m.end(): heads[i + 1].start() if i + 1 < len(heads) else len(text)]
        found = {}
        for r in re.finditer(r'(?<!\d)(1[0-2]|[1-9])R\s+(.{0,120}?)\s+([0-2]?\d:[0-5]\d)', section, re.S):
            n = int(r.group(1))
            name = re.sub(r'\s+', ' ', r.group(2)).strip(' -|')[:160] or 'JRA競走'
            found.setdefault(n, {'race': n, 'time': r.group(3).zfill(5), 'name': name})
        if found:
            out[venue] = [found[n] for n in sorted(found)]
    return out


def fetch_jra_resilient(day):
    # First use the base official JRA fetch.  If GitHub's Python HTTP stack is
    # blocked with 403, retry the exact same official page with curl.
    out = _original_jra(day)
    if out:
        return out

    url = b.jra_url(day)
    cmd = [
        'curl', '-L', '--compressed', '--silent', '--show-error',
        '--retry', '2', '--retry-all-errors', '--connect-timeout', '8', '--max-time', '18',
        '-A', b.UA,
        '-H', 'Accept-Language: ja-JP,ja;q=0.9',
        '-H', 'Referer: https://www.jra.go.jp/keiba/calendar/',
        url,
    ]
    try:
        cp = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=22, check=False)
        if cp.stdout:
            out = _parse_jra_official(_decode_bytes(cp.stdout))
            if out:
                print(f'JRA {day}: curl official fallback OK venues={list(out)}')
                return out
        if cp.returncode:
            print(f'JRA {day}: curl official fallback rc={cp.returncode} {cp.stderr.decode("utf-8", errors="replace")[:180]}')
    except Exception as e:
        print(f'JRA {day}: curl official fallback failed: {e}')

    # Last resort: netkeiba race-list partial.  This remains independent of
    # every other GitHub repository and is used only when the official site is
    # unreachable from Actions.
    nurl = f'https://race.netkeiba.com/top/race_list_sub.html?kaisai_date={day.strftime("%Y%m%d")}'
    source = b.fetch_text(nurl, f'JRA netkeiba fallback {day}', timeout=8, headers={'Referer': 'https://race.netkeiba.com/top/race_list.html'})
    out = _parse_jra_netkeiba(source) if source else {}
    if out:
        print(f'JRA {day}: netkeiba fallback OK venues={list(out)}')
    return out


def build_jra_fast(root, target_days, verified):
    meetings_by_day = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(fetch_jra_resilient, day): day for day in target_days}
        for fut in as_completed(futs):
            day = futs[fut]
            try:
                meetings_by_day[day] = fut.result()
            except Exception as e:
                print(f'JRA FAST {day}: {e}')
                meetings_by_day[day] = {}

    original = b.fetch_jra
    try:
        b.fetch_jra = lambda day: meetings_by_day.get(day, {})
        # Reuse the already-tested output formatting in the base module.
        _build_jra_original(root, target_days, verified)
    finally:
        b.fetch_jra = original


_build_jra_original = b.build_jra
b.build_keirin = build_keirin_fast
b.build_nar = build_nar_fast
b.build_boat = build_boat_fast
b.build_auto = build_auto_fast
b.build_jra = build_jra_fast

if __name__ == '__main__':
    b.main()
