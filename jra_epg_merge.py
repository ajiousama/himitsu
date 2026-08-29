from __future__ import annotations

from pathlib import Path
import copy
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

GUIDES = Path('guides.xml')
DEDICATED_EPG = Path('gch_free_epg.xml')
PUBLIC_EPG = 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/epg.xml'

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


def fetch_public_epg() -> ET.Element:
    req = urllib.request.Request(
        PUBLIC_EPG,
        headers={'User-Agent': 'FreeWiFi-GCH-Free-EPG/2.0', 'Cache-Control': 'no-cache'},
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return ET.fromstring(r.read())


def is_race_programme(p: ET.Element) -> bool:
    title = (p.findtext('title') or '').strip()
    if not title:
        return False
    if any(word in title for word in (
        '開催していません', '開催は終了', 'データ取得準備中',
        '本日は開催', '本日非開催', '次回開催',
    )):
        return False
    return 'ℛ' in title or bool(re.search(r'(?<!\d)(?:[1-9]|1[0-2])\s*R(?!\d)', title, re.I))


def unique_text(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        value = (value or '').strip()
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


def build_a_programmes(public_root: ET.Element) -> list[ET.Element]:
    """Combine EAST/WEST/HOKKAIDO race EPG into one chronological channel."""
    by_start: dict[str, list[tuple[str, ET.Element]]] = {}

    for p in public_root.findall('programme'):
        source_id = p.get('channel') or ''
        start = p.get('start') or ''
        if source_id not in A_SOURCE_IDS or not start or not is_race_programme(p):
            continue
        by_start.setdefault(start, []).append((source_id, p))

    if not by_start:
        print('A EPG: no JRA race programmes in EAST/WEST/HOKKAIDO')
        return []

    starts = sorted(by_start)
    output: list[ET.Element] = []

    for i, start in enumerate(starts):
        items = sorted(by_start[start], key=lambda x: A_SOURCE_IDS.index(x[0]))
        next_start = starts[i + 1] if i + 1 < len(starts) else None

        source_stops = [p.get('stop') or '' for _, p in items if p.get('stop')]
        if next_start:
            stop = next_start
        elif source_stops:
            stop = max(source_stops)
        else:
            stop = start

        titles = unique_text([p.findtext('title') or '' for _, p in items])
        descriptions = []
        for source_id, p in items:
            desc = (p.findtext('desc') or '').strip()
            if desc:
                descriptions.append(f'[{A_SOURCE_LABEL[source_id]}] {desc}')

        q = ET.Element('programme', {
            'start': start,
            'stop': stop,
            'channel': A_ID,
        })
        ET.SubElement(q, 'title', {'lang': 'ja'}).text = ' / '.join(titles)
        if descriptions:
            ET.SubElement(q, 'desc', {'lang': 'ja'}).text = '\n'.join(unique_text(descriptions))
        ET.SubElement(q, 'category', {'lang': 'ja'}).text = '中央競馬'
        output.append(q)

    return output


def add_channel(root: ET.Element, channel_id: str, display_name: str) -> None:
    ch = ET.SubElement(root, 'channel', {'id': channel_id})
    ET.SubElement(ch, 'display-name').text = display_name


def build_b_programmes() -> list[ET.Element]:
    """B only needs a simple fixed programme label for the free GCH feed."""
    now = datetime.now(JST)
    day0 = datetime(now.year, now.month, now.day, tzinfo=JST)
    programmes: list[ET.Element] = []
    for offset in range(3):
        start = day0 + timedelta(days=offset)
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


def build_dedicated_epg() -> ET.Element:
    public_root = fetch_public_epg()
    root = ET.Element('tv', {
        'generator-info-name': 'FreeWiFi GCH Free A-B EPG',
        'generator-info-url': 'https://github.com/ajiousama/himitsu',
    })

    add_channel(root, A_ID, A_NAME)
    add_channel(root, B_ID, B_NAME)

    a_programmes = build_a_programmes(public_root)
    b_programmes = build_b_programmes()

    for p in a_programmes:
        root.append(p)
    for p in b_programmes:
        root.append(p)

    dedicated_tree = ET.ElementTree(root)
    ET.indent(dedicated_tree, space='  ')
    dedicated_tree.write(DEDICATED_EPG, encoding='utf-8', xml_declaration=True)
    print(f'Dedicated GCH EPG built: A={len(a_programmes)} B={len(b_programmes)}')
    return root


def remove_target(root: ET.Element, target_id: str) -> None:
    for ch in list(root.findall('channel')):
        if ch.get('id') == target_id:
            root.remove(ch)
    for p in list(root.findall('programme')):
        if p.get('channel') == target_id:
            root.remove(p)


def merge_into_guides(dedicated_root: ET.Element) -> None:
    if not GUIDES.exists():
        raise RuntimeError('guides.xml not found')

    tree = ET.parse(GUIDES)
    root = tree.getroot()

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
    print(f'guides.xml GCH merged: A={a_count} B={b_count}')


def main() -> None:
    dedicated_root = build_dedicated_epg()
    merge_into_guides(dedicated_root)


if __name__ == '__main__':
    main()
