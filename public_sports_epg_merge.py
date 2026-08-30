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

FULLWIDTH = str.maketrans('0123456789', '０１２３４５６７８９')


def load_status():
    if not STATUS_JSON.exists():
        return {}
    try:
        return json.loads(STATUS_JSON.read_text(encoding='utf-8')).get('channels', {})
    except Exception:
        return {}


def wanted_ids(status=None):
    # today_public_sports_status.json is authoritative. 以前はfreewifi全体を
    # 走査していたため、非開催のboat.*までEPGへ再混入していた。
    if status is None:
        status = load_status()
    ids = {cid for cid in status if cid.startswith(PREFIXES)}
    if ids:
        return ids

    # Status JSONが無い時だけ従来方式へフォールバック。
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
    req = urllib.request.Request(PUBLIC_EPG_URL, headers={'User-Agent': 'FreeWiFi-PublicSports-EPG/2.2', 'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return ET.fromstring(r.read())


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


def _race_no(text):
    if not text:
        return None
    norm = text.translate(str.maketrans('０１２３４５６７８９Ｒｒ', '0123456789Rr'))
    m = re.search(r'(?:【\s*)?(?:第\s*)?(1[0-2]|[1-9])\s*[Rr](?:\s*】)?', norm)
    return int(m.group(1)) if m else None


def _departure_time(title, desc):
    for text in (title or '', desc or ''):
        m = re.search(r'([0-2]?\d:[0-5]\d)\s*(?:発走|発走予定)?', text)
        if m:
            return m.group(1)
    return None


def normalize_race_title(programme):
    title_el = programme.find('title')
    if title_el is None or not (title_el.text or '').strip():
        return
    title = title_el.text.strip()
    desc_el = programme.find('desc')
    desc = (desc_el.text or '') if desc_el is not None else ''
    n = _race_no(title) or _race_no(desc)
    if not n:
        return

    marker = f'【{str(n).translate(FULLWIDTH)}Ｒ】'
    tm = _departure_time(title, desc)
    rest = re.sub(r'^\s*(?:【\s*)?(?:第\s*)?[０-９0-9]{1,2}\s*[ＲRｒr](?:\s*】)?\s*', '', title, count=1)
    if rest == title:
        rest = re.sub(r'(?:【\s*)?(?:第\s*)?[０-９0-9]{1,2}\s*[ＲRｒr](?:\s*】)?', '', title, count=1).strip()

    if tm:
        rest = re.sub(rf'\s*{re.escape(tm)}\s*(?:発走|発走予定)?\s*', ' ', rest, count=1).strip()
        title_el.text = f'{marker} {tm}発走' + (f'  {rest}' if rest else '')
    else:
        title_el.text = marker + (f'  {rest}' if rest else '')


def validate_written_guides(wanted):
    root = ET.parse(GUIDES).getroot()
    channel_ids = {ch.get('id') for ch in root.findall('channel')}
    programme_ids = {p.get('channel') for p in root.findall('programme')}
    missing_channels = sorted(wanted - channel_ids)
    missing_programmes = sorted(wanted - programme_ids)
    if missing_channels or missing_programmes:
        raise SystemExit(
            'Public sports EPG validation failed: '
            f'missing_channels={missing_channels}, missing_programmes={missing_programmes}'
        )
    print(f'Public sports EPG validation OK: {len(wanted)}/{len(wanted)} active channels have EPG')


def main():
    status = load_status()
    wanted = wanted_ids(status)
    if not wanted:
        raise SystemExit('Public sports EPG: no active target channels found')

    dst = ET.parse(GUIDES).getroot()
    try:
        src = fetch_public_epg()
    except Exception as e:
        print(f'Public sports EPG fetch failed: {e}')
        src = ET.Element('tv')

    # 全公営競技EPGを一度除去してから「本日開催分だけ」を戻す。
    # これで非開催ボートの「データ取得準備中」等が残留しない。
    removed = 0
    for el in list(dst):
        cid = el.get('id') if el.tag == 'channel' else el.get('channel') if el.tag == 'programme' else None
        if cid and cid.startswith(PREFIXES):
            dst.remove(el)
            removed += 1

    source_channels = {ch.get('id'): ch for ch in src.findall('channel') if ch.get('id') in wanted}
    source_programmes = {}
    for p in src.findall('programme'):
        cid = p.get('channel')
        if cid in wanted:
            source_programmes.setdefault(cid, []).append(p)

    channels = 0
    programmes = 0
    fallbacks = 0
    normalized = 0
    for cid in sorted(wanted):
        progs = source_programmes.get(cid, [])
        if cid in source_channels and progs:
            dst.append(ET.fromstring(ET.tostring(source_channels[cid], encoding='utf-8')))
            channels += 1
            for p in progs:
                copied = ET.fromstring(ET.tostring(p, encoding='utf-8'))
                before = (copied.findtext('title') or '')
                normalize_race_title(copied)
                after = (copied.findtext('title') or '')
                if before != after:
                    normalized += 1
                dst.append(copied)
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
    validate_written_guides(wanted)
    print(f'Public sports EPG merged: channels={channels}, programmes={programmes}, wanted={len(wanted)}, fallbacks={fallbacks}, removed_old={removed}, race_titles_normalized={normalized}')


if __name__ == '__main__':
    main()
