from pathlib import Path
from datetime import datetime, timezone, timedelta
from html import unescape
import json
import re
import urllib.request
import xml.etree.ElementTree as ET

FREEWIFI = Path('freewifi')
STATUS_JSON = Path('today_public_sports_status.json')
PUBLIC_M3U_URL = 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/public_sports.m3u'
PUBLIC_EPG_URL = 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/epg.xml'
START = '# === TODAY_PUBLIC_SPORTS_START ==='
END = '# === TODAY_PUBLIC_SPORTS_END ==='
GROUP = '今日の開催場'
JST = timezone(timedelta(hours=9))
TARGET_SECTIONS = {'競輪', '地方競馬', 'ボートレース', 'オートレース'}
DISPLAY_NAMES = {'地方競馬':'地方競馬','競輪':'競輪','ボートレース':'ボート','オートレース':'オート'}
NON_EVENT_WORDS = ('本日非開催','非開催','開催していません','開催予定はありません','本日開催なし','開催なし','次回開催','データ取得準備中','休止中','休止','準備中','現在準備中')
OFFICIAL_URLS = {
    '競輪': 'https://www.keirin.jp/sp/raceschedule',
    '地方競馬': 'https://sp.keiba.go.jp/KeibaWebSP/TodayRaceInfo/S_TodayRaceInfoTop',
    'ボートレース': 'https://www.boatrace.jp/owsp/sp/race/pay',
    'オートレース': 'https://autorace.jp/race_info/',
}


def fetch_text(url, timeout=30):
    req = urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0 (FreeWiFi venue checker)'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode('utf-8-sig', errors='replace')


def html_text(s):
    s = re.sub(r'(?is)<script.*?</script>|<style.*?</style>', ' ', s)
    s = re.sub(r'(?s)<[^>]+>', ' ', s)
    return re.sub(r'\s+', ' ', unescape(s)).strip()


def parse_m3u(text):
    entries, section = {}, ''
    lines = text.splitlines(); i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.startswith('## '):
            section = line[3:].strip(); i += 1; continue
        if line.startswith('#EXTINF:'):
            block=[lines[i]]; j=i+1
            while j < len(lines) and not lines[j].startswith('#EXTINF:') and not lines[j].startswith('## '):
                if lines[j].strip(): block.append(lines[j])
                j += 1
            m=re.search(r'tvg-id="([^"]+)"', line)
            if m and section in TARGET_SECTIONS: entries[m.group(1)] = (section, block)
            i=j; continue
        i += 1
    return entries


def parse_xmltv_time(s):
    if not s: return None
    m=re.match(r'^(\d{14})\s*([+-]\d{4})?', s.strip())
    if not m: return None
    base=datetime.strptime(m.group(1),'%Y%m%d%H%M%S')
    off=m.group(2)
    if off:
        sign=1 if off[0]=='+' else -1
        tz=timezone(sign*timedelta(hours=int(off[1:3]),minutes=int(off[3:5])))
        return base.replace(tzinfo=tz)
    return base.replace(tzinfo=JST)


def epg_state(text):
    root=ET.fromstring(text); today=datetime.now(JST).date()
    real=set(); last_stop={}; modes={}
    for p in root.findall('programme'):
        cid=p.get('channel') or ''; start=parse_xmltv_time(p.get('start')); stop=parse_xmltv_time(p.get('stop'))
        if not start or start.astimezone(JST).date()!=today: continue
        title=''.join((p.findtext('title') or '').split())
        if not title or any(w in title for w in NON_EVENT_WORDS): continue
        real.add(cid)
        if stop:
            ls=stop.astimezone(JST)
            if cid not in last_stop or ls>last_stop[cid]: last_stop[cid]=ls
        joined=title+' '+(p.findtext('desc') or '')
        modes[cid]='overnight' if 'オーバーミッドナイト' in joined else ('midnight' if 'ミッドナイト' in joined else ('night' if 'ナイター' in joined else modes.get(cid,'day')))
    return real,last_stop,modes


