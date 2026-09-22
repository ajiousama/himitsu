from pathlib import Path
import datetime
import re
import xml.etree.ElementTree as ET

JST = datetime.timezone(datetime.timedelta(hours=9))
LIVE_PREFIX = "🔴📺 ただいま実況放送中！！！ 📺🔴"
FINISHED_TITLE = "⛔🏁 本日の全レースは終了しました 🏁⛔"
NON_EVENT_TITLE = "🚫💤 本日は開催していません 💤🚫"
TARGET_PREFIXES = ("keirin.", "chihou.", "keiba.", "auto.", "boat.")
TARGET_JRA = {"jra.east", "jra.west", "jra.hokkaido"}
SPECIAL_KEIRIN = {"keirin.kawasaki":"かわさき","keirin.nagoya":"なごや","keirin.kochi":"こうち"}
SPECIAL_KEIRIN_FULL = {"keirin.pist6":"千葉PIST6（休止中）","keirin.takamatsu":"高松けいりん（休止中）","keirin.mukomachi":"向日町けいりん（休止中）"}
SPECIAL_BOAT = {"boat.karatsu":"BOATRACEからつ"}
R_CIRCLED={1:"❶",2:"❷",3:"❸",4:"❹",5:"❺",6:"❻",7:"❼",8:"❽",9:"❾",10:"❿",11:"⓫",12:"⓬"}; CIRCLED_R={v:str(k) for k,v in R_CIRCLED.items()}

def parse_xmltv(v):
    m=re.match(r"(\d{14})\s*([+-]\d{4})?",str(v or '').strip())
    if not m:return None
    d,o=m.groups()
    if o:return datetime.datetime.strptime(f'{d} {o}','%Y%m%d%H%M%S %z').astimezone(JST)
    return datetime.datetime.strptime(d,'%Y%m%d%H%M%S').replace(tzinfo=JST)
def fmt_xmltv(dt):return dt.astimezone(JST).strftime('%Y%m%d%H%M%S +0900')
def is_target(cid):return cid.startswith(TARGET_PREFIXES) or cid in TARGET_JRA

def clean_base_name(name):
    s=str(name or '').strip();s=re.sub(r'^\d{1,2}\s+','',s);s=s.replace('Ⓚ','')
    for x in ('けいりん','けいば','オート'):
        if s.endswith(x):s=s[:-len(x)]
    if s.startswith('BOATRACE'):s=s[8:]
    return s.strip()
def standardized_name(cid,current):
    if cid in SPECIAL_KEIRIN_FULL:return SPECIAL_KEIRIN_FULL[cid]
    if cid in SPECIAL_BOAT:return SPECIAL_BOAT[cid]
    b=clean_base_name(current)
    if cid.startswith('keirin.'):return f'{SPECIAL_KEIRIN.get(cid,b)}けいりん'
    if cid.startswith(('chihou.','keiba.')):return f'{b}けいば'
    if cid.startswith('auto.'):return f'{b}オート'
    if cid.startswith('boat.'):return f'BOATRACE{b}'
    return current

def extract_race_parts(title):
    t=str(title or '').strip();m=re.search(r'(?P<venue>[^\s【】]+)\s+(?P<race>\d{1,2})R\s+(?P<time>\d{1,2}:\d{2})発走\s*(?P<rest>.*)$',t)
    if m:race_no=m.group('race');race_time=m.group('time');rest=m.group('rest').strip()
    else:
        sy=''.join(re.escape(x) for x in CIRCLED_R);m=re.search(rf'(?P<race>[{sy}])ℛ\s+(?P<time>\d{{1,2}}:\d{{2}})発走\s*(?P<rest>.*)$',t)
        if not m:return None
        race_no=CIRCLED_R.get(m.group('race'));race_time=m.group('time');rest=m.group('rest').strip()
    rest=rest.replace(LIVE_PREFIX,'').strip();br=re.findall(r'【([^】]+)】',rest);plain=re.sub(r'\s*【[^】]+】\s*',' ',rest);plain=re.sub(r'\s+',' ',plain).strip();detail=br[-1].strip() if br else plain
    return race_no,race_time,detail or 'レース'
def race_no_deco(n):
    try:i=int(str(n).strip());return f'【{i}Ｒ】'
    except:return f'【{n}Ｒ】'
def competition_icon(cid,d):
    if re.search(r'[LＬ]級|ガールズ',d):return '💛'
    if cid.startswith('boat.'):return '🚤'
    if cid.startswith('auto.'):return '🏍️'
    if cid.startswith(('chihou.','keiba.')) or cid in TARGET_JRA:return '🏇'
    return '🚲' if cid.startswith('keirin.') else ''
def decorate_detail(d,cid):
    d=re.sub(r'\s+',' ',str(d or 'レース')).strip();icon=competition_icon(cid,d)
    if re.search(r'優勝|決勝|ファイナル',d):return f'🏆【{d}】🏆'
    if '準決' in d:return f'🔥【{d}】🔥'
    return f'{icon}【{d} {icon}】' if icon else f'【{d}】'
def build_live_title(n,t,d,cid):return '  '.join([race_no_deco(n),f'{t}発走',decorate_detail(d,cid),LIVE_PREFIX])
def resolve_post_time(p,t):
    s=parse_xmltv(p.get('start'))
    if not s:return None
    try:
        raw_h,m=map(int,t.split(':'))
    except (TypeError,ValueError):
        return None
    if raw_h < 0 or not 0 <= m < 60:
        return None
    day_offset,h=divmod(raw_h,24)
    base=s.date()
    cs=[datetime.datetime.combine(base+datetime.timedelta(days=x+day_offset),datetime.time(h,m),tzinfo=JST) for x in (-1,0,1)]
    return min(cs,key=lambda x:abs((x-s).total_seconds()))

