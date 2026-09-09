from pathlib import Path
from datetime import datetime, timezone, timedelta, time
import json
import re
import xml.etree.ElementTree as ET
from sports_race_time import race_time

FREEWIFI = Path('freewifi')
STATUS_JSON = Path('today_public_sports_status.json')
PUBLIC_M3U = Path('ganble')
PUBLIC_EPG = Path('public_sports_epg_local.xml')
START = '# === TODAY_PUBLIC_SPORTS_START ==='
END = '# === TODAY_PUBLIC_SPORTS_END ==='
GROUP = '今日の開催場'
RAW_BASE = 'https://raw.githubusercontent.com/ajiousama/himitsu/main'
LOGO_PROXY = 'https://images.weserv.nl/?url=raw.githubusercontent.com/ajiousama/himitsu/main'

def venue_png(name):
    return f'{LOGO_PROXY}/logos/public_sports/venues/{name}&output=png'

# Every KEIRIN venue is mapped explicitly. The public-sports master can omit
# tvg-logo, and today's active set changes daily, so non-hosting/paused venues
# must already have a valid logo before their next event becomes active.
KEIRIN_LOGOS = {
    'keirin.hakodate': venue_png('keirin_hakodate.svg'),
    'keirin.aomori': venue_png('keirin_aomori.svg'),
    'keirin.iwakitaira': venue_png('keirin_iwakitaira.svg'),
    'keirin.yahiko': venue_png('keirin_yahiko.svg'),
    'keirin.maebashi': venue_png('keirin_maebashi.svg'),
    'keirin.toride': venue_png('keirin_toride.svg'),
    'keirin.utsunomiya': venue_png('keirin_utsunomiya.svg'),
    'keirin.omiya': venue_png('keirin_omiya.svg'),
    'keirin.seibuen': venue_png('keirin_seibuen.svg'),
    'keirin.keiogatsu': venue_png('keirin_keiogatsu.svg'),
    'keirin.tachikawa': venue_png('keirin_tachikawa.svg'),
    'keirin.matsudo': venue_png('keirin_matsudo.svg'),
    'keirin.kawasaki': venue_png('keirin_kawasaki.svg'),
    'keirin.hiratsuka': venue_png('keirin_hiratsuka.svg'),
    'keirin.odawara': venue_png('keirin_odawara.svg'),
    'keirin.ito': venue_png('keirin_ito.svg'),
    'keirin.shizuoka': venue_png('keirin_shizuoka.svg'),
    'keirin.nagoya': venue_png('keirin_nagoya.svg'),
    'keirin.gifu': venue_png('keirin_gifu.svg'),
    'keirin.ogaki': venue_png('keirin_ogaki.svg'),
    'keirin.toyohashi': venue_png('keirin_toyohashi.svg'),
    'keirin.toyama': venue_png('keirin_toyama.svg'),
    'keirin.matsusaka': venue_png('keirin_matsusaka.svg'),
    'keirin.yokkaichi': venue_png('keirin_yokkaichi.svg'),
    'keirin.fukui': venue_png('keirin_fukui.svg'),
    'keirin.nara': venue_png('keirin_nara.svg'),
    'keirin.mukomachi': venue_png('keirin_mukomachi.png'),
    'keirin.wakayama': venue_png('keirin_wakayama.svg'),
    'keirin.kishiwada': venue_png('keirin_kishiwada.svg'),
    'keirin.hiroshima': venue_png('keirin_hiroshima.svg'),
    'keirin.hofu': venue_png('keirin_hofu.svg'),
    'keirin.takamatsu': venue_png('keirin_takamatsu.svg'),
    'keirin.komatsushima': venue_png('keirin_komatsushima.svg'),
    'keirin.kochi': venue_png('keirin_kochi.svg'),
    'keirin.matsuyama': venue_png('keirin_matsuyama.svg'),
    'keirin.kokura': venue_png('keirin_kokura.svg'),
    'keirin.kurume': venue_png('keirin_kurume.svg'),
    'keirin.takeo': venue_png('keirin_takeo.svg'),
    'keirin.sasebo': venue_png('keirin_sasebo.svg'),
    'keirin.beppu': venue_png('keirin_beppu.svg'),
    'keirin.kumamoto': venue_png('keirin_kumamoto.png'),
    'keirin.pist6': venue_png('keirin_pist6.png'),
    'keirin.tamano': venue_png('keirin_tamano.svg'),
}

