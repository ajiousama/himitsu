from pathlib import Path
from datetime import datetime, timezone, timedelta
import json
import re
import urllib.request
import xml.etree.ElementTree as ET

FREEWIFI = Path('freewifi')
GUIDES = Path('guides.xml')
STATUS_JSON = Path('today_public_sports_status.json')
PUBLIC_EPG_URL = 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/epg.xml'
PREFIXES = ('keirin.', 'chihou.', 'boat.', 'auto.')
JST = timezone(timedelta(hours=9))

MODE_WINDOWS = {
    'morning': (8, 30, 12, 30),
    'day': (10, 30, 17, 30),
    'night': (15, 0, 21, 30),
    'midnight': (20, 30, 24, 0),
    'overnight': (21, 0, 24, 30),
}
MODE_LABELS = {
    'morning': 'モーニング',
    'day': 'デイ',
    'night': 'ナイター',
    'midnight': 'ミッドナイト',
    'overnight': 'オーバーミッドナイト',
}


def wanted_ids():
    ids = set()
    text = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    for line in text.splitlines():
        if not line.startswith('#EXTINF:'):
            continue
        m = re.search(r'tvg-id="([^"]+)"', line)
        if m and m.group(1).startswith(PREFIXES):
            ids.add(m.group(1))
    return ids


def fetch_public_epg():
    req = urllib.request.Request(PUBLIC_EPG_URL, headers={'User-Agent': 'FreeWiFi-PublicSports-EPG/2.0'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return ET.fromstring(r.read())


def load_status():
    if not STATUS_JSON.exists():
        return {}
    try:
        return json.loads(STATUS_JSON.read_text(encoding='utf-8')).get('channels', {})
    except Exception:
        return {}


def fmt(dt):
    return dt.strftime('%Y%m%d%H%M%S %z')


def fallback_times(mode):
    now = datetime.now(JST)
    y, m, d = now.year, now.month, now.day
    sh, sm, eh, em = MODE_WINDOWS.get(mode, MODE_WINDOWS['day'])
    start = datetime(y, m, d, sh, sm, tzinfo=JST)
    if eh >= 24:
        stop = datetime(y, m, d, 0, em, tzinfo=JST) + timedelta(days=1, hours=eh - 24)
    else:
        stop = datetime(y, m, d, eh, em, tzinfo=JST)
    return start, stop


def add_fallback(dst, cid, meta):
    name = meta.get('name') or cid
    section = meta.get('section') or '公営競技'
    mode = meta.get('mode') or 'day'
    label = MODE_LABELS.get(mode, 'デイ')
    start, stop = fallback_times(mode)

    ch = ET.Element('channel', {'id': cid})
    ET.SubElement(ch, 'display-name').text = name
    dst.append(ch)

    p = ET.Element('programme', {'channel': cid, 'start': fmt(start), 'stop': fmt(stop)})
    ET.SubElement(p, 'title', {'lang': 'ja'}).text = f'{name} 本日開催あり／現在準備中'
    ET.SubElement(p, 'desc', {'lang': 'ja'}).text = f'{section}・{label}開催。番組詳細を取得できていないため、現在準備中です。開催自体は公式日程で確認済みです。'
    dst.append(p)


def main():
    wanted = wanted_ids()
    if not wanted:
        print('Public sports EPG: no target channels in FreeWiFi')
        return

    dst = ET.parse(GUIDES).getroot()
    status = load_status()
    try:
        src = fetch_public_epg()
    except Exception as e:
        print(f'Public sports EPG fetch failed: {e}')
        src = ET.Element('tv')

    # epg_build.py may have created fallback entries for these IDs.
    for el in list(dst):
        if el.tag == 'channel' and el.get('id') in wanted:
            dst.remove(el)
        elif el.tag == 'programme' and el.get('channel') in wanted:
            dst.remove(el)

    source_channels = {ch.get('id'): ch for ch in src.findall('channel') if ch.get('id') in wanted}
    source_programmes = {}
    for p in src.findall('programme'):
        cid = p.get('channel')
        if cid in wanted:
            source_programmes.setdefault(cid, []).append(p)

    channels = 0
    programmes = 0
    fallbacks = 0
    for cid in sorted(wanted):
        progs = source_programmes.get(cid, [])
        if cid in source_channels and progs:
            dst.append(ET.fromstring(ET.tostring(source_channels[cid], encoding='utf-8')))
            channels += 1
            for p in progs:
                dst.append(ET.fromstring(ET.tostring(p, encoding='utf-8')))
                programmes += 1
        else:
            meta = status.get(cid)
            if meta:
                add_fallback(dst, cid, meta)
                channels += 1
                programmes += 1
                fallbacks += 1

    ET.indent(dst, space='  ')
    GUIDES.write_bytes(ET.tostring(dst, encoding='utf-8', xml_declaration=True))
    print(f'Public sports EPG merged: channels={channels}, programmes={programmes}, wanted={len(wanted)}, fallbacks={fallbacks}')


if __name__ == '__main__':
    main()
