from pathlib import Path
from datetime import datetime, timezone, timedelta
import copy
import re
import xml.etree.ElementTree as ET

GUIDES=Path('guides.xml')
LOCAL=Path('public_sports_epg_local.xml')
JST=timezone(timedelta(hours=9))
REGIONAL=('jra.east','jra.west','jra.hokkaido')
NAMES={'jra.gch':'グリーンチャンネル','jra.east':'JRA EAST','jra.west':'JRA WEST','jra.hokkaido':'JRA HOKKAIDO','jra.official':'GCH無料版A（YouTube）','jra.gch.free':'GCH無料版B（グリーンチャンネルWeb）'}
NORMAL_GCH='グリーンチャンネル_jp'
TARGET=set(NAMES)

def date_key(p):
    m=re.match(r'^(\d{8})',p.get('start') or ''); return m.group(1) if m else ''

def add_channel(root,cid,name):
    c=ET.Element('channel',{'id':cid}); ET.SubElement(c,'display-name').text=name; root.append(c)

def is_race(p):
    t=(p.findtext('title') or '')
    return bool(re.search(r'(?:【\s*)?[０-９0-9]{1,2}\s*[ＲR]|発走',t)) and '終了しました' not in t

def remove_targets(root):
    for el in list(root):
        cid=el.get('id') if el.tag=='channel' else el.get('channel') if el.tag=='programme' else ''
        if cid in TARGET: root.remove(el)

def clone(p,cid=None):
    q=copy.deepcopy(p)
    if cid: q.set('channel',cid)
    return q

def main():
    if not GUIDES.exists() or not LOCAL.exists(): raise SystemExit('guides/local JRA EPG missing')
    src=ET.parse(LOCAL).getroot(); tree=ET.parse(GUIDES); root=tree.getroot()
    normal=[copy.deepcopy(p) for p in root.findall('programme') if p.get('channel')==NORMAL_GCH]
    remove_targets(root)
    regional={cid:[p for p in src.findall('programme') if p.get('channel')==cid] for cid in REGIONAL}
    any_regional=any(regional.values())
    if normal or any_regional:
        add_channel(root,'jra.gch',NAMES['jra.gch'])
        for p in normal: root.append(clone(p,'jra.gch'))
    for cid in REGIONAL:
        if not regional[cid]: continue
        add_channel(root,cid,NAMES[cid])
        for p in regional[cid]: root.append(clone(p))
    by_start={}
    for cid in REGIONAL:
        for p in regional[cid]:
            if is_race(p): by_start.setdefault(p.get('start'),[]).append(p)
    if by_start:
        add_channel(root,'jra.official',NAMES['jra.official'])
        starts=sorted(by_start)
        for i,s in enumerate(starts):
            items=by_start[s]; stop=starts[i+1] if i+1<len(starts) else max((p.get('stop') or s) for p in items)
            q=ET.Element('programme',{'channel':'jra.official','start':s,'stop':stop})
            titles=[]; desc=[]
            for p in items:
                t=(p.findtext('title') or '').strip(); d=(p.findtext('desc') or '').strip()
                if t and t not in titles: titles.append(t)
                if d and d not in desc: desc.append(d)
            ET.SubElement(q,'title',{'lang':'ja'}).text=' / '.join(titles)
            if desc: ET.SubElement(q,'desc',{'lang':'ja'}).text='\n'.join(desc)
            root.append(q)
        dates=sorted({date_key(p) for cid in REGIONAL for p in regional[cid] if date_key(p)})
        if dates:
            add_channel(root,'jra.gch.free',NAMES['jra.gch.free'])
            for d in dates:
                day=datetime.strptime(d,'%Y%m%d').replace(tzinfo=JST); nxt=day+timedelta(days=1)
                q=ET.Element('programme',{'channel':'jra.gch.free','start':day.strftime('%Y%m%d%H%M%S +0900'),'stop':nxt.strftime('%Y%m%d%H%M%S +0900')})
                ET.SubElement(q,'title',{'lang':'ja'}).text='競馬全レース中継　GCH（無料版）'; root.append(q)
    ET.indent(tree,space='  '); tree.write(GUIDES,encoding='utf-8',xml_declaration=True)
    print('JRA LOCAL EPG merged:', {cid:len(regional[cid]) for cid in REGIONAL}, 'GCH=',len(normal),'A=',len(by_start))
if __name__=='__main__': main()
