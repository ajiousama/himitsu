from pathlib import Path
from datetime import datetime, timezone, timedelta
import json, re
import xml.etree.ElementTree as ET

FREEWIFI=Path('freewifi'); VERIFIED=Path('verified_daily_status.json'); STATUS=Path('today_jra_status.json'); LOCAL_EPG=Path('public_sports_epg_local.xml')
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


GRADE_RE = re.compile(r'(?i)(?:Jpn\s*(?:I{1,3}|[123])|G\s*(?:I{1,3}|[123])|Jpn[ⅠⅡⅢ]|G[ⅠⅡⅢ])')

def local_graded_races_today(now):
 graded=[]
 if not LOCAL_EPG.exists(): return graded
 try:
  root=ET.parse(LOCAL_EPG).getroot()
 except Exception:
  return graded
 date_prefix=now.strftime('%Y%m%d')
 for p in root.findall('programme'):
  if not str(p.get('channel') or '').startswith('chihou.'): continue
  start=str(p.get('start') or '')
  if not start.startswith(date_prefix): continue
  title=' '.join((p.findtext('title') or '', p.findtext('desc') or ''))
  m=GRADE_RE.search(title)
  if m:
   graded.append({'channel':p.get('channel'),'grade':m.group(0),'title':(p.findtext('title') or '').strip()})
 return graded

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
 now=datetime.now(JST); reported=[]; local_graded=local_graded_races_today(now)
 try:
  cfg=json.loads(VERIFIED.read_text(encoding='utf-8-sig'))
  if cfg.get('date')==now.date().isoformat(): reported=[x for x in cfg.get('jra_active_ids',[]) if x in SOURCES]
 except Exception: pass
 active=list(dict.fromkeys(['jra.gch',*reported])) if (reported or local_graded) else []
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
 STATUS.write_text(json.dumps({'generated_at':now.isoformat(),'active_count':len(active),'active_ids':active,'active_labels':[SOURCES[x][0] for x in active],'exposed_quality_ids':exposed,'local_graded_races':local_graded,'gch_reason':'local graded race' if local_graded and not reported else ('JRA active' if reported else None),'channels':{x:{'active':x in active,'source':'earphone HQ/LQ canonical'} for x in SOURCES}},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print('JRA earphone HQ/LQ active:',exposed)
if __name__=='__main__': main()
