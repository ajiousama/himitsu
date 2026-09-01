from __future__ import annotations

from pathlib import Path
import copy
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

GUIDES = Path('guides.xml')
DEDICATED_EPG = Path('gch_free_epg.xml')
JRA_STATUS = Path('today_jra_status.json')
PUBLIC_EPG = 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/epg.xml'

# Custom-logo JRA / Green Channel routes.
BASE_IDS = ('jra.gch', 'jra.east', 'jra.west', 'jra.hokkaido')
BASE_NAMES = {
    'jra.gch': 'グリーンチャンネル',
    'jra.east': 'JRA EAST',
    'jra.west': 'JRA WEST',
    'jra.hokkaido': 'JRA HOKKAIDO',
}
# The persistent NAORI/PrimeHome/etc. GCH routes already use this ID and
# epg_build.py resolves it from normal TV-guide sources. Reuse that schedule
# for the custom-logo HQ/LQ jra.gch pair instead of maintaining a second grid.
NORMAL_GCH_ID = 'グリーンチャンネル_jp'

A_ID = 'jra.official'
A_NAME = 'GCH無料版A（YouTube）'
A_SOURCE_IDS = ('jra.east', 'jra.west', 'jra.hokkaido')
A_SOURCE_LABEL = {
    'jra.east': 'EAST',
    'jra.west': 'WEST',
    'jra.hokkaido': 'HOKKAIDO',
}

B_ID = 'jra.gch.free'
B_NAME = 'GCH無料版B（グリーンチャンネルWeb）'
B_TITLE = '競馬全レース中継　GCH（無料版）'

JST = timezone(timedelta(hours=9))
EPG_DAYS = 3


