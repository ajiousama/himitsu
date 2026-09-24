from pathlib import Path
import json, re

FREEWIFI = Path('freewifi')
STATUS = Path('today_jra_status.json')
START = '# === JRA_EARPHONE_QUALITY_START ==='
END = '# === JRA_EARPHONE_QUALITY_END ==='
RAW = 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main'
LOGO = RAW + '/public_sports_logos_github_43/jra_quality'

CHANNELS = [
    ('jra.gch.hq','グリーンチャンネル HQ','gchmain.m3u8','gch_hq.png','jra.gch'),
    ('jra.gch.lq','グリーンチャンネル LQ','gchmain_LQ.m3u8','gch_lq.png','jra.gch'),
    ('jra.east.hq','JRA EAST HQ','EAST_test.m3u8','east_hq.png','jra.east'),
    ('jra.east.lq','JRA EAST LQ','EAST_test_LQ.m3u8','east_lq.png','jra.east'),
    ('jra.west.hq','JRA WEST HQ','WEST_master%20.m3u8','west_hq.png','jra.west'),
    ('jra.west.lq','JRA WEST LQ','WEST_master_LQ.m3u8','west_lq.png','jra.west'),
    ('jra.local.hq','JRA LOCAL WEB5 HQ','hokaido_master%20(1).m3u8','local_hq.png','jra.hokkaido'),
    ('jra.local.lq','JRA LOCAL WEB5 LQ','hokaido_master_LQ.m3u8','local_lq.png','jra.hokkaido'),
]


def active_sources():
    try:
        d=json.loads(STATUS.read_text(encoding='utf-8-sig'))
        if int(d.get('active_count',0)) <= 0:
            return set()
        return {cid for cid,v in (d.get('channels') or {}).items() if v.get('active')}
    except Exception:
        return set()


def strip_managed(text):
    text=re.sub(re.escape(START)+r'.*?'+re.escape(END)+r'\n?', '', text, flags=re.S)
    ids={x[0] for x in CHANNELS}
    lines=text.splitlines(); out=[]; i=0
    while i < len(lines):
        line=lines[i]
        m=re.search(r'tvg-id="([^"]+)"',line) if line.startswith('#EXTINF:') else None
        if m and m.group(1) in ids:
            i += 2
            if i < len(lines) and not lines[i].strip(): i += 1
            continue
        out.append(line); i += 1
    return '\n'.join(out).rstrip()+'\n'


def main():
    text=FREEWIFI.read_text(encoding='utf-8-sig',errors='replace')
    text=strip_managed(text)
    active=active_sources()
    if not active:
        FREEWIFI.write_text(text,encoding='utf-8')
        print('JRA inactive: earphone HQ/LQ block removed')
        return
    rows=[]
    for cid,name,stream,logo,source in CHANNELS:
        # Every quality pair follows today_jra_status exactly.
        # In particular, GCH is active only when the actual Green Channel guide
        # contains an overseas-racing or local-racing broadcast trigger.
        if source not in active:
            continue
        rows += [f'#EXTINF:-1 tvg-id="{cid}" tvg-name="{name}" tvg-logo="{LOGO}/{logo}" group-title="今日の開催場",{name}', f'{RAW}/{stream}', '']
    block=START+'\n## JRA / GCH HQ・LQ（earphone正本）\n'+'\n'.join(rows).rstrip()+'\n'+END+'\n'
    anchor='# === TODAY_JRA_END ==='
    text=text.replace(anchor,block+anchor,1) if anchor in text else text.rstrip()+'\n\n'+block
    FREEWIFI.write_text(text.rstrip()+'\n',encoding='utf-8')
    print('earphone JRA quality channels installed:', len(rows)//3)

if __name__=='__main__': main()
