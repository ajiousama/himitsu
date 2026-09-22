from pathlib import Path
import datetime
import re
import xml.etree.ElementTree as ET

EPG=Path('epg.xml')
M3U=Path('public_sports.m3u')
JST=datetime.timezone(datetime.timedelta(hours=9))
TODAY=datetime.datetime.now(JST).date()
SORT_GROUPS={'競輪','地方競馬','オートレース','ボートレース'}
RACE_TIME_RE=re.compile(r'([0-2]?\d:[0-5]\d)\s*発走')
TVG_ID_RE=re.compile(r'tvg-id="([^"]+)"',re.I)

BOAT_LOGO_SLUG={
    'boat.kiryu':'kiryu','boat.toda':'toda','boat.edogawa':'edogawa','boat.heiwajima':'heiwajima',
    'boat.tamagawa':'tamagawa','boat.hamanako':'hamanako','boat.gamagori':'gamagori','boat.tokoname':'tokoname',
    'boat.tsu':'tsu','boat.mikuni':'mikuni','boat.biwako':'biwako','boat.suminoe':'suminoe',
    'boat.amagasaki':'amagasaki','boat.naruto':'naruto','boat.marugame':'marugame','boat.kojima':'kojima',
    'boat.miyajima':'miyajima','boat.tokuyama':'tokuyama','boat.shimonoseki':'shimonoseki','boat.wakamatsu':'wakamatsu',
    'boat.ashiya':'ashiya','boat.fukuoka':'fukuoka','boat.karatsu':'karatsu','boat.omura':'omura',
}
BOAT_LOGO_BASE='https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/public_sports_logos_github_43/boatrace_24_spaced_cut_1024'


def current_order():
    h=datetime.datetime.now(JST).hour
    if h < 11:
        seq=['モーニング','デイ','通常','薄暮','サマータイム','ナイター','ミッドナイト','オーバーミッドナイト']; band='朝'
    elif h < 17:
        seq=['デイ','通常','薄暮','サマータイム','ナイター','ミッドナイト','オーバーミッドナイト','モーニング']; band='昼'
    else:
        seq=['薄暮','サマータイム','ナイター','ミッドナイト','オーバーミッドナイト','デイ','通常','モーニング']; band='夕'
    return {x:i for i,x in enumerate(seq)},band

def parse_dt(value):
    m=re.match(r'(\d{14})\s*([+-]\d{4})?',str(value or ''))
    if not m:return None
    digits,off=m.groups()
    if off:return datetime.datetime.strptime(f'{digits} {off}','%Y%m%d%H%M%S %z').astimezone(JST)
    return datetime.datetime.strptime(digits,'%Y%m%d%H%M%S').replace(tzinfo=JST)

def classify(desc,first,last):
    for key in ('オーバーミッドナイト','ミッドナイト','ナイター','サマータイム','薄暮','モーニング','デイ','通常'):
        if key in desc:return key
    if last is not None and last+30 > 23*60+40:return 'オーバーミッドナイト'
    if first is None:return '非開催'
    if first < 10*60:return 'モーニング'
    if first >= 19*60:return 'ミッドナイト'
    if first >= 14*60:return 'ナイター'
    return 'デイ'

def load_epg_names():
    root=ET.parse(EPG).getroot(); names={}
    for ch in root.findall('channel'):
        cid=(ch.get('id') or '').strip(); name=(ch.findtext('display-name') or '').strip()
        if cid and name:names[cid]=name
    return names

def build_epg_keys():
    root=ET.parse(EPG).getroot(); by={}
    for p in root.findall('programme'):
        cid=p.get('channel',''); start=parse_dt(p.get('start'))
        if not cid or start is None:continue
        logical=start.date() if start.hour>=4 else start.date()-datetime.timedelta(days=1)
        if logical!=TODAY:continue
        title=p.findtext('title') or ''; desc=p.findtext('desc') or ''
        if '本日は開催していません' in title or 'データ取得準備中' in title:
            by.setdefault(cid,{'times':[],'desc':''}); continue
        m=RACE_TIME_RE.search(title) or re.search(r'発走予定[:：]?\s*([0-2]?\d:[0-5]\d)',desc)
        if not m:continue
        hh,mm=map(int,m.group(1).split(':')); mins=hh*60+mm
        info=by.setdefault(cid,{'times':[],'desc':''}); info['times'].append(mins); info['desc']+=' '+desc+' '+title
    priority,band=current_order(); keys={}
    for cid,info in by.items():
        times=sorted(info['times'])
        if not times:keys[cid]=(99,9999,cid);continue
        typ=classify(info['desc'],times[0],times[-1]); keys[cid]=(priority.get(typ,50),times[0],cid)
    return keys,band