def entry_name(block):
    m=re.search(r'tvg-name="([^"]+)"', block[0])
    return m.group(1) if m else block[0].rsplit(',',1)[-1].strip()


def aliases(section,name):
    n=re.sub(r'[（(].*?[）)]','',name).strip(); vals={n}
    if section=='競輪': vals |= {n.replace('けいりん',''),n.replace('競輪',''),n.replace('温泉','')}
    elif section=='地方競馬':
        vals |= {n.replace('けいば',''),n.replace('競馬場',''),n.replace('競馬','')}
        if '帯広' in n: vals.add('帯広ば')
    elif section=='ボートレース': vals |= {n.replace('BOATRACE',''),n.replace('ボートレース','')}
    elif section=='オートレース': vals |= {n.replace('オートレース',''),n.replace('オート','')}
    return sorted({v.strip() for v in vals if len(v.strip())>=2},key=len,reverse=True)


def in_mmdd_range(today,a_m,a_d,b_m,b_d):
    y=today.year; a=datetime(y,int(a_m),int(a_d)).date(); b=datetime(y,int(b_m),int(b_d)).date()
    if b<a:
        b=datetime(y+1,int(b_m),int(b_d)).date()
        if today<a: today=datetime(y+1,today.month,today.day).date()
    return a<=today<=b


def official_keirin(text,name,today):
    for a in aliases('競輪',name):
        pos=text.find(a)
        while pos>=0:
            chunk=text[pos:pos+1400]
            for m in re.finditer(r'(\d{1,2})/(\d{1,2})\s*[～〜~-]\s*(\d{1,2})/(\d{1,2})',chunk):
                if in_mmdd_range(today,*m.groups()):
                    mode='overnight' if 'オーバーミッドナイト' in chunk else ('midnight' if 'ミッドナイト' in chunk else ('night' if 'ナイター' in chunk else ('morning' if 'モーニング' in chunk else 'day')))
                    return True,mode
            pos=text.find(a,pos+len(a))
    return False,None


def dated_window(text,today):
    pats=[f'{today.year}年{today.month}月{today.day}日',f'{today.year}/{today.month:02d}/{today.day:02d}',f'{today.month}/{today.day}']
    starts=[text.find(p) for p in pats if text.find(p)>=0]
    if not starts: return text
    s=min(starts); nxt=today+timedelta(days=1)
    ends=[text.find(f'{nxt.year}年{nxt.month}月{nxt.day}日',s+10),text.find(f'{nxt.year}/{nxt.month:02d}/{nxt.day:02d}',s+10)]
    ends=[x for x in ends if x>=0]
    return text[s:min(ends) if ends else min(len(text),s+8000)]


def official_simple(section,text,name,today):
    window=dated_window(text,today)
    ok=any(a in window for a in aliases(section,name))
    if not ok: return False,None
    mode='overnight' if 'オーバーミッドナイト' in window else ('midnight' if 'ミッドナイト' in window else ('night' if ('ナイター' in window or '☆' in window) else 'day'))
    return True,mode


def official_boat(text,name,today):
    plain=html_text(text)
    return (any(a in plain for a in aliases('ボートレース',name)), None)


def rewrite_group(extinf):
    if 'group-title=' in extinf: return re.sub(r'group-title="[^"]*"',f'group-title="{GROUP}"',extinf,count=1)
    comma=extinf.find(','); return extinf[:comma]+f' group-title="{GROUP}"'+extinf[comma:] if comma>=0 else extinf+f' group-title="{GROUP}"'


