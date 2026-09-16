#!/usr/bin/env python3
import json, os, re, sys, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo
from xml.sax.saxutils import unescape

ROOT = Path(__file__).resolve().parent
CFG = ROOT / 'haru_vod_favorites.json'
OUT = ROOT / 'haru_vod.m3u'
FREEWIFI = ROOT / 'freewifi'
EPG_URL = os.environ.get('HARU_EPG_URL', 'https://akariko-bck1.sankuria.sbs/epg/kai-epg.xml')
PROBE = os.environ.get('HARU_PROBE', '1') != '0'
RAW = 'https://raw.githubusercontent.com/ajiousama/himitsu/main/'
JST = ZoneInfo('Asia/Tokyo')
START = '# === HARU_VOD_START ==='
END = '# === HARU_VOD_END ==='

PAIR_RE = re.compile(r'<!--\s*(https://haru\.charandom\.blog/stream/jp/[^\s]+?/replay\.m3u8\?mode=hls&amp;start=\d+|https://haru\.charandom\.blog/stream/jp/[^\s]+?/replay\.m3u8\?mode=hls&start=\d+)\s*-->\s*<programme\b([^>]*)>(.*?)</programme>', re.S|re.I)
TITLE_RE = re.compile(r'<title(?:\s[^>]*)?>(.*?)</title>', re.S|re.I)
ATTR_RE = re.compile(r'(\w+)="([^"]*)"')
TAG_RE = re.compile(r'<[^>]+>')

def fetch_text(url):
    req=urllib.request.Request(url, headers={'User-Agent':'Mozilla/5.0 HARU-VOD/1.0'})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode('utf-8','replace')

def clean(s): return unescape(TAG_RE.sub('', s)).strip()
def title_matches(title, rule): return any(x in title for x in rule.get('include',[])) and not any(x in title for x in rule.get('exclude',[]))

def probe(url):
    if not PROBE: return True
    try:
        req=urllib.request.Request(url, headers={'User-Agent':'VLC/3.0 HARU-VOD/1.0','Range':'bytes=0-2047'})
        with urllib.request.urlopen(req, timeout=8) as r:
            data=r.read(2048)
            return r.status in (200,206) and b'#EXTM3U' in data
    except Exception: return False

def parse_epg(text, rules):
    now=int(datetime.now(timezone.utc).timestamp()); found=[]
    for m in PAIR_RE.finditer(text):
        url=unescape(m.group(1)); attrs=dict(ATTR_RE.findall(m.group(2))); tm=TITLE_RE.search(m.group(3))
        if not tm: continue
        title=clean(tm.group(1)); sm=re.search(r'[?&]start=(\d+)',url)
        if not sm: continue
        start=int(sm.group(1))
        if start > now + 300: continue
        for rule in rules:
            if title_matches(title,rule):
                found.append({'rule':rule,'title':title,'url':url,'start':start,'channel':attrs.get('channel','')}); break
    seen=set(); out=[]
    for x in sorted(found,key=lambda z:z['start'],reverse=True):
        k=(x['rule']['id'],x['url'])
        if k not in seen: seen.add(k); out.append(x)
    return out

def kick_has_gccx():
    if not FREEWIFI.exists(): return False
    s=FREEWIFI.read_text(encoding='utf-8-sig',errors='replace')
    return '# === KICK_REPLAY_START ===' in s and ('ゲームセンターＣＸ' in s or 'ゲームセンターCX' in s)

def build_m3u(items, group):
    lines=['#EXTM3U']; kick_gccx=kick_has_gccx()
    for x in items:
        r=x['rule']
        if r.get('prefer_kick') and kick_gccx: continue
        dt=datetime.fromtimestamp(x['start'], timezone.utc).astimezone(JST).strftime('%m/%d %H:%M')
        logo=RAW+r['logo']; name=f"{r['name']} {dt}｜{x['title']}"
        lines += [f'#EXTINF:-1 tvg-logo="{logo}" group-title="{group}",{name}', x['url']]
    return '\n'.join(lines)+'\n'

def merge_freewifi(vod):
    if not FREEWIFI.exists(): return
    s=FREEWIFI.read_text(encoding='utf-8-sig',errors='replace'); body='\n'.join(vod.splitlines()[1:]).strip(); block=f'{START}\n{body}\n{END}'
    if START in s and END in s: s=re.sub(re.escape(START)+r'.*?'+re.escape(END), block, s, flags=re.S)
    else: s=s.rstrip()+'\n\n'+block+'\n'
    FREEWIFI.write_text(s,encoding='utf-8')

def main():
    cfg=json.loads(CFG.read_text(encoding='utf-8')); epg=fetch_text(EPG_URL); candidates=parse_epg(epg,cfg['programmes'])
    if not candidates: raise SystemExit('HARU VOD: no favourite programmes found; refusing to overwrite shelf')
    checked=[x for x in candidates if probe(x['url'])]
    if PROBE and not checked:
        print('HARU VOD: all probes failed; using EPG candidates rather than publishing an empty shelf',file=sys.stderr); checked=candidates
    vod=build_m3u(checked,cfg.get('group_title','HARU VOD')); OUT.write_text(vod,encoding='utf-8'); merge_freewifi(vod)
    counts={r['name']:0 for r in cfg['programmes']}
    for x in checked: counts[x['rule']['name']]+=1
    print('HARU VOD:',len(checked),'entries',counts)

if __name__=='__main__': main()