# Restore the adopted AUTO RACE venue logos from earphone1981 instead of the
# unintended locally regenerated motorcycle-card set.
AUTO_LOGOS = {
    'auto.kawaguchi': 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/public_sports_logos_github_43/autorace/kawaguchi.png',
    'auto.isesaki': 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/public_sports_logos_github_43/autorace/isesaki.png',
    'auto.hamamatsu': 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/public_sports_logos_github_43/autorace/hamamatsu.png',
    'auto.sanyo': 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/public_sports_logos_github_43/autorace/sanyo.png',
    'auto.iizuka': 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/public_sports_logos_github_43/autorace/iizuka.png',
}

def local_logo(cid):
    if cid.startswith('chihou.'):
        slug = cid.split('.', 1)[1]
        slug = {'kawasaki_keiba': 'kawasaki', 'nagoya_keiba': 'nagoya', 'kochi_keiba': 'kochi'}.get(slug, slug)
        return f'{RAW_BASE}/logos/public_sports/venues/localrace_{slug}.png'
    if cid.startswith('keirin.'):
        return KEIRIN_LOGOS.get(cid)
    if cid.startswith('auto.'):
        return AUTO_LOGOS.get(cid)
    return None

JST = timezone(timedelta(hours=9))
# BOAT Auto v3 exclusively owns every boat.* entry and the TODAY_BOAT block.
# This builder must never parse, remove, recreate, reorder, or otherwise mutate BOAT.
TARGET_SECTIONS = {'競輪', '地方競馬', 'オートレース'}
NON_EVENT_WORDS = ('本日非開催','非開催','開催していません','開催予定はありません','本日開催なし','開催なし','次回開催','データ取得準備中','休止中','休止','準備中','現在準備中','本日の開催は終了しました','翌日開催予定','仮時間')


def parse_m3u(text):
    entries = {}
    section = ''
    lines = text.splitlines(); i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('## '):
            section = line[3:].strip(); i += 1; continue
        if not line.startswith('#EXTINF:'):
            i += 1; continue
        block = [line]; j = i + 1
        while j < len(lines) and not lines[j].startswith('#EXTINF:') and not lines[j].startswith('## '):
            if lines[j].strip(): block.append(lines[j])
            j += 1
        m = re.search(r'tvg-id="([^"]+)"', line)
        if m and section in TARGET_SECTIONS:
            cid = m.group(1)
            if not cid.startswith('boat.'):
                entries[cid] = (section, block)
        i = j
    return entries


def parse_xmltv_time(value):
    m = re.match(r'^(\d{14})\s*([+-]\d{4})?', str(value or '').strip())
    if not m: return None
    d, off = m.groups()
    try:
        if off:
            return datetime.strptime(f'{d} {off}', '%Y%m%d%H%M%S %z').astimezone(JST)
        return datetime.strptime(d, '%Y%m%d%H%M%S').replace(tzinfo=JST)
    except Exception:
        return None


def race_datetime(today, hhmm):
    try:
        hh, mm = map(int, hhmm.split(':'))
        if mm < 0 or mm > 59 or hh < 0:
            return None
        day_add, hour = divmod(hh, 24)
        return datetime.combine(today + timedelta(days=day_add), time(hour, mm), tzinfo=JST)
    except Exception:
        return None


def epg_state():
    if not PUBLIC_EPG.exists():
        raise SystemExit('public_sports_epg_local.xml missing')
    try:
        root = ET.parse(PUBLIC_EPG).getroot()
    except Exception as e:
        raise SystemExit(f'public_sports_epg_local.xml parse failed: {e}')

    now = datetime.now(JST); today = now.date()
    real = set(); modes = {}; next_race = {}
    bad = 0
    for p in root.findall('programme'):
        try:
            cid = p.get('channel') or ''
            if not cid or cid.startswith('boat.'):
                continue
            start = parse_xmltv_time(p.get('start'))
            if not start:
                bad += 1; continue
            title = (p.findtext('title') or '').strip()
            desc = (p.findtext('desc') or '').strip()
            race = race_time(p)
            if (race['day'] != today if race else start.date() != today):
                continue
            compact = ''.join(title.split())
            if not compact or any(x in compact for x in NON_EVENT_WORDS):
                continue
            real.add(cid)
            joined = title + ' ' + desc
            modes[cid] = ('overnight' if 'オーバーミッドナイト' in joined else 'midnight' if 'ミッドナイト' in joined else 'night' if 'ナイター' in joined else 'morning' if 'モーニング' in joined else 'twilight' if '薄暮' in joined else 'day')
            if race and race['dt'] >= now:
                item = {'race': race['race'], 'start': race['start'], 'title': title, '_dt': race['dt']}
                if cid not in next_race or race['dt'] < next_race[cid]['_dt']:
                    next_race[cid] = item
        except Exception as e:
            bad += 1
            print(f'EPG row skipped: {e}')
            continue
    for v in next_race.values(): v.pop('_dt', None)
    print(f'EPG state: active={len(real)} next={len(next_race)} skipped={bad}')
    return real, modes, next_race


