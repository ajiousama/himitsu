from __future__ import annotations

import html
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

FREEWIFI = Path('freewifi')
GUIDES = Path('guides.xml')
OFFICIAL_URL = 'https://jdleague.jp/games/month/'
JST = timezone(timedelta(hours=9))

JD_HINTS = ('JDリーグ', 'JD.LEAGUE', 'JD LEAGUE', '女子ソフトボール')
WEEKDAY_JA = ['月', '火', '水', '木', '金', '土', '日']


def fetch_official_text() -> str:
    req = urllib.request.Request(
        OFFICIAL_URL,
        headers={
            'User-Agent': 'Mozilla/5.0 (FreeWiFi JDLeague EPG; +https://github.com/ajiousama/himitsu)',
            'Accept-Language': 'ja,en;q=0.8',
        },
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read().decode('utf-8', errors='replace')
    raw = re.sub(r'<script\b[^>]*>.*?</script>', ' ', raw, flags=re.I | re.S)
    raw = re.sub(r'<style\b[^>]*>.*?</style>', ' ', raw, flags=re.I | re.S)
    text = re.sub(r'<[^>]+>', '\n', raw)
    text = html.unescape(text)
    text = text.replace('\r', '\n')
    text = re.sub(r'[ \t\u3000]+', ' ', text)
    text = re.sub(r'\n+', '\n', text)
    return text.strip()


def parse_next_schedule(text: str):
    today = datetime.now(JST).date()
    # Official page date headings look like: 2026.09.04 (Fri)
    date_matches = list(re.finditer(r'(?m)(20\d{2})[./](\d{1,2})[./](\d{1,2})\s*\([A-Za-z]{3}\)', text))
    future = []
    for m in date_matches:
        try:
            d = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=JST).date()
        except ValueError:
            continue
        if d >= today:
            future.append((d, m))
    if not future:
        raise RuntimeError('JD.LEAGUE official page: no future schedule date found')

    day, match = min(future, key=lambda x: x[0])
    start = match.end()
    next_heading = next((m for m in date_matches if m.start() > match.start()), None)
    end = next_heading.start() if next_heading else min(len(text), start + 5000)
    segment = text[start:end]

    round_match = re.search(r'(第\s*\d+\s*節|プレーオフ\s*(?:1st|2nd)|SEMI\s*FINAL|FINAL)', segment, flags=re.I)
    round_name = re.sub(r'\s+', '', round_match.group(1)) if round_match else ''

    # Capture useful visible lines for that date. Keep only compact game-like rows.
    lines = [x.strip() for x in segment.splitlines() if x.strip()]
    ignore = {
        'Image', 'VS', 'イベント情報', 'EVENT INFO', 'Live', 'チケット購入', 'BUY TICKET',
    }
    clean = []
    for line in lines:
        if line in ignore:
            continue
        if re.fullmatch(r'\d{1,2}:\d{2}', line) or re.search(r'球場|スタジアム|公園野球場|市民球場|運動公園', line) or line in {
            'ホンダ','デンソー','豊田織機','トヨタ','タカギ','伊予銀行','戸田中央','太陽誘電','日立','SGH','SHIONOGI','NEC','ビック','ミナモ'
        }:
            clean.append(line)
        if len(clean) >= 36:
            break

    wd = WEEKDAY_JA[day.weekday()]
    date_label = f'{day.month}/{day.day}({wd})'
    title = f'🥎 JDリーグ 次回開催 {date_label}' + (f' {round_name}' if round_name else '')
    desc = f'JD.LEAGUE公式サイトから取得した次回開催日程です。\n次回開催: {day.year}/{day.month}/{day.day}({wd})'
    if round_name:
        desc += f' {round_name}'
    if clean:
        desc += '\n' + ' / '.join(clean)
    desc += f'\n公式: {OFFICIAL_URL}'
    return day, title, desc


def find_jd_channels():
    text = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    found = {}
    for line in text.splitlines():
        if not line.startswith('#EXTINF:'):
            continue
        upper = line.upper()
        if not any(h.upper() in upper for h in JD_HINTS):
            continue
        m = re.search(r'tvg-id="([^"]+)"', line)
        if not m:
            continue
        tvg_id = m.group(1).strip()
        name = line.rsplit(',', 1)[-1].strip() if ',' in line else tvg_id
        found.setdefault(tvg_id, name)
    return found


def xmltv_time(dt: datetime) -> str:
    return dt.strftime('%Y%m%d%H%M%S +0900')


def ensure_channel(root, tvg_id: str, name: str):
    for ch in root.findall('channel'):
        if ch.get('id') == tvg_id:
            return
    ch = ET.SubElement(root, 'channel', {'id': tvg_id})
    ET.SubElement(ch, 'display-name').text = name


def apply_epg(channels, title: str, desc: str):
    tree = ET.parse(GUIDES)
    root = tree.getroot()
    ids = set(channels)

    # JD League channels should show the next official schedule on every channel,
    # replacing generic fallback entries from the merged EPG builder.
    for p in list(root.findall('programme')):
        if p.get('channel') in ids:
            root.remove(p)

    now = datetime.now(JST)
    base = datetime(now.year, now.month, now.day, tzinfo=JST)
    for tvg_id, name in channels.items():
        ensure_channel(root, tvg_id, name)
        for d in range(3):
            st = base + timedelta(days=d)
            en = st + timedelta(hours=23, minutes=59)
            p = ET.SubElement(root, 'programme', {
                'start': xmltv_time(st),
                'stop': xmltv_time(en),
                'channel': tvg_id,
            })
            ET.SubElement(p, 'title', {'lang': 'ja'}).text = title
            ET.SubElement(p, 'desc', {'lang': 'ja'}).text = desc
            ET.SubElement(p, 'category', {'lang': 'ja'}).text = 'JDリーグ'

    ET.indent(tree, space='  ')
    tree.write(GUIDES, encoding='utf-8', xml_declaration=True)


def main():
    channels = find_jd_channels()
    if not channels:
        # The FreeWiFi playlist does not always carry JD League channels.
        # This helper is only an EPG overlay, so absence is a normal no-op,
        # not a repository/build failure. If the channels return later they
        # will be detected automatically and receive the official schedule.
        print('JD League EPG skipped: no JD League channels currently present in freewifi')
        return
    text = fetch_official_text()
    next_day, title, desc = parse_next_schedule(text)
    apply_epg(channels, title, desc)
    print(f'JD League EPG applied: {len(channels)} channels / next={next_day.isoformat()} / {title}')


if __name__ == '__main__':
    main()
