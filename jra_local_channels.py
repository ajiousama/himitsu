from pathlib import Path
import json, re

FREEWIFI = Path('freewifi')
STATUS = Path('today_jra_status.json')
START = '# === JRA_LOCAL_QUALITY_START ==='
END = '# === JRA_LOCAL_QUALITY_END ==='
RAW = 'https://raw.githubusercontent.com/ajiousama/himitsu/main'
LOGO = RAW + '/logos/public_sports/jra_quality'

CHANNELS = [
    ('jra.gch.hq','グリーンチャンネル HQ','gchmain_master.m3u8','gch_hq.png','jra.gch'),
    ('jra.gch.lq','グリーンチャンネル LQ','gchmain_LQ.m3u8','gch_lq.png','jra.gch'),
    ('jra.east.hq','JRA EAST HQ','gch_east_master.m3u8','gch_hq.png','jra.east'),
    ('jra.east.lq','JRA EAST LQ','gch_east_LQ.m3u8','gch_lq.png','jra.east'),
    ('jra.west.hq','JRA WEST HQ','gch_west_master.m3u8','gch_hq.png','jra.west'),
    ('jra.west.lq','JRA WEST LQ','gch_west_LQ.m3u8','gch_lq.png','jra.west'),
    ('jra.local.hq','JRA LOCAL WEB5 HQ','gch_hokkaido_master.m3u8','gch_hq.png','jra.hokkaido'),
    ('jra.local.lq','JRA LOCAL WEB5 LQ','gch_hokkaido_LQ.m3u8','gch_lq.png','jra.hokkaido'),
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
        print('JRA inactive: ajiousama HQ/LQ block removed')
        return
    rows=[]
    for cid,name,stream,logo,source in CHANNELS:
        # Every quality pair follows today_jra_status exactly.
        # In particular, GCH is active only when the actual Green Channel guide
        # contains an overseas-racing or local-racing broadcast trigger.
        if source not in active:
            continue
        rows += [f'#EXTINF:-1 tvg-id="{cid}" tvg-name="{name}" tvg-logo="{LOGO}/{logo}" group-title="今日の開催場",{name}', f'{RAW}/{stream}', '']
    block=START+'\n## JRA / GCH HQ・LQ（ajiousama正本）\n'+'\n'.join(rows).rstrip()+'\n'+END+'\n'
    anchor='# === TODAY_JRA_END ==='
    text=text.replace(anchor,block+anchor,1) if anchor in text else text.rstrip()+'\n\n'+block
    FREEWIFI.write_text(text.rstrip()+'\n',encoding='utf-8')
    print('ajiousama JRA quality channels installed:', len(rows)//3)

if __name__=='__main__': main()
