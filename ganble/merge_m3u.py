from pathlib import Path
from urllib.parse import quote
import datetime
import re
import xml.etree.ElementTree as ET

BASE = Path(__file__).resolve().parent
OUT = BASE / 'public_sports.m3u'
EPG = BASE / 'epg.xml'
RAW = 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main'
EPG_URL = RAW + '/epg.xml'
JST = datetime.timezone(datetime.timedelta(hours=9))

INPUTS = [
    ('競輪', BASE/'keirin_master.m3u'),
    ('地方競馬', BASE/'keiba_master.m3u'),
    ('オートレース', BASE/'autorace_master.m3u'),
    ('ボートレース', BASE/'boatrace_today.m3u'),
]

JRA = [
    ('jra.gch.hq','グリーンチャンネル HQ','グリーンチャンネル（高画質）','gchmain.m3u8','public_sports_logos_github_43/jra_quality/gch_hq.png'),
    ('jra.gch.lq','グリーンチャンネル LQ','グリーンチャンネル（低画質）','gchmain_LQ.m3u8','public_sports_logos_github_43/jra_quality/gch_lq.png'),
    ('jra.east.hq','JRA EAST HQ','JRA EAST（高画質）','EAST_test.m3u8','public_sports_logos_github_43/jra_quality/east_hq.png'),
    ('jra.east.lq','JRA EAST LQ','JRA EAST（低画質）','EAST_test_LQ.m3u8','public_sports_logos_github_43/jra_quality/east_lq.png'),
    ('jra.west.hq','JRA WEST HQ','JRA WEST（高画質）','WEST_master .m3u8','public_sports_logos_github_43/jra_quality/west_hq.png'),
    ('jra.west.lq','JRA WEST LQ','JRA WEST（低画質）','WEST_master_LQ.m3u8','public_sports_logos_github_43/jra_quality/west_lq.png'),
    ('jra.local.hq','JRA LOCAL WEB5 HQ','JRA LOCAL WEB5（高画質）','hokaido_master (1).m3u8','public_sports_logos_github_43/jra_quality/local_hq.png'),
    ('jra.local.lq','JRA LOCAL WEB5 LQ','JRA LOCAL WEB5（低画質）','hokaido_master_LQ.m3u8','public_sports_logos_github_43/jra_quality/local_lq.png'),
]


def priority_order():
    h = datetime.datetime.now(JST).hour
    if h < 11:
        seq = ['モーニング','デイ','通常','薄暮','サマータイム','ナイター','ミッドナイト','オーバーミッドナイト']
        label = '朝'
    elif h < 17:
        seq = ['デイ','通常','薄暮','サマータイム','ナイター','ミッドナイト','オーバーミッドナイト','モーニング']
        label = '昼'
    else:
        seq = ['薄暮','サマータイム','ナイター','ミッドナイト','オーバーミッドナイト','デイ','通常','モーニング']
        label = '夕'
    return {name:i for i,name in enumerate(seq)}, label


def read_entries(path):
    if not path.exists():
        return []
    lines = path.read_text(encoding='utf-8-sig', errors='replace').replace('\r\n','\n').replace('\r','\n').split('\n')
    entries=[]
    i=0
    while i < len(lines):
        if lines[i].strip().startswith('#EXTINF:'):
            block=[lines[i].strip()]
            i += 1
            while i < len(lines):
                s=lines[i].strip()
                if s.startswith('#EXTINF:') or s.startswith('## '):
                    break
                if s:
                    block.append(s)
                    if not s.startswith('#'):
                        i += 1
                        break
                i += 1
            if block and not block[-1].startswith('#'):
                entries.append(block)
            continue
        i += 1
    return entries


def attr(ext, name):
    m = re.search(rf'{re.escape(name)}="([^"]*)"', ext)
    return m.group(1).strip() if m else ''


