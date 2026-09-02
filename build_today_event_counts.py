from pathlib import Path
from datetime import datetime, timezone, timedelta
import json

JST = timezone(timedelta(hours=9))
PUBLIC = Path('today_public_sports_status.json')
JRA = Path('today_jra_status.json')
BOAT = Path('today_boat_status.json')
OUT = Path('today_event_counts.json')


def load(path):
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}


def main():
    pub = load(PUBLIC)
    jra = load(JRA)
    boat = load(BOAT)
    channels = pub.get('channels', {})

    mapping = {
        '競輪': 'keirin',
        '地方競馬': 'local_horse',
        'オートレース': 'autorace',
        'ボートレース': 'boat',
    }
    counts = {v: 0 for v in mapping.values()}
    venues = {v: [] for v in mapping.values()}

    for info in channels.values():
        section = info.get('section')
        key = mapping.get(section)
        if not key:
            continue
        # BOAT V2 is authoritative for BOAT. Ignore any transient legacy BOAT
        # rows that may still exist in the general status file.
        if key == 'boat' and boat.get('system') == 'boat-v2-resolver':
            continue
        counts[key] += 1
        venues[key].append(info.get('name') or '')

    if boat.get('system') == 'boat-v2-resolver':
        counts['boat'] = int(boat.get('visible_count') or 0)
        venues['boat'] = [
            info.get('name') or ''
            for info in (boat.get('venues') or {}).values()
            if info.get('visible')
        ]

    counts['jra'] = int(jra.get('active_count') or 0)
    venues['jra'] = jra.get('active_labels') or []

    labels = {
        'jra': 'JRA',
        'local_horse': '地方競馬',
        'keirin': '競輪',
        'autorace': 'オート',
        'boat': 'ボート',
    }
    summary = {
        'generated_at': datetime.now(JST).isoformat(),
        'counts': counts,
        'venues': venues,
        'display': {labels[k]: counts[k] for k in ('jra','local_horse','keirin','autorace','boat')},
        'total': sum(counts.values()),
    }
    OUT.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Current event counts:', summary['display'])


if __name__ == '__main__':
    main()