def prune_abema_rakuten(text):
    lines=text.splitlines(); out=[]; i=0
    while i<len(lines):
        line=lines[i]
        if not line.startswith('#EXTINF:'): out.append(line); i+=1; continue
        block=[line]; j=i+1
        while j<len(lines) and not lines[j].startswith('#EXTINF:') and not lines[j].startswith('## '): block.append(lines[j]); j+=1
        low=line.lower(); drop=False
        if 'abema' in low or 'アベマ' in line: drop=not ('アニメ' in line or 'anime' in low)
        elif 'rakuten' in low or '楽天' in line:
            keep_rail=any(k in line for k in ('鉄道','電車','列車')) or 'rail' in low or 'train' in low
            keep_adult=any(k in line for k in ('アダルト','成人','R18','R-18','18禁')) or 'adult' in low
            drop=not (keep_rail or keep_adult)
        if not drop: out.extend(block)
        i=j
    return '\n'.join(out).rstrip()+'\n'


def replace_block(text,block):
    text=re.sub(re.escape(START)+r'.*?'+re.escape(END)+r'\n?','',text,flags=re.S)
    anchor='# === GENERAL_YOUTUBE_MANAGED_START ==='
    return text.replace(anchor,block+'\n\n'+anchor,1) if anchor in text else text.rstrip()+'\n\n'+block+'\n'


def main():
    now=datetime.now(JST); today=now.date()
    base=prune_abema_rakuten(FREEWIFI.read_text(encoding='utf-8-sig',errors='replace'))
    entries=parse_m3u(fetch_text(PUBLIC_M3U_URL))
    epg_real,last_stop,epg_modes=epg_state(fetch_text(PUBLIC_EPG_URL))
    official={}
    for section,url in OFFICIAL_URLS.items():
        try:
            raw=fetch_text(url); official[section]=raw if section=='ボートレース' else html_text(raw)
            print(f'Official schedule OK: {section}')
        except Exception as e:
            official[section]=''; print(f'Official schedule NG: {section}: {e}')

    selected=[]; counts={k:0 for k in TARGET_SECTIONS}; status={}
    for tvg,(section,block) in entries.items():
        name=entry_name(block); active=False; mode=epg_modes.get(tvg,'day'); source=''
        page=official.get(section,'')
        if section=='ボートレース':
            if page:
                active,found_mode=official_boat(page,name,today); source='BOATRACE official today page'
            else:
                active=tvg in epg_real; found_mode=None; source='earphone1981 EPG fallback'
            if found_mode: mode=found_mode
            stop=last_stop.get(tvg)
            if active and stop and now>=stop+timedelta(minutes=30): active=False
        elif page:
            if section=='競輪': active,found_mode=official_keirin(page,name,today)
            else: active,found_mode=official_simple(section,page,name,today)
            if found_mode: mode=found_mode
            source='official schedule'
            # The official pages occasionally change markup and can fail to identify
            # individual venues. If the upstream EPG has real programmes for today,
            # keep the venue active rather than dropping it from FreeWiFi.
            if not active and tvg in epg_real:
                active=True
                source='earphone1981 EPG fallback after official miss'
            if active and tvg in last_stop and now>=last_stop[tvg]: active=False
        else:
            # Official schedule fetch failed completely: use real upstream EPG as the
            # authoritative fallback for keirin/autorace/local racing.
            active=tvg in epg_real
            found_mode=None
            source='earphone1981 EPG fallback'
        if not active: continue
        b=block[:]; b[0]=rewrite_group(b[0]); selected.extend(b); selected.append('')
        counts[section]+=1
        status[tvg]={'section':section,'name':name,'mode':mode,'source':source,'epg_available':tvg in epg_real}

    body='\n'.join(selected).rstrip(); managed=START+'\n## 今日の開催場\n'+body+('\n' if body else '')+END
    FREEWIFI.write_text(replace_block(base,managed).rstrip()+'\n',encoding='utf-8')
    STATUS_JSON.write_text(json.dumps({'generated_at':now.isoformat(),'channels':status},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print('Today public sports synced:',sum(counts.values()))
    for section in ('地方競馬','競輪','ボートレース','オートレース'): print(f'{DISPLAY_NAMES[section]}: {counts.get(section,0)}')

if __name__=='__main__': main()
