from pathlib import Path
from datetime import datetime, timezone, timedelta
import json
import re
import urllib.request

JST = timezone(timedelta(hours=9))
FREEWIFI = Path('freewifi')
VERIFY = Path('verified_daily_status.json')
PUBLIC_STATUS = Path('today_public_sports_status.json')
JRA_STATUS = Path('today_jra_status.json')
PUBLIC_M3U_URL = 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/public_sports.m3u'
GENERAL_YOUTUBE = Path('public_sports_youtube_fallback.m3u')
FALLBACK_ENTRIES = {
    ('ボートレース', '桐生'): {
        'source_id': 'youtube.boat_kiryu', 'tvg_id': 'boat.kiryu', 'name': 'BOATRACE桐生',
        'logo': 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/public_sports_logos_github_43/boatrace_24_spaced_cut_1024/kiryu.png',
    },
    ('ボートレース', '住之江'): {
        'source_id': 'youtube.boat_suminoe', 'tvg_id': 'boat.suminoe', 'name': 'BOATRACE住之江',
        'logo': 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/public_sports_logos_github_43/boatrace_24_spaced_cut_1024/suminoe.png',
    },
}
CANONICAL_ALIASES = {'こうち': '高知', 'からつ': '唐津'}
PSTART = '# === TODAY_PUBLIC_SPORTS_START ==='
PEND = '# === TODAY_PUBLIC_SPORTS_END ==='
JSTART = '# === TODAY_JRA_START ==='
JEND = '# === TODAY_JRA_END ==='
GROUP = '今日の開催場'

def fetch_text(url):
    req=urllib.request.Request(url,headers={'User-Agent':'FreeWiFi-Verified-Daily/1.0','Cache-Control':'no-cache'})
    with urllib.request.urlopen(req,timeout=45) as r:return r.read().decode('utf-8-sig',errors='replace')

def norm(s):
    s=re.sub(r'[（(].*?[）)]','',s or '')
    for w in ('けいりん','競輪場','競輪','けいば','競馬場','競馬','ボートレース','BOATRACE','ボート','オートレース','オート','温泉'):
        s=s.replace(w,'')
    value=re.sub(r'[^0-9A-Za-z一-龥ぁ-んァ-ン]+','',s).lower()
    return CANONICAL_ALIASES.get(value,value)

def parse_entries(text):
    out=[];section='';lines=text.splitlines();i=0
    while i<len(lines):
        line=lines[i]
        if line.startswith('## '):section=line[3:].strip();i+=1;continue
        if not line.startswith('#EXTINF:'):i+=1;continue
        block=[line];j=i+1
        while j<len(lines) and not lines[j].startswith('#EXTINF:') and not lines[j].startswith('## '):
            if lines[j].strip():block.append(lines[j])
            j+=1
        mid=re.search(r'tvg-id="([^"]+)"',line)
        # Venue display name after the final comma is canonical for matching.
        # tvg-name may intentionally be hiragana/branding (e.g. こうちけいりん).
        display=line.rsplit(',',1)[-1].strip() if ',' in line else ''
        mn=re.search(r'tvg-name="([^"]+)"',line)
        name=display or (mn.group(1) if mn else '')
        if mid:out.append((mid.group(1),section,name,block))
        i=j
    return out

def fallback_source_entries():
    if not GENERAL_YOUTUBE.exists():
        return {}
    parsed=parse_entries(GENERAL_YOUTUBE.read_text(encoding='utf-8-sig',errors='replace'))
    return {cid:block for cid,_section,_name,block in parsed}

def materialize_fallback(section,venue,sources):
    spec=FALLBACK_ENTRIES.get((section,venue))
    if not spec:
        return None
    block=sources.get(spec['source_id'])
    if not block:
        return None
    b=block[:];line=b[0]
    line=re.sub(r'tvg-id="[^"]+"',f'tvg-id="{spec["tvg_id"]}"',line,count=1)
    if 'tvg-name=' in line:
        line=re.sub(r'tvg-name="[^"]*"',f'tvg-name="{spec["name"]}"',line,count=1)
    else:
        line=line.replace('#EXTINF:-1',f'#EXTINF:-1 tvg-name="{spec["name"]}"',1)
    if 'tvg-logo=' in line:
        line=re.sub(r'tvg-logo="[^"]*"',f'tvg-logo="{spec["logo"]}"',line,count=1)
    else:
        line=line.replace(' group-title=',f' tvg-logo="{spec["logo"]}" group-title=',1)
    line=re.sub(r',.*$',','+spec['name'],line,count=1)
    b[0]=line
    return spec['tvg_id'],spec['name'],b

def rewrite_group(line):
    if 'group-title=' in line:return re.sub(r'group-title="[^"]*"',f'group-title="{GROUP}"',line,count=1)
    p=line.find(',');return line[:p]+f' group-title="{GROUP}"'+line[p:] if p>=0 else line

def replace_block(text,start,end,heading,blocks):
    body=[]
    for block in blocks:
        b=block[:];b[0]=rewrite_group(b[0]);body.extend(b);body.append('')
    payload='\n'.join(body).rstrip();managed=start+'\n## '+heading+'\n'+payload+('\n' if payload else '')+end
    pat=re.compile(re.escape(start)+r'.*?'+re.escape(end)+r'\n?',re.S)
    if pat.search(text):return pat.sub(managed+'\n',text,count=1)
    anchor='# === GENERAL_YOUTUBE_MANAGED_START ==='
    return text.replace(anchor,managed+'\n\n'+anchor,1) if anchor in text else text.rstrip()+'\n\n'+managed+'\n'

