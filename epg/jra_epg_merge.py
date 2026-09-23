from pathlib import Path
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
 races=combined(regional)
 # GCH MAIN is also exposed for local graded races and overseas race broadcasts.
 # When JRA regional race EPG is empty, build GCH EPG from the matching
 # local-horse-racing programmes so final audit never sees an orphan channel.
 local_graded=[]; overseas=[]
 grade_re=re.compile(r'(?i)(?:Jpn\\s*(?:I{1,3}|[123])|G\\s*(?:I{1,3}|[123])|Jpn[ⅠⅡⅢ]|G[ⅠⅡⅢ])')
 overseas_re=re.compile(r'(?:海外競馬|海外馬券|凱旋門賞|ブリーダーズ.?カップ|ドバイ(?:ワールドカップ|シーマクラシック|ターフ)|香港国際競走|香港カップ|香港マイル|香港スプリント|香港ヴァーズ|サウジカップ|ロイヤルアスコット|メルボルンカップ)',re.I)
 # NAR repair and the normal TV EPG have already populated guides.xml here.
 for p in root.findall('programme'):
  cid=p.get('channel') or ''
  text=' '.join(((p.findtext('title') or ''),(p.findtext('desc') or '')))
  if cid.startswith('chihou.') and grade_re.search(text):
   local_graded.append(copy.deepcopy(p))
  if overseas_re.search(text):
   overseas.append(copy.deepcopy(p))
 gch_programmes=[]
 seen=set()
 for p in [*races,*local_graded,*overseas]:
  key=(p.get('start'),p.get('stop'),(p.findtext('title') or '').strip())
  if key in seen: continue
  seen.add(key); gch_programmes.append(p)
 if gch_programmes:
  for quality,label in (('hq','HQ'),('lq','LQ')):
   cid=f'jra.gch.{quality}'; add_channel(root,cid,f'グリーンチャンネル MAIN {label}')
   for p in gch_programmes: root.append(clone(p,cid))
 ET.indent(tree,space='  '); tree.write(GUIDES,encoding='utf-8',xml_declaration=True)
 print('JRA earphone HQ/LQ race EPG:',{k:len(v) for k,v in regional.items()},'GCH races=',len(races),'GCH local graded=',len(local_graded),'GCH overseas=',len(overseas))
if __name__=='__main__': main()