def parse_xmltv(value):
    m = re.match(r'(\d{14})\s*([+-]\d{4})?', str(value or '').strip())
    if not m:
        return None
    digits, off = m.groups()
    if off:
        return datetime.datetime.strptime(f'{digits} {off}', '%Y%m%d%H%M%S %z').astimezone(JST)
    return datetime.datetime.strptime(digits, '%Y%m%d%H%M%S').replace(tzinfo=JST)


def classify(text, first, last):
    for key in ('オーバーミッドナイト','ミッドナイト','ナイター','サマータイム','薄暮','モーニング','デイ','通常'):
        if key in text:
            return key
    if last and (last.hour * 60 + last.minute) > 23 * 60 + 40:
        return 'オーバーミッドナイト'
    if not first:
        return '通常'
    h = first.hour
    if h < 10: return 'モーニング'
    if h >= 19: return 'ミッドナイト'
    if h >= 14: return 'ナイター'
    return 'デイ'


def today_order():
    if not EPG.exists():
        return {}, 'EPGなし'
    root = ET.parse(EPG).getroot()
    today = datetime.datetime.now(JST).date()
    by_ch = {}
    bad = ('本日は開催していません','データ取得準備中','開催情報確認待ち')
    for p in root.findall('programme'):
        cid = p.get('channel','')
        if not cid.startswith(('keirin.','chihou.','keiba.','auto.','boat.')):
            continue
        start = parse_xmltv(p.get('start'))
        stop = parse_xmltv(p.get('stop'))
        if not start:
            continue
        logical = start.date() if start.hour >= 4 else start.date() - datetime.timedelta(days=1)
        if logical != today:
            continue
        text = (p.findtext('title') or '') + ' ' + (p.findtext('desc') or '')
        if any(x in text for x in bad):
            continue
        info = by_ch.setdefault(cid, {'starts':[], 'stops':[], 'text':''})
        info['starts'].append(start)
        if stop: info['stops'].append(stop)
        info['text'] += ' ' + text

    priorities, band = priority_order()
    order = {}
    for cid, info in by_ch.items():
        first = min(info['starts']) if info['starts'] else None
        last = max(info['stops']) if info['stops'] else first
        typ = classify(info['text'], first, last)
        order[cid] = (priorities.get(typ, 50), first or datetime.datetime.max.replace(tzinfo=JST))
    return order, band


def sorted_entries(path, order):
    entries = read_entries(path)
    decorated=[]
    for idx, block in enumerate(entries):
        cid = attr(block[0], 'tvg-id')
        if cid in order:
            decorated.append(((0,)+order[cid]+(idx,), block))
        else:
            decorated.append(((1,99,datetime.datetime.max.replace(tzinfo=JST),idx), block))
    decorated.sort(key=lambda x:x[0])
    return [b for _,b in decorated]


def append_file(out, label, path, order):
    entries = sorted_entries(path, order)
    if not entries:
        print(label, '0 <-', path.name)
        return 0
    out.append('## ' + label)
    for block in entries:
        out.extend(block)
        out.append('')
    print(label, len(entries), '<-', path.name)
    return len(entries)


def raw(filename):
    return RAW + '/' + quote(filename)


def main():
    out=[f'#EXTM3U url-tvg="{EPG_URL}"','']
    order, band = today_order()
    total=0
    print('時間帯:', band, '並べ替え対象:', len(order), 'ch')
    for label,path in INPUTS:
        total += append_file(out,label,path,order)

    out.append('## 中央競馬')
    for tvg,name,display,filename,logo in JRA:
        out += [f'#EXTINF:-1 tvg-id="{tvg}" tvg-name="{name}" tvg-logo="{raw(logo)}" group-title="中央競馬",{display}',raw(filename),'']
        total += 1

    OUT.write_text('\n'.join(out).rstrip()+'\n', encoding='utf-8')
    print('M3U一本化 完了:', total, 'ch / YouTubeなし')


if __name__ == '__main__':
    main()
