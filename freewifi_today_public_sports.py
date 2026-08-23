from pathlib import Path
from datetime import datetime, timezone, timedelta
import re
import urllib.request
import xml.etree.ElementTree as ET

FREEWIFI = Path('freewifi')
PUBLIC_M3U_URL = 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/public_sports.m3u'
PUBLIC_EPG_URL = 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/epg.xml'
START = '# === TODAY_PUBLIC_SPORTS_START ==='
END = '# === TODAY_PUBLIC_SPORTS_END ==='
GROUP = '今日の開催場'
JST = timezone(timedelta(hours=9))
TARGET_SECTIONS = {'競輪', '地方競馬', 'ボート', 'オート'}
NON_EVENT_WORDS = ('本日非開催', '非開催', '次回開催', 'データ取得準備中', '休止中', '休止')


def fetch_text(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode('utf-8-sig', errors='replace')


def parse_m3u(text):
    entries = {}
    section = ''
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('## '):
            section = line[3:].strip()
            i += 1
            continue
        if line.startswith('#EXTINF:'):
            block = [lines[i]]
            j = i + 1
            while j < len(lines) and not lines[j].startswith('#EXTINF:') and not lines[j].startswith('## '):
                if lines[j].strip():
                    block.append(lines[j])
                j += 1
            m = re.search(r'tvg-id="([^"]+)"', line)
            if m and section in TARGET_SECTIONS:
                entries[m.group(1)] = (section, block)
            i = j
            continue
        i += 1
    return entries


def parse_xmltv_time(s):
    if not s:
        return None
    s = s.strip()
    m = re.match(r'^(\d{14})\s*([+-]\d{4})?', s)
    if not m:
        return None
    base = datetime.strptime(m.group(1), '%Y%m%d%H%M%S')
    off = m.group(2)
    if off:
        sign = 1 if off[0] == '+' else -1
        hh = int(off[1:3]); mm = int(off[3:5])
        tz = timezone(sign * timedelta(hours=hh, minutes=mm))
        return base.replace(tzinfo=tz)
    return base.replace(tzinfo=JST)


def active_channels(epg_text):
    root = ET.fromstring(epg_text)
    today = datetime.now(JST).date()
    active = set()
    for p in root.findall('programme'):
        ch = p.get('channel') or ''
        start = parse_xmltv_time(p.get('start'))
        stop = parse_xmltv_time(p.get('stop'))
        if not start:
            continue
        local_start = start.astimezone(JST)
        local_stop = stop.astimezone(JST) if stop else local_start
        if local_start.date() != today and local_stop.date() != today:
            continue
        title = ''.join((p.findtext('title') or '').split())
        if any(word in title for word in NON_EVENT_WORDS):
            continue
        active.add(ch)
    return active


def rewrite_group(extinf):
    if 'group-title=' in extinf:
        return re.sub(r'group-title="[^"]*"', f'group-title="{GROUP}"', extinf, count=1)
    comma = extinf.find(',')
    if comma >= 0:
        return extinf[:comma] + f' group-title="{GROUP}"' + extinf[comma:]
    return extinf + f' group-title="{GROUP}"'


def prune_abema_rakuten(text):
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith('#EXTINF:'):
            out.append(line)
            i += 1
            continue
        block = [line]
        j = i + 1
        while j < len(lines) and not lines[j].startswith('#EXTINF:') and not lines[j].startswith('## '):
            block.append(lines[j])
            j += 1
        low = line.lower()
        drop = False
        if 'abema' in low or 'アベマ' in line:
            drop = not ('アニメ' in line or 'anime' in low)
        elif 'rakuten' in low or '楽天' in line:
            keep_rail = any(k in line for k in ('鉄道', '電車', '列車')) or 'rail' in low or 'train' in low
            keep_adult = any(k in line for k in ('アダルト', '成人', 'R18', 'R-18', '18禁')) or 'adult' in low
            drop = not (keep_rail or keep_adult)
        if not drop:
            out.extend(block)
        i = j
    return '\n'.join(out).rstrip() + '\n'


def replace_block(text, block):
    pat = re.compile(re.escape(START) + r'.*?' + re.escape(END) + r'\n?', re.S)
    text = pat.sub('', text)
    anchor = '# === GENERAL_YOUTUBE_MANAGED_START ==='
    if anchor in text:
        text = text.replace(anchor, block + '\n\n' + anchor, 1)
    else:
        text = text.rstrip() + '\n\n' + block + '\n'
    return text


def main():
    base = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    base = prune_abema_rakuten(base)
    m3u = fetch_text(PUBLIC_M3U_URL)
    epg = fetch_text(PUBLIC_EPG_URL)
    entries = parse_m3u(m3u)
    active = active_channels(epg)

    selected = []
    counts = {k: 0 for k in TARGET_SECTIONS}
    for tvg, (section, block) in entries.items():
        if tvg not in active:
            continue
        block = block[:]
        block[0] = rewrite_group(block[0])
        selected.extend(block)
        selected.append('')
        counts[section] += 1

    body = '\n'.join(selected).rstrip()
    block = START + '\n## 今日の開催場\n' + body + ('\n' if body else '') + END
    base = replace_block(base, block)
    FREEWIFI.write_text(base.rstrip() + '\n', encoding='utf-8')

    print('Today public sports synced:', sum(counts.values()))
    for k in ('地方競馬', '競輪', 'ボート', 'オート'):
        print(f'{k}: {counts.get(k, 0)}')


if __name__ == '__main__':
    main()
