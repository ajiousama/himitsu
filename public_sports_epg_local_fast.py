from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, time
import urllib.request

import public_sports_epg_local as b

# Keep one slow endpoint from stalling the entire daily refresh.
_original_fetch_text = b.fetch_text

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


def build_boat_fast(root, target_days, verified):
    index_results = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(b.boat_codes, day): day for day in target_days}
        for fut in as_completed(futs):
            day = futs[fut]
            try:
                index_results[day] = fut.result()
            except Exception as e:
                print(f'BOAT FAST index {day}: {e}')
                index_results[day] = []

    jobs = []
    with ThreadPoolExecutor(max_workers=10) as ex:
        for day in target_days:
            for code in index_results.get(day, []):
                if code in b.BOAT:
                    jobs.append((ex.submit(b.boat_races, day, code), day, code))
        results = []
        for fut, day, code in jobs:
            try:
                results.append((day, code, fut.result()))
            except Exception as e:
                print(f'BOAT FAST {day} {code}: {e}')
                results.append((day, code, []))

    by_key = {(day, code): races for day, code, races in results}
    for offset, day in enumerate(target_days):
        codes = index_results.get(day, [])
        # BOAT official details are often not yet published for day+2.
        if not codes and offset >= 2:
            for code, (venue, cid) in b.BOAT.items():
                b.ensure_channel(root, cid, f'BOATRACE{venue}')
                start = datetime.combine(day, time(10, 0), tzinfo=b.JST)
                stop = datetime.combine(day, time(18, 0), tzinfo=b.JST)
                b.add_programme(root, cid, start, stop, f'BOATRACE{venue} 開催予定（公式詳細未公表）', '3日目は公式詳細未公表のため、開催・非開催と実時刻は未確定です。')
            continue
        for code in codes:
            if code not in b.BOAT:
                continue
            venue, cid = b.BOAT[code]
            races = by_key.get((day, code), [])
            b.ensure_channel(root, cid, f'BOATRACE{venue}')
            if races:
                mode, label = b.mode_from_times(races)
                b.add_race_grid(root, cid, f'BOATRACE{venue}', day, races, '🚤', label, 'ボートレース', switch_after=3)
            else:
                mode, label = 'day', 'デイ'
                b.add_programme(root, cid, datetime.combine(day, time(10, 0), tzinfo=b.JST), datetime.combine(day, time(18, 0), tzinfo=b.JST), f'BOATRACE{venue} 開催予定／発走時刻確認待ち', 'BOAT RACE公式の開催一覧で開催確認済み。')
            if day == target_days[0]:
                verified['public_sports']['ボートレース'].append(venue)
                verified['public_sports_modes']['ボートレース'][venue] = mode


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


def build_jra_fast(root, target_days, verified):
    meetings_by_day = {}
    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = {ex.submit(b.fetch_jra, day): day for day in target_days}
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
