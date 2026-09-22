import datetime
import html
import re
import urllib.request
import xml.etree.ElementTree as ET

JST = datetime.timezone(datetime.timedelta(hours=9))
TODAY = datetime.datetime.now(JST).date()
DATE = TODAY.strftime('%Y%m%d')
M3U = 'boatrace_today.m3u'
EPG = 'epg.xml'

TVG_TO_CODE = {
    'boat.kiryu':'01','boat.toda':'02','boat.edogawa':'03','boat.heiwajima':'04',
    'boat.tamagawa':'05','boat.hamanako':'06','boat.gamagori':'07','boat.tokoname':'08',
    'boat.tsu':'09','boat.mikuni':'10','boat.biwako':'11','boat.suminoe':'12',
    'boat.amagasaki':'13','boat.naruto':'14','boat.marugame':'15','boat.kojima':'16',
    'boat.miyajima':'17','boat.tokuyama':'18','boat.shimonoseki':'19','boat.wakamatsu':'20',
    'boat.ashiya':'21','boat.fukuoka':'22','boat.karatsu':'23','boat.omura':'24',
}
CODE_NAME = {
    '01':'桐生','02':'戸田','03':'江戸川','04':'平和島','05':'多摩川','06':'浜名湖',
    '07':'蒲郡','08':'常滑','09':'津','10':'三国','11':'びわこ','12':'住之江',
    '13':'尼崎','14':'鳴門','15':'丸亀','16':'児島','17':'宮島','18':'徳山',
    '19':'下関','20':'若松','21':'芦屋','22':'福岡','23':'からつ','24':'大村',
}

def fetch(url):
    req = urllib.request.Request(url, headers={
        'User-Agent':'Mozilla/5.0',
        'Accept-Language':'ja-JP,ja;q=0.9',
        'Cache-Control':'no-cache',
        'Referer':'https://www.boatrace.jp/'
    })
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode('utf-8', errors='ignore')

def strip_tags(src):
    src = re.sub(r'(?is)<script.*?</script>', ' ', src or '')
    src = re.sub(r'(?is)<style.*?</style>', ' ', src)
    src = re.sub(r'(?s)<[^>]+>', ' ', src)
    src = html.unescape(src)
    return re.sub(r'\s+', ' ', src).strip()

def race_times(src):
    raw = html.unescape(src or '')
    compact = re.sub(r'\s+', ' ', raw)
    found = {}
    for n in range(1, 13):
        for pat in (
            rf'>\s*{n}R\s*<.*?([0-2]?\d:[0-5]\d)',
            rf'\b{n}R\b.{{0,2200}}?([0-2]?\d:[0-5]\d)',
        ):
            m = re.search(pat, compact, re.I | re.S)
            if m:
                found[n] = m.group(1)
                break
    if len(found) < 12:
        plain = strip_tags(raw)
        pos = plain.find('締切予定時刻')
        if pos >= 0:
            window = plain[pos:pos + 2400]
            seq = re.findall(r'(?<!\d)([0-2]?\d:[0-5]\d)(?!\d)', window)
            uniq = []
            for hm in seq:
                if not uniq or hm != uniq[-1]:
                    uniq.append(hm)
            if len(uniq) >= 12:
                return [(n, uniq[n-1]) for n in range(1, 13)]
    if len(found) < 12:
        plain = strip_tags(raw)
        m = re.search(
            r'1R\s+2R\s+3R\s+4R\s+5R\s+6R\s+7R\s+8R\s+9R\s+10R\s+11R\s+12R(.{0,2600})',
            plain,
            re.S,
        )
        if m:
            seq = re.findall(r'(?<!\d)([0-2]?\d:[0-5]\d)(?!\d)', m.group(1))
            if len(seq) >= 12:
                return [(n, seq[n-1]) for n in range(1, 13)]
    return [(n, found[n]) for n in sorted(found)]

def day_type(times):
    if not times:
        return ('開催','🚤')
    h = int(times[0][1].split(':')[0])
    last_h = int(times[-1][1].split(':')[0])
    if last_h >= 22:
        return ('ミッドナイト','⭐')
    if h < 10:
        return ('モーニング','🌅')
    if h >= 14:
        return ('ナイター','🌙')
    return ('デイ','☀️')

def xdt(dt):
    return dt.strftime('%Y%m%d%H%M%S +0900')

