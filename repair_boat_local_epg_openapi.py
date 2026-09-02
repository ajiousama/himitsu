from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
import urllib.request
import xml.etree.ElementTree as ET

import public_sports_epg_local as b

EPG = Path('public_sports_epg_local.xml')
VERIFIED = Path('verified_daily_status.json')
JST = timezone(timedelta(hours=9))
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152 Safari/537.36'
API = 'https://boatraceopenapi.github.io/api/v1/{year}/{ymd}.json'


def fetch_today(day):
    url = API.format(year=day.strftime('%Y'), ymd=day.strftime('%Y%m%d'))
    req = urllib.request.Request(url, headers={
        'User-Agent': UA,
        'Accept': 'application/json',
        'Cache-Control': 'no-cache',
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return json.loads(r.read().decode('utf-8'))
    except Exception as e:
        print(f'BOAT OpenAPI fallback unavailable: {type(e).__name__}: {e}')
        return {}


def api_races(data, day):
    stadiums = (((data or {}).get('programs') or {}).get('stadiums') or {})
    out = {}
    for key, item in stadiums.items():
        try:
            code = f'{int(key):02d}'
        except Exception:
            continue
        if code not in b.BOAT:
            continue
        races_obj = (item or {}).get('races') or {}
        races = []
        for rkey, race in races_obj.items():
            race = race or {}
            try:
                n = int(race.get('race_number') or rkey)
            except Exception:
                continue
            if not 1 <= n <= 12:
                continue
            closed = str(race.get('closed_at') or '').strip()
            if not closed:
                continue
            try:
                dt = datetime.strptime(closed, '%Y-%m-%d %H:%M:%S')
            except Exception:
                try:
                    dt = datetime.fromisoformat(closed)
                except Exception:
                    continue
            if dt.date() != day:
                continue
            title = str(race.get('subtitle') or race.get('title') or 'ボートレース').strip()
            races.append({'race': n, 'time': dt.strftime('%H:%M'), 'name': title})
        races.sort(key=lambda x: x['race'])
        # A proper daily card should contain nearly the whole grid. Avoid
        # replacing better official data with a partial upstream snapshot.
        if len(races) >= 10:
            out[code] = races
    return out


def parse_start(value):
    text = str(value or '').strip()
    if len(text) < 8:
        return ''
    return text[:8]


def remove_today_boat_programmes(root, day, replace_ids):
    ymd = day.strftime('%Y%m%d')
    removed = 0
    for p in list(root.findall('programme')):
        cid = p.get('channel') or ''
        if cid not in replace_ids:
            continue
        if parse_start(p.get('start')) == ymd:
            root.remove(p)
            removed += 1
    return removed


def load_verified(day):
    if VERIFIED.exists():
        try:
            obj = json.loads(VERIFIED.read_text(encoding='utf-8-sig'))
            if obj.get('date') == day.isoformat():
                return obj
        except Exception:
            pass
    return {
        'date': day.isoformat(),
        'checked_at': datetime.now(JST).isoformat(),
        'public_sports': {'競輪': [], '地方競馬': [], 'ボートレース': [], 'オートレース': []},
        'public_sports_modes': {'競輪': {}, '地方競馬': {}, 'ボートレース': {}, 'オートレース': {}},
        'jra_active_ids': [],
        'source': 'ajiousama/himitsu direct official acquisition',
    }


def main():
    if not EPG.exists():
        raise SystemExit('public_sports_epg_local.xml missing')

    day = datetime.now(JST).date()
    data = fetch_today(day)
    cards = api_races(data, day)
    if not cards:
        print('BOAT OpenAPI repair: no complete cards; preserve current local EPG')
        return 0

    tree = ET.parse(EPG)
    root = tree.getroot()
    replace_ids = {b.BOAT[code][1] for code in cards}
    removed = remove_today_boat_programmes(root, day, replace_ids)

    verified = load_verified(day)
    public = verified.setdefault('public_sports', {}).setdefault('ボートレース', [])
    modes = verified.setdefault('public_sports_modes', {}).setdefault('ボートレース', {})

    added = 0
    for code, races in sorted(cards.items()):
        venue, cid = b.BOAT[code]
        b.ensure_channel(root, cid, f'BOATRACE{venue}')
        mode, label = b.mode_from_times(races)
        b.add_race_grid(root, cid, f'BOATRACE{venue}', day, races, '🚤', label, 'ボートレース', switch_after=3)
        if venue not in public:
            public.append(venue)
        modes[venue] = mode
        added += len(races)

    verified['checked_at'] = datetime.now(JST).isoformat()
    verified['source'] = 'ajiousama/himitsu direct acquisition + Boatrace Open API fallback'
    verified['boat_schedule_fallback'] = {
        'source': 'boatraceopenapi/api v1',
        'date': day.isoformat(),
        'venues': len(cards),
        'races': added,
    }

    # Preserve channel-first XML ordering and chronological programme order.
    channels = [x for x in list(root) if x.tag == 'channel']
    programmes = [x for x in list(root) if x.tag == 'programme']
    programmes.sort(key=lambda p: (p.get('start', ''), p.get('channel', '')))
    for x in list(root):
        root.remove(x)
    seen = set()
    for ch in channels:
        cid = ch.get('id')
        if cid in seen:
            continue
        seen.add(cid)
        root.append(ch)
    for p in programmes:
        root.append(p)

    ET.indent(tree, space='  ')
    tree.write(EPG, encoding='utf-8', xml_declaration=True)
    VERIFIED.write_text(json.dumps(verified, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'BOAT OpenAPI repair: venues={len(cards)} races={added} removed_old={removed}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