def event_intro(cid,name,programmes):
    text=' '.join((p.findtext('title') or '')+' '+(p.findtext('desc') or '') for p in programmes)
    if cid.startswith('keirin.'):
        if 'ミッドナイト' in text:return '本日、ミッドナイト開催予定'
        if 'モーニング' in text:return '本日、モーニング開催予定'
        if 'ナイター' in text:return '本日、ナイター開催予定'
        return '本日、デイ開催予定'
    if cid.startswith('boat.'):
        if 'ナイター' in text:return '本日、ナイター開催予定'
        if 'モーニング' in text:return '本日、モーニング開催予定'
        return '本日、デイ開催予定'
    if cid.startswith('auto.'):
        if 'オーバーミッドナイト' in text:return '本日、オーバーミッドナイト開催予定'
        if 'ミッドナイト' in text:return '本日、ミッドナイト開催予定'
        if 'ナイター' in text:return '本日、ナイター開催予定'
        if 'モーニング' in text:return '本日、モーニング開催予定'
        return '本日、デイ開催予定'
    if cid.startswith(('chihou.','keiba.')):
        if 'ナイター' in text:return '本日、ナイター開催予定'
        if '薄暮' in text:return '本日、薄暮開催予定'
        if 'モーニング' in text:return '本日、モーニング開催予定'
        return '本日、デイ開催予定'
    if cid in TARGET_JRA:return '本日、デイ開催予定'
    return f'本日、{name}開催予定'

def normalize_today(root):
    today=datetime.datetime.now(JST).date();ds=datetime.datetime.combine(today,datetime.time(0,0),tzinfo=JST);de=ds+datetime.timedelta(days=1)
    names={ch.get('id'):ch.findtext('display-name') or ch.get('id') for ch in root.findall('channel') if is_target(ch.get('id',''))}
    rebuilt=0
    for cid,name in names.items():
        candidates=[]
        for p in list(root.findall('programme')):
            if p.get('channel')!=cid:continue
            s=parse_xmltv(p.get('start'));e=parse_xmltv(p.get('stop'));title=(p.findtext('title') or '').strip()
            if not s or not e or not title or e<=ds or s>=de:continue
            candidates.append((max(s,ds),min(e,de),p))
        candidates.sort(key=lambda x:(x[0],x[1]))
        intro=event_intro(cid,name,[p for _,_,p in candidates])
        for p in list(root.findall('programme')):
            if p.get('channel')!=cid:continue
            s=parse_xmltv(p.get('start'));e=parse_xmltv(p.get('stop'))
            if s and e and e>ds and s<de:root.remove(p)
        cur=ds
        for s,e,p in candidates:
            if e<=cur:continue
            if s>cur:
                gap=ET.SubElement(root,'programme',start=fmt_xmltv(cur),stop=fmt_xmltv(s),channel=cid);ET.SubElement(gap,'title',lang='ja').text=intro;ET.SubElement(gap,'desc',lang='ja').text=f'{name}の本日の開催案内です。'
            ns=max(s,cur)
            if ns<e:
                p.set('start',fmt_xmltv(ns));p.set('stop',fmt_xmltv(e));root.append(p);cur=e
        if cur<de:
            gap=ET.SubElement(root,'programme',start=fmt_xmltv(cur),stop=fmt_xmltv(de),channel=cid);ET.SubElement(gap,'title',lang='ja').text=intro;ET.SubElement(gap,'desc',lang='ja').text=f'{name}の本日の開催案内です。'
        rebuilt+=1
    return rebuilt

def main():
    path=Path('epg.xml');tree=ET.parse(path);root=tree.getroot()
    for ch in root.findall('channel'):
        cid=ch.get('id','')
        if not is_target(cid):continue
        dn=ch.find('display-name');cur=dn.text if dn is not None and dn.text else '';name=standardized_name(cid,cur)
        if dn is None:dn=ET.SubElement(ch,'display-name')
        dn.text=name
    by={};formatted=0
    for p in root.findall('programme'):
        cid=p.get('channel','')
        if not is_target(cid):continue
        te=p.find('title')
        if te is None:continue
        title=te.text or ''
        if '本日は開催していません' in title:te.text=NON_EVENT_TITLE;continue
        if '本日の開催は終了しました' in title or '本日の全レースは終了しました' in title:te.text=FINISHED_TITLE;continue
        parts=extract_race_parts(title)
        if not parts:continue
        n,t,d=parts;post=resolve_post_time(p,t)
        if not post:continue
        te.text=build_live_title(n,t,d,cid);by.setdefault(cid,[]).append((post,p));formatted+=1
    adjusted=0
    for cid,items in by.items():
        items.sort(key=lambda x:x[0]);prev=None
        for post,p in items:
            cut=post+datetime.timedelta(minutes=3)
            if prev is None:
                ns=post-datetime.timedelta(minutes=15)
            else:
                ns=prev
            if ns<cut:p.set('start',fmt_xmltv(ns));p.set('stop',fmt_xmltv(cut));adjusted+=1
            prev=cut
    rebuilt=normalize_today(root)
    ps=list(root.findall('programme'))
    for p in ps:root.remove(p)
    ps.sort(key=lambda p:(parse_xmltv(p.get('start')) or datetime.datetime.max.replace(tzinfo=JST),p.get('channel','')))
    for p in ps:root.append(p)
    ET.indent(tree,space='    ');tree.write(path,encoding='utf-8',xml_declaration=True)
    print(f'EPG v11 finalized: titles={formatted} timing={adjusted} timelines={rebuilt}')
if __name__=='__main__':main()
