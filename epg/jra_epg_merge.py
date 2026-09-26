from pathlib import Path
from datetime import datetime, timezone, timedelta
import copy, re
import xml.etree.ElementTree as ET

GUIDES=Path('guides.xml'); LOCAL=Path('public_sports_epg_local.xml')
REGIONAL=('jra.east','jra.west','jra.hokkaido')
QUALITY={'jra.east':('jra.east','JRA EAST WEB3'),'jra.west':('jra.west','JRA WEST WEB4'),'jra.hokkaido':('jra.local','JRA LOCAL WEB5')}
TARGET={'jra.gch','jra.east','jra.west','jra.hokkaido','jra.local','jra.official','jra.gch.free','jra.gch.hq','jra.gch.lq'}
for base,_ in QUALITY.values(): TARGET|={base+'.hq',base+'.lq'}

def add_channel(root,cid,name):
 c=ET.Element('channel',{'id':cid}); ET.SubElement(c,'display-name').text=name; root.append(c)

def is_race(p):
 t=(p.findtext('title') or '')
 return bool(re.search(r'(?:【\s*)?[０-９0-9]{1,2}\s*[ＲR]|発走',t)) and '終了しました' not in t

def clone(p,cid):
 q=copy.deepcopy(p); q.set('channel',cid); return q

def combined(regional):
 by={}
 for source in REGIONAL:
  for p in regional[source]:
   if is_race(p): by.setdefault(p.get('start'),[]).append(p)
 out=[]; starts=sorted(by)
 for i,s in enumerate(starts):
  items=by[s]; stop=starts[i+1] if i+1<len(starts) else max((p.get('stop') or s) for p in items)
  q=ET.Element('programme',{'start':s,'stop':stop}); titles=[]; desc=[]
  for p in items:
   t=(p.findtext('title') or '').strip(); d=(p.findtext('desc') or '').strip()
   if t and t not in titles: titles.append(t)
   if d and d not in desc: desc.append(d)
  ET.SubElement(q,'title',{'lang':'ja'}).text=' / '.join(titles)
  if desc: ET.SubElement(q,'desc',{'lang':'ja'}).text='\n'.join(desc)
  out.append(q)
 return out

def main():
 if not GUIDES.exists() or not LOCAL.exists(): raise SystemExit('guides/local JRA EPG missing')
 src=ET.parse(LOCAL).getroot(); tree=ET.parse(GUIDES); root=tree.getroot()
 regional={cid:[copy.deepcopy(p) for p in src.findall('programme') if p.get('channel')==cid] for cid in REGIONAL}
 for el in list(root):
  cid=el.get('id') if el.tag=='channel' else el.get('channel') if el.tag=='programme' else ''
  if cid in TARGET: root.remove(el)
 for source,(base,display) in QUALITY.items():
  if not regional[source]: continue
  for quality,label in (('hq','HQ'),('lq','LQ')):
   cid=f'{base}.{quality}'; add_channel(root,cid,f'{display} {label}')
   for p in regional[source]: root.append(clone(p,cid))
 # GCH MAIN is visible on every JRA race day, and also on non-JRA days when
 # the Green Channel guide carries overseas/local race coverage.
 gch_ids=set()
 for ch in root.findall('channel'):
  cid=str(ch.get('id') or '')
  names=' '.join((x.text or '') for x in ch.findall('display-name'))
  if 'グリーンチャンネル' in names or 'グリーンチャンネル' in cid:
   gch_ids.add(cid)

 JST=timezone(timedelta(hours=9))
 today=datetime.now(JST).strftime('%Y%m%d')
 trigger_re=re.compile(r'(?:海外競馬中継|地方競馬中継)',re.I)
 gch_today=[
  copy.deepcopy(p) for p in root.findall('programme')
  if str(p.get('channel') or '') in gch_ids and str(p.get('start') or '').startswith(today)
 ]
 gch_special=[
  p for p in gch_today
  if trigger_re.search(' '.join(((p.findtext('title') or ''),(p.findtext('desc') or ''))))
 ]
 jra_race_day=any(regional[source] for source in REGIONAL)
 show_gch=jra_race_day or bool(gch_special)
 if show_gch:
  for quality,label in (('hq','HQ'),('lq','LQ')):
   cid=f'jra.gch.{quality}'; add_channel(root,cid,f'グリーンチャンネル MAIN {label}')
   for p in gch_today: root.append(clone(p,cid))
 ET.indent(tree,space='  '); tree.write(GUIDES,encoding='utf-8',xml_declaration=True)
 print('JRA earphone HQ/LQ race EPG:',{k:len(v) for k,v in regional.items()},'GCH source ids=',sorted(gch_ids),'JRA race day=',jra_race_day,'GCH trigger programmes=',len(gch_special),'GCH mirrored programmes=',len(gch_today) if show_gch else 0)
if __name__=='__main__': main()