def strip_tvg_ids(text,ids):
    lines=text.splitlines();out=[];i=0
    while i<len(lines):
        line=lines[i]
        if line.startswith('#EXTINF:') and any(f'tvg-id="{cid}"' in line for cid in ids):
            i+=1
            while i<len(lines) and not lines[i].startswith('#EXTINF:') and not lines[i].startswith('## ') and not lines[i].startswith('# ==='):
                i+=1
            continue
        out.append(line);i+=1
    return '\n'.join(out).rstrip()+'\n'

def strip_jra_entries(text):
    text=re.sub(re.escape(JSTART)+r'.*?'+re.escape(JEND)+r'\n?','',text,flags=re.S)
    text=re.sub(r'# === JRA_GCH_FREE_START ===.*?# === JRA_GCH_FREE_END ===\n?','',text,flags=re.S)
    text=re.sub(r'# === JRA_OFFICIAL_YOUTUBE_START ===.*?# === JRA_OFFICIAL_YOUTUBE_END ===\n?','',text,flags=re.S)
    ids=('jra.east','jra.west','jra.hokkaido','jra.official','jra.gch.free');lines=text.splitlines();out=[];i=0
    while i<len(lines):
        line=lines[i]
        if line.startswith('#EXTINF:') and any(f'tvg-id="{cid}"' in line for cid in ids):
            i+=1
            while i<len(lines) and not lines[i].startswith('#EXTINF:') and not lines[i].startswith('## ') and not lines[i].startswith('# ==='):i+=1
            continue
        out.append(line);i+=1
    return '\n'.join(out).rstrip()+'\n'

def mode_for(section,name):
    n=norm(name)
    if section=='競輪':
        if n in {norm(x) for x in ('青森','宇都宮','熊本')}:return 'midnight'
        if n in {norm(x) for x in ('松戸','松阪')}:return 'night'
    if section=='ボートレース' and n in {norm(x) for x in ('桐生','丸亀','若松')}:return 'night'
    if section=='オートレース' and n==norm('飯塚'):return 'overnight'
    return 'day'

def main():
    now=datetime.now(JST)
    if not VERIFY.exists() or not FREEWIFI.exists():return
    cfg=json.loads(VERIFY.read_text(encoding='utf-8-sig'))
    if cfg.get('date')!=now.date().isoformat():print('Verified daily override expired/not for today; skipped');return
    wanted=cfg.get('public_sports') or {};entries=parse_entries(fetch_text(PUBLIC_M3U_URL));fallback_sources=fallback_source_entries();selected=[];status={};matched={k:[] for k in wanted};selected_ids=set()
    for cid,section,name,block in entries:
        if section not in wanted:continue
        n=norm(name);target=None
        # Canonical venue names must match exactly after normalization.
        # Substring matching caused 津 to incorrectly match 唐津.
        for v in wanted.get(section,[]):
            if n and n==norm(v):target=v;break
        if target is None or cid in selected_ids:continue
        selected_ids.add(cid);selected.append(block);matched[section].append(target);status[cid]={'section':section,'name':name,'mode':mode_for(section,name),'source':'verified daily override','epg_available':True,'next_race':None,'next_race_text':'本日開催'}
    for section,venues in wanted.items():
        have={norm(x) for x in matched.get(section,[])}
        for venue in venues:
            if norm(venue) in have:
                continue
            fallback=materialize_fallback(section,venue,fallback_sources)
            if not fallback:
                continue
            cid,name,block=fallback
            if cid in selected_ids:
                continue
            selected_ids.add(cid);selected.append(block);matched[section].append(venue);have.add(norm(venue))
            status[cid]={'section':section,'name':name,'mode':mode_for(section,name),'source':'official YouTube fallback','epg_available':True,'next_race':None,'next_race_text':'本日開催'}
    expected=sum(len(v) for v in wanted.values());missing=[]
    for section,vals in wanted.items():
        have={norm(x) for x in matched.get(section,[])};missing += [f'{section}:{v}' for v in vals if norm(v) not in have]
    if missing:
        print(f'WARNING: verified upstream channels missing: matched={len(selected)}/{expected}, missing={missing}')
    text=FREEWIFI.read_text(encoding='utf-8-sig',errors='replace');text=strip_tvg_ids(text,{x['source_id'] for x in FALLBACK_ENTRIES.values()});text=replace_block(text,PSTART,PEND,'今日の開催場',selected)
    jra_ids=cfg.get('jra_active_ids') or []
    if not jra_ids:text=strip_jra_entries(text);text=replace_block(text,JSTART,JEND,'JRA',[])
    FREEWIFI.write_text(text.rstrip()+'\n',encoding='utf-8')
    PUBLIC_STATUS.write_text(json.dumps({'generated_at':now.isoformat(),'verified_date':cfg['date'],'expected_count':expected,'matched_count':len(selected),'missing':missing,'channels':status},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    JRA_STATUS.write_text(json.dumps({'generated_at':now.isoformat(),'verified_date':cfg['date'],'active_count':len(jra_ids),'active_ids':jra_ids,'active_labels':[],'special_entries':0,'channels':{}},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Verified daily override applied:',len(selected),'public sports; JRA=',len(jra_ids))
    for section in ('地方競馬','競輪','ボートレース','オートレース'):print(section,len(wanted.get(section,[])))
if __name__=='__main__':main()