def entry_name(block):
    m = re.search(r'tvg-name="([^"]+)"', block[0])
    return m.group(1) if m else block[0].rsplit(',',1)[-1].strip()


def sanitize_extinf(line):
    mid = re.search(r'tvg-id="([^"]+)"', line)
    cid = mid.group(1) if mid else ''
    logo = local_logo(cid)
    if logo:
        if 'tvg-logo=' in line:
            line = re.sub(r'tvg-logo="[^"]*"', f'tvg-logo="{logo}"', line, count=1)
        else:
            pos = line.find(',')
            line = line[:pos] + f' tvg-logo="{logo}"' + line[pos:] if pos >= 0 else line
    if 'group-title=' in line:
        line = re.sub(r'group-title="[^"]*"', f'group-title="{GROUP}"', line, count=1)
    else:
        pos = line.find(',')
        line = line[:pos] + f' group-title="{GROUP}"' + line[pos:] if pos >= 0 else line
    return line


def strip_ids(text, ids):
    # Safety invariant: this non-BOAT builder can never remove a boat.* entry,
    # even if a future caller accidentally passes one in ids.
    ids = {cid for cid in ids if not cid.startswith('boat.')}
    lines = text.splitlines(); out=[]; i=0
    while i < len(lines):
        line = lines[i]
        if line.startswith('#EXTINF:'):
            m = re.search(r'tvg-id="([^"]+)"', line)
            if m and m.group(1) in ids:
                i += 1
                while i < len(lines) and not lines[i].startswith('#EXTINF:') and not lines[i].startswith('## ') and not lines[i].startswith('# ==='): i += 1
                continue
        out.append(line); i += 1
    return '\n'.join(out).rstrip() + '\n'


def replace_block(text, payload):
    pat = re.compile(re.escape(START)+r'.*?'+re.escape(END)+r'\n?', re.S)
    if pat.search(text): return pat.sub(lambda _m: payload+'\n', text, count=1)
    anchor = '# === GENERAL_YOUTUBE_MANAGED_START ==='
    return text.replace(anchor, payload+'\n\n'+anchor, 1) if anchor in text else text.rstrip()+'\n\n'+payload+'\n'


def main():
    if not FREEWIFI.exists() or not PUBLIC_M3U.exists():
        raise SystemExit('freewifi/ganble missing')
    # BOAT Auto v3 owns the complete OpenAPI race grid. This general builder
    # consumes the already-generated local EPG and never mutates BOAT state.
    real, modes, next_race = epg_state()
    entries = parse_m3u(PUBLIC_M3U.read_text(encoding='utf-8-sig', errors='replace'))
    if not entries:
        raise SystemExit('ganble has no non-BOAT public-sports master entries')
    missing_keirin_logos = sorted(cid for cid in entries if cid.startswith('keirin.') and cid not in KEIRIN_LOGOS)
    if missing_keirin_logos:
        raise SystemExit('missing KEIRIN logo mappings: ' + ', '.join(missing_keirin_logos))
    rows=[]; status={}
    for cid, (section, block) in entries.items():
        if cid.startswith('boat.') or cid not in real:
            continue
        try:
            item_block = block[:]
            item_block[0] = sanitize_extinf(item_block[0])
            name = entry_name(item_block); nr = next_race.get(cid)
            rows.append({'id':cid,'name':name,'block':item_block,'next_race':nr})
            status[cid] = {'section':section,'name':name,'mode':modes.get(cid,'day'),'source':'ajiousama local direct EPG','epg_available':True,'next_race':nr,'next_race_text':f"次は {nr['race']}R {nr['start']}発走" if nr else '本日開催／次レースなし'}
        except Exception as e:
            print(f'M3U row skipped {cid}: {e}')
    rows.sort(key=lambda r: ((int(r['next_race']['start'][:2])*60+int(r['next_race']['start'][3:])) if r['next_race'] else 2000, r['name']))
    body=[]
    for r in rows: body += r['block'] + ['']
    managed = START+'\n## 今日の開催場\n'+'\n'.join(body).rstrip()+('\n' if body else '')+END
    base = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    owned_ids = {cid for cid in entries if not cid.startswith('boat.')}
    base = strip_ids(base, owned_ids)
    FREEWIFI.write_text(replace_block(base, managed).rstrip()+'\n', encoding='utf-8')
    STATUS_JSON.write_text(json.dumps({'generated_at':datetime.now(JST).isoformat(),'channels':{r['id']:status[r['id']] for r in rows}}, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print('Today public sports local:', len(rows))

if __name__ == '__main__': main()
