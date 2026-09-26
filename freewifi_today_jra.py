from pathlib import Path
from datetime import datetime, timezone, timedelta
import json, re, urllib.request
import xml.etree.ElementTree as ET

FREEWIFI=Path('freewifi'); VERIFIED=Path('verified_daily_status.json'); STATUS=Path('today_jra_status.json'); LOCAL_EPG=Path('public_sports_epg_local.xml'); GUIDES=Path('guides.xml')
JST=timezone(timedelta(hours=9)); START='# === TODAY_JRA_START ==='; END='# === TODAY_JRA_END ==='; GROUP='今日の開催場'
RAW='https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main'
LOGO=RAW+'/public_sports_logos_github_43/jra_quality'
SOURCES={
 'jra.gch':('グリーンチャンネル MAIN','gchmain.m3u8','gchmain_LQ.m3u8','gch_hq.png','gch_lq.png'),
 'jra.east':('JRA EAST WEB3','EAST_test.m3u8','EAST_test_LQ.m3u8','east_hq.png','east_lq.png'),
 'jra.west':('JRA WEST WEB4','WEST_master%20.m3u8','WEST_master_LQ.m3u8','west_hq.png','west_lq.png'),
 'jra.hokkaido':('JRA LOCAL WEB5','hokaido_master%20(1).m3u8','hokaido_master_LQ.m3u8','local_hq.png','local_lq.png'),
}
QUALITY_IDS={f'{base}.{q}' if base!='jra.hokkaido' else f'jra.local.{q}' for base in SOURCES for q in ('hq','lq')}
LEGACY_FREE_IDS={'jra.official','jra.gch.free'}
JRA_RACE_IDS={'jra.east','jra.west','jra.hokkaido'}
GCH_STATUS_URL='https://ajiousama-radiko.onrender.com/gch-status'


GCH_TRIGGER_RE = re.compile(r'(?:海外競馬中継|地方競馬中継)', re.I)

def gch_special_broadcasts_today(now):
 events=[]
 if not GUIDES.exists(): return events
 try:
  root=ET.parse(GUIDES).getroot()
 except Exception:
  return events

 # Find the actual Green Channel EPG channel IDs from channel/display-name,
 # instead of assuming one hard-coded XMLTV id.
 gch_ids=set()
 for ch in root.findall('channel'):
  cid=str(ch.get('id') or '')
  names=' '.join((x.text or '') for x in ch.findall('display-name'))
  # Generated HQ/LQ mirrors must never become the trigger source themselves.
  if cid.startswith('jra.gch.'):
   continue
  if 'グリーンチャンネル' in names or 'グリーンチャンネル' in cid:
   gch_ids.add(cid)

 date_prefix=now.strftime('%Y%m%d')
 for p in root.findall('programme'):
  if str(p.get('channel') or '') not in gch_ids: continue
  start=str(p.get('start') or '')
  if not start.startswith(date_prefix): continue
  title=(p.findtext('title') or '').strip()
  desc=(p.findtext('desc') or '').strip()
  if GCH_TRIGGER_RE.search(' '.join((title,desc))):
   events.append({'channel':p.get('channel'),'title':title,'start':start})
 return events


def gch_render_status(now):
 try:
  req=urllib.request.Request(GCH_STATUS_URL+'?refresh=1',headers={'User-Agent':'FreeWiFi-GCH-Client/1.0','Accept':'application/json'})
  with urllib.request.urlopen(req,timeout=45) as r:
   data=json.loads(r.read().decode('utf-8','replace'))
  if data.get('date') != now.date().isoformat(): return {'ok':False,'reason':'date_mismatch','data':data}
  return {'ok':True,'data':data}
 except Exception as e:
  return {'ok':False,'reason':f'{type(e).__name__}: {e}'}

def strip(text):
 text=re.sub(re.escape(START)+r'.*?'+re.escape(END)+r'\n?','',text,flags=re.S)
 lines=text.splitlines(); out=[]; i=0
 while i<len(lines):
  line=lines[i]; m=re.search(r'tvg-id="([^"]+)"',line) if line.startswith('#EXTINF:') else None
  if m and (m.group(1) in SOURCES or m.group(1) in QUALITY_IDS or m.group(1) in LEGACY_FREE_IDS):
   i+=1
   while i<len(lines) and not lines[i].startswith(('#EXTINF:','## ','# ===')): i+=1
   continue
  out.append(line); i+=1
 return '\n'.join(out).rstrip()+'\n'

def main():
 now=datetime.now(JST); reported=[]; gch_special=gch_special_broadcasts_today(now)
 try:
  cfg=json.loads(VERIFIED.read_text(encoding='utf-8-sig'))
  if cfg.get('date')==now.date().isoformat(): reported=[x for x in cfg.get('jra_active_ids',[]) if x in SOURCES]
 except Exception: pass
 active=[x for x in dict.fromkeys(reported) if x != 'jra.gch']
 jra_race_day=any(x in JRA_RACE_IDS for x in active)
 render_status={'ok':False,'reason':'not_needed_on_jra_race_day'}
 render_special=False
 if not jra_race_day:
  render_status=gch_render_status(now)
  if render_status.get('ok'):
   rd=render_status.get('data') or {}
   render_special=bool(rd.get('local_race_broadcast') or rd.get('overseas_race_broadcast'))
 show_gch=jra_race_day or render_special or bool(gch_special)
 if show_gch: active.insert(0,'jra.gch')
 base=strip(FREEWIFI.read_text(encoding='utf-8-sig',errors='replace')); rows=[]; exposed=[]
 for source in active:
  name,hq,lq,hqlogo,lqlogo=SOURCES[source]
  outbase='jra.local' if source=='jra.hokkaido' else source
  for q,stream,logo in (('hq',hq,hqlogo),('lq',lq,lqlogo)):
   cid=f'{outbase}.{q}'; label=f'{name} {q.upper()}'
   rows += [f'#EXTINF:-1 tvg-id="{cid}" tvg-name="{label}" tvg-logo="{LOGO}/{logo}" group-title="{GROUP}",{label}',f'{RAW}/{stream}','']
   exposed.append(cid)
 managed=START+'\n## 本日の開催場（JRA / earphone HQ・LQ）\n'+'\n'.join(rows).rstrip()+('\n' if rows else '')+END
 anchor='# === GENERAL_YOUTUBE_MANAGED_START ==='
 text=base.replace(anchor,managed+'\n\n'+anchor,1) if anchor in base else base.rstrip()+'\n\n'+managed+'\n'
 FREEWIFI.write_text(text.rstrip()+'\n',encoding='utf-8')
 STATUS.write_text(json.dumps({'generated_at':now.isoformat(),'active_count':len(active),'active_ids':active,'active_labels':[SOURCES[x][0] for x in active],'exposed_quality_ids':exposed,'gch_special_broadcasts':gch_special,'gch_render_status':render_status,'jra_race_day':jra_race_day,'gch_reason':('JRA race day' if jra_race_day else 'Render GCH official schedule: overseas/local race broadcast' if render_special else 'GCH programme guide: overseas/local race broadcast' if gch_special else None),'channels':{x:{'active':x in active,'source':'earphone HQ/LQ canonical'} for x in SOURCES}},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('JRA earphone HQ/LQ active:',exposed)
if __name__=='__main__': main()