def split_sections(text):
    lines=text.replace('\r\n','\n').split('\n'); header=[]; sections=[]; name=None; cur=[]
    for line in lines:
        if line.startswith('## '):
            if name is None:header.extend(cur)
            else:sections.append((name,cur))
            name=line[3:].strip(); cur=[line]
        else:cur.append(line)
    if name is None:header.extend(cur)
    else:sections.append((name,cur))
    return header,sections

def parse_blocks(lines):
    prefix=[lines[0]] if lines else []; blocks=[]; i=1
    while i<len(lines):
        if not lines[i].startswith('#EXTINF:'):i+=1;continue
        b=[lines[i]];i+=1
        while i<len(lines) and not lines[i].startswith('#EXTINF:'):b.append(lines[i]);i+=1
        while b and b[-1]=='':b.pop()
        blocks.append(b)
    return prefix,blocks

def block_id(block):
    m=TVG_ID_RE.search(block[0]) if block else None
    return m.group(1).strip() if m else ''

def sync_tvg_name(block,epg_names):
    if not block:return block
    cid=block_id(block); name=epg_names.get(cid)
    if not name:return block
    ext=block[0]
    if re.search(r'tvg-name="[^"]*"',ext,re.I):
        ext=re.sub(r'tvg-name="[^"]*"',f'tvg-name="{name}"',ext,flags=re.I)
    else:
        ext=ext.replace(' group-title=',f' tvg-name="{name}" group-title=',1)
    # IPTV clients commonly display the M3U name after the final comma rather
    # than tvg-name, so keep both labels identical.
    if ',' in ext:
        ext=ext.rsplit(',',1)[0]+','+name
    block[0]=ext; return block

def repair_boat_logo(block):
    if not block:return block
    cid=block_id(block); slug=BOAT_LOGO_SLUG.get(cid)
    if not slug:return block
    logo=f'{BOAT_LOGO_BASE}/{slug}.png'; ext=block[0]
    if re.search(r'tvg-logo="[^"]*"',ext,re.I):ext=re.sub(r'tvg-logo="[^"]*"',f'tvg-logo="{logo}"',ext,flags=re.I)
    else:ext=ext.replace(' group-title=',f' tvg-logo="{logo}" group-title=',1)
    block[0]=ext; return block

def main():
    keys,band=build_epg_keys(); epg_names=load_epg_names(); text=M3U.read_text(encoding='utf-8-sig'); header,sections=split_sections(text); out=[]
    if header:
        out.extend(header)
        while out and out[-1]=='':out.pop()
        out.append('')
    synced=0
    for name,lines in sections:
        prefix,blocks=parse_blocks(lines)
        if not blocks:
            out.extend(lines)
            if out and out[-1]!='':out.append('')
            continue
        decorated=[]
        for idx,b in enumerate(blocks):
            cid=block_id(b)
            before=b[0] if b else ''
            b=sync_tvg_name(b,epg_names)
            if b and b[0]!=before:synced+=1
            if name=='ボートレース':b=repair_boat_logo(b)
            key=keys.get(cid,(99,9999,cid or f'zz{idx:04d}')) if name in SORT_GROUPS else (idx,)
            decorated.append((key,idx,b))
        if name in SORT_GROUPS:decorated.sort(key=lambda x:(x[0],x[1]))
        out.extend(prefix)
        for _,_,b in decorated:out.extend(b);out.append('')
        if name in SORT_GROUPS:print(f'{name}: {len(blocks)} ch sorted')
    M3U.write_text('\n'.join(out).rstrip()+'\n',encoding='utf-8')
    print(f'public_sports.m3u sorted for {band} priority / tvg-name synced={synced} / BOAT logos repaired')

if __name__=='__main__':main()
