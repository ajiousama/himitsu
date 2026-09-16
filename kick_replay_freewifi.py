#!/usr/bin/env python3
from __future__ import annotations
import json, re, urllib.parse
from pathlib import Path
FREEWIFI=Path('freewifi'); KICK_M3U=Path('kick_replay.m3u'); GMCX_M3U=Path('kick_gmcx_chapters.m3u'); GMCX_JSON=Path('kick_gmcx_chapters.json')
KICK_END='# === KICK_MANAGED_END ==='; START='# === KICK_REPLAY_START ==='; END='# === KICK_REPLAY_END ==='

def entries(path):
    if not path.exists(): return []
    lines=path.read_text(encoding='utf-8-sig',errors='replace').splitlines(); out=[]; i=0
    while i<len(lines):
        line=lines[i].strip()
        if line.startswith('#EXTINF:'):
            j=i+1
            while j<len(lines) and (not lines[j].strip() or lines[j].lstrip().startswith('#')): j+=1
            if j<len(lines) and lines[j].strip().startswith(('http://','https://')): out.append((line,lines[j].strip())); i=j
        i+=1
    return out

def as_vod(extinf):
    if 'group-title=' in extinf: return re.sub(r'group-title="[^"]*"','group-title="VOD"',extinf)
    return extinf.replace('#EXTINF:-1','#EXTINF:-1 group-title="VOD"',1)
def tvg_id(x):
    m=re.search(r'\btvg-id="([^"]+)"',x); return m.group(1) if m else ''
def vod_id(url):
    try: return (urllib.parse.parse_qs(urllib.parse.urlparse(url).query).get('vod') or [''])[0]
    except Exception: return ''
def render_url(url):
    vid=vod_id(url)
    if not vid: return url
    q=urllib.parse.parse_qs(urllib.parse.urlparse(url).query); out='https://kick-resolver.onrender.com/kick?vod='+urllib.parse.quote(vid)
    if q.get('start'): out+='&start='+urllib.parse.quote(q['start'][0])
    return out
def remove_old(text): return re.sub(r'\n?'+re.escape(START)+r'.*?'+re.escape(END)+r'\n?','\n',text,flags=re.S)

def main():
    if not FREEWIFI.exists() or not KICK_M3U.exists(): raise RuntimeError('FreeWiFi/KICK VOD input missing')
    generic=[]; gccx=[]; chapters=entries(GMCX_M3U); ai=set()
    if GMCX_JSON.exists():
        data=json.loads(GMCX_JSON.read_text(encoding='utf-8-sig'))
        ai={str(x['vod_id']) for x in data.get('results',[]) if isinstance(x,dict) and x.get('status')=='ai_required' and x.get('vod_id')}
    for ext,url in entries(KICK_M3U):
        if tvg_id(ext).startswith('kick.gccx'):
            if vod_id(url) in ai: gccx.append((ext,url))
        else: generic.append((ext,url))
    body=[START,'## VOD']
    for ext,url in generic: body += [as_vod(ext),render_url(url)]
    for ext,url in chapters: body += [as_vod(ext),render_url(url)]
    for ext,url in gccx:
        if ',' in ext:
            head,name=ext.split(',',1); ext=f"{head},🎞 {name.removeprefix('📼 ').strip()} [変則VOD]"
        body += [as_vod(ext),render_url(url)]
    body.append(END); block='\n'.join(body)+'\n'
    text=remove_old(FREEWIFI.read_text(encoding='utf-8-sig',errors='replace')); pos=text.find(KICK_END)
    if pos<0: raise RuntimeError(f'{KICK_END} not found')
    pos+=len(KICK_END); FREEWIFI.write_text(text[:pos]+'\n\n'+block+text[pos:].lstrip('\n'),encoding='utf-8')
    print('FreeWiFi VOD:',len(generic),'generic,',len(chapters),'chapters,',len(gccx),'special'); return 0
if __name__=='__main__': raise SystemExit(main())