def fetch_public_epg() -> ET.Element:
    req = urllib.request.Request(
        PUBLIC_EPG,
        headers={'User-Agent': 'FreeWiFi-GCH-EPG/3.1', 'Cache-Control': 'no-cache'},
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return ET.fromstring(r.read())


def load_today_jra_status() -> tuple[bool, set[str]]:
    if not JRA_STATUS.exists():
        return False, set()
    try:
        data = json.loads(JRA_STATUS.read_text(encoding='utf-8-sig'))
        active_ids = {str(x) for x in (data.get('active_ids') or []) if str(x) in A_SOURCE_IDS}
        active = int(data.get('active_count') or 0) > 0
        return active, active_ids
    except Exception:
        return False, set()


def is_race_programme(p: ET.Element) -> bool:
    title = (p.findtext('title') or '').strip()
    if not title:
        return False
    if any(word in title for word in (
        '開催していません', '開催は終了', 'データ取得準備中',
        '本日は開催', '本日非開催', '次回開催',
    )):
        return False
    if '🏇' in title and '発走' in title:
        return True
    return (
        'ℛ' in title
        or bool(re.search(r'【\s*[０-９0-9]{1,2}\s*[RＲ]\s*】', title))
        or bool(re.search(r'(?<!\d)(?:[1-9]|1[0-2])\s*[RＲ](?!\d)', title, re.I))
    )


def start_date_key(start: str) -> str:
    m = re.match(r'^(\d{8})', start or '')
    return m.group(1) if m else ''


def rolling_date_keys(days: int = EPG_DAYS) -> set[str]:
    now = datetime.now(JST)
    day0 = datetime(now.year, now.month, now.day, tzinfo=JST)
    return {(day0 + timedelta(days=i)).strftime('%Y%m%d') for i in range(days)}


def unique_text(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = (value or '').strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def build_a_programmes(public_root: ET.Element, active_today: bool) -> list[ET.Element]:
    """Combine EAST/WEST/HOKKAIDO race EPG for the rolling 3-day window."""
    by_start: dict[str, list[tuple[str, ET.Element]]] = {}
    today_key = datetime.now(JST).strftime('%Y%m%d')
    allowed_dates = rolling_date_keys()

    for p in public_root.findall('programme'):
        source_id = p.get('channel') or ''
        start = p.get('start') or ''
        date_key = start_date_key(start)
        if source_id not in A_SOURCE_IDS or not start or not is_race_programme(p):
            continue
        if date_key not in allowed_dates:
            continue
        if date_key == today_key and not active_today:
            continue
        by_start.setdefault(start, []).append((source_id, p))

    if not by_start:
        print('A EPG: no JRA race programmes in rolling 3-day window')
        return []

    starts = sorted(by_start)
    output: list[ET.Element] = []

    for i, start in enumerate(starts):
        items = sorted(by_start[start], key=lambda x: A_SOURCE_IDS.index(x[0]))
        next_start = starts[i + 1] if i + 1 < len(starts) else None
        source_stops = [p.get('stop') or '' for _, p in items if p.get('stop')]
        stop = next_start if next_start else (max(source_stops) if source_stops else start)

        titles = unique_text([p.findtext('title') or '' for _, p in items])
        descriptions = []
        for source_id, p in items:
            desc = (p.findtext('desc') or '').strip()
            if desc:
                descriptions.append(f'[{A_SOURCE_LABEL[source_id]}] {desc}')

        q = ET.Element('programme', {'start': start, 'stop': stop, 'channel': A_ID})
        ET.SubElement(q, 'title', {'lang': 'ja'}).text = ' / '.join(titles)
        if descriptions:
            ET.SubElement(q, 'desc', {'lang': 'ja'}).text = '\n'.join(unique_text(descriptions))
        ET.SubElement(q, 'category', {'lang': 'ja'}).text = '中央競馬'
        output.append(q)

    return output


def add_channel(root: ET.Element, channel_id: str, display_name: str) -> None:
    ch = ET.SubElement(root, 'channel', {'id': channel_id})
    ET.SubElement(ch, 'display-name').text = display_name


def programme_date_key(p: ET.Element) -> str:
    return start_date_key(p.get('start') or '')


def build_b_programmes(a_programmes: list[ET.Element], active_today: bool) -> list[ET.Element]:
    """Build B only on actual JRA race dates inside the rolling 3-day window."""
    now = datetime.now(JST)
    day0 = datetime(now.year, now.month, now.day, tzinfo=JST)
    active_dates = {programme_date_key(p) for p in a_programmes}
    active_dates.discard('')
    today_key = day0.strftime('%Y%m%d')
    if active_today:
        active_dates.add(today_key)
    else:
        active_dates.discard(today_key)

    programmes: list[ET.Element] = []
    for offset in range(EPG_DAYS):
        start = day0 + timedelta(days=offset)
        if start.strftime('%Y%m%d') not in active_dates:
            continue
        stop = start + timedelta(days=1)
        p = ET.Element('programme', {
            'start': start.strftime('%Y%m%d%H%M%S +0900'),
            'stop': stop.strftime('%Y%m%d%H%M%S +0900'),
            'channel': B_ID,
        })
        ET.SubElement(p, 'title', {'lang': 'ja'}).text = B_TITLE
        ET.SubElement(p, 'category', {'lang': 'ja'}).text = '中央競馬'
        programmes.append(p)
    return programmes


def build_dedicated_epg(public_root: ET.Element, active_today: bool) -> ET.Element:
    root = ET.Element('tv', {
        'generator-info-name': 'FreeWiFi GCH Free A-B EPG',
        'generator-info-url': 'https://github.com/ajiousama/himitsu',
    })

    a_programmes = build_a_programmes(public_root, active_today)
    b_programmes = build_b_programmes(a_programmes, active_today)

    if a_programmes:
        add_channel(root, A_ID, A_NAME)
    if b_programmes:
        add_channel(root, B_ID, B_NAME)

    for p in a_programmes:
        root.append(p)
    for p in b_programmes:
        root.append(p)

    dedicated_tree = ET.ElementTree(root)
    ET.indent(dedicated_tree, space='  ')
    dedicated_tree.write(DEDICATED_EPG, encoding='utf-8', xml_declaration=True)
    print(f'Dedicated GCH free EPG built: today_active={active_today} A={len(a_programmes)} B={len(b_programmes)}')
    return root


def remove_target(root: ET.Element, target_id: str) -> None:
    for ch in list(root.findall('channel')):
        if ch.get('id') == target_id:
            root.remove(ch)
    for p in list(root.findall('programme')):
        if p.get('channel') == target_id:
            root.remove(p)


def clone_for_channel(p: ET.Element, channel_id: str) -> ET.Element:
    q = copy.deepcopy(p)
    q.set('channel', channel_id)
    return q


def sync_custom_logo_base_epg(
    guides_root: ET.Element,
    public_root: ET.Element,
    active_today_ids: set[str],
) -> dict[str, int]:
    """Attach EPG to the custom-logo GCH/EAST/WEST/HOKKAIDO HQ/LQ routes."""
    today_key = datetime.now(JST).strftime('%Y%m%d')
    allowed_dates = rolling_date_keys()

    normal_gch_programmes = [
        copy.deepcopy(p)
        for p in guides_root.findall('programme')
        if p.get('channel') == NORMAL_GCH_ID
    ]

    for cid in BASE_IDS:
        remove_target(guides_root, cid)
        add_channel(guides_root, cid, BASE_NAMES[cid])

    counts = {cid: 0 for cid in BASE_IDS}

    # GCH HQ/LQ mirrors the persistent full Green Channel grid.
    for p in normal_gch_programmes:
        guides_root.append(clone_for_channel(p, 'jra.gch'))
        counts['jra.gch'] += 1

    # Regional feeds: race rows only, limited to today + next 2 days.
    for p in public_root.findall('programme'):
        cid = p.get('channel') or ''
        start = p.get('start') or ''
        date_key = start_date_key(start)
        if cid not in A_SOURCE_IDS or not start or not is_race_programme(p):
            continue
        if date_key not in allowed_dates:
            continue
        if date_key == today_key and cid not in active_today_ids:
            continue
        guides_root.append(copy.deepcopy(p))
        counts[cid] += 1

    print(
        'Custom-logo GCH/JRA EPG synced:',
        ', '.join(f'{cid}={counts[cid]}' for cid in BASE_IDS),
    )
    return counts


def merge_into_guides(
    dedicated_root: ET.Element,
    public_root: ET.Element,
    active_today_ids: set[str],
) -> None:
    if not GUIDES.exists():
        raise RuntimeError('guides.xml not found')

    tree = ET.parse(GUIDES)
    root = tree.getroot()

    base_counts = sync_custom_logo_base_epg(root, public_root, active_today_ids)

    for target_id in (A_ID, B_ID):
        remove_target(root, target_id)

    for ch in dedicated_root.findall('channel'):
        root.insert(0, copy.deepcopy(ch))
    for p in dedicated_root.findall('programme'):
        root.append(copy.deepcopy(p))

    ET.indent(tree, space='  ')
    tree.write(GUIDES, encoding='utf-8', xml_declaration=True)

    a_count = sum(1 for p in root.findall('programme') if p.get('channel') == A_ID)
    b_count = sum(1 for p in root.findall('programme') if p.get('channel') == B_ID)
    print(
        'guides.xml GCH merged:',
        f"base={sum(base_counts.values())}",
        f'A={a_count}',
        f'B={b_count}',
    )


def main() -> None:
    public_root = fetch_public_epg()
    active_today, active_today_ids = load_today_jra_status()
    dedicated_root = build_dedicated_epg(public_root, active_today)
    merge_into_guides(dedicated_root, public_root, active_today_ids)


if __name__ == '__main__':
    main()