def add(root, ch, start, stop, title, desc=''):
    if stop <= start:
        return
    p = ET.SubElement(root, 'programme', start=xdt(start), stop=xdt(stop), channel=ch)
    ET.SubElement(p, 'title', lang='ja').text = title
    if desc:
        ET.SubElement(p, 'desc', lang='ja').text = desc

m3u = open(M3U, encoding='utf-8-sig').read()
active = []
for tvg, code in TVG_TO_CODE.items():
    if f'tvg-id="{tvg}"' in m3u:
        active.append((tvg, code))

root = ET.parse(EPG).getroot()
start_prefix = DATE
changed = 0
print('BOAT active from M3U:', ','.join(code for _, code in active))

day_start = datetime.datetime.strptime(f'{DATE} 08:00', '%Y%m%d %H:%M').replace(tzinfo=JST)
day_end = datetime.datetime.strptime(f'{DATE} 23:59', '%Y%m%d %H:%M').replace(tzinfo=JST)

for tvg, code in active:
    existing = [
        p for p in root.findall('programme')
        if p.get('channel') == tvg and (p.get('start') or '').startswith(start_prefix)
    ]
    real_race = []
    for p in existing:
        text = ' '.join(p.itertext())
        if re.search(r'(?:\b(?:[1-9]|1[0-2])R\b|[❶❷❸❹❺❻❼❽❾❿⓫⓬]ℛ)', text):
            real_race.append(p)
    if real_race:
        print(f'BOAT {code}: existing race EPG OK ({len(real_race)})')
        continue

    url = f'https://www.boatrace.jp/owpc/pc/race/raceindex?hd={DATE}&jcd={code}'
    try:
        src = fetch(url)
        times = race_times(src)
    except Exception as e:
        print(f'BOAT {code} fetch failed: {e}')
        if code == '24':
            for p in existing:
                root.remove(p)
            add(root, tvg, day_start, day_end,
                '⚠️ BOAT EPG診断 大村: 公式ページ取得失敗',
                f'URL={url}\nERROR={type(e).__name__}: {e}')
            changed += 1
        continue

    if len(times) < 2:
        print(f'BOAT {code}: race times not found ({len(times)})')
        if code == '24':
            plain = strip_tags(src)
            sample = plain[:1200]
            for p in existing:
                root.remove(p)
            add(root, tvg, day_start, day_end,
                f'⚠️ BOAT EPG診断 大村: 時刻抽出失敗 ({len(times)}件)',
                f'取得HTML文字数={len(src)}\n先頭サンプル={sample}')
            changed += 1
        continue

    print(f'BOAT {code}: race times = {times}')
    for p in existing:
        root.remove(p)

    typ, emo = day_type(times)
    name = CODE_NAME[code]
    dts = []
    for n, hm in times:
        dt = datetime.datetime.strptime(f'{DATE} {hm}', '%Y%m%d %H:%M').replace(tzinfo=JST)
        dts.append((n, hm, dt))

    pre = max(day_start, dts[0][2] - datetime.timedelta(minutes=20))
    if day_start < pre:
        add(root, tvg, day_start, pre,
            f'⏳ 待機 {code} {name} {emo}{typ}',
            f'🚤 BOATRACE{name}\n1R {dts[0][1]} 発走予定')

    for i, (n, hm, dt) in enumerate(dts):
        bs = max(pre, dt - datetime.timedelta(minutes=10))
        be = dts[i+1][2] - datetime.timedelta(minutes=10) if i + 1 < len(dts) else dt + datetime.timedelta(minutes=30)
        if be <= bs:
            be = dt + datetime.timedelta(minutes=15)
        add(root, tvg, bs, min(be, day_end),
            f'🚤 {code} {name} {n}R {hm}発走 {emo}{typ}',
            f'🚤 BOATRACE{name}\n{emo} 開催区分: {typ}\n⏰ 発走予定: {hm}')

    finish = dts[-1][2] + datetime.timedelta(minutes=30)
    if finish < day_end:
        add(root, tvg, finish, day_end,
            f'🏁✨ 本日の開催は終了しました 🚤🌙 {code} {name}（ボートレース）')

    changed += 1
    print(f'BOAT EPG repaired from M3U: {code} {name} / {typ} / {len(times)}R')

if changed:
    programmes = list(root.findall('programme'))
    for p in programmes:
        root.remove(p)
    programmes.sort(key=lambda p: (p.get('start',''), p.get('channel','')))
    for p in programmes:
        root.append(p)
    ET.ElementTree(root).write(EPG, encoding='utf-8', xml_declaration=True)

print(f'BOAT M3U active repair: {changed} venue(s)')
