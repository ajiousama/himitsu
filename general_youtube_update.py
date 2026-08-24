from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import json, re, subprocess

SRC=Path('general_youtube_sources.json')
OUT=Path('general_youtube.m3u')
FREEWIFI=Path('freewifi')
COOKIES=Path('youtube_cookies.txt')
START='# === GENERAL_YOUTUBE_MANAGED_START ==='
END='# === GENERAL_YOUTUBE_MANAGED_END ==='
SKIP_IDS={'youtube.kobe_waterfront2','youtube.narita_t1'}
CMD_TIMEOUT=22
SEARCH_TIMEOUT=18
MAX_WORKERS=6


def run(cmd, timeout):
    safe=list(cmd)
    if safe and safe[0]=='yt-dlp':
        safe[1:1]=['--socket-timeout','10','--retries','1','--fragment-retries','1']
    return subprocess.run(safe,capture_output=True,text=True,timeout=timeout)


def base_cmd():
    cmd=['yt-dlp','--js-runtimes','node','--no-warnings','--no-cache-dir']
    if COOKIES.exists() and COOKIES.stat().st_size>20:
        cmd += ['--cookies',str(COOKIES)]
    return cmd


def classify_error(stderr):
    s=(stderr or '').lower()
    if '429' in s or 'too many requests' in s: return 'RATE_LIMIT'
    if 'sign in to confirm you' in s or 'not a bot' in s or ('bot' in s and 'confirm' in s): return 'BOT_CHECK'
    if 'cookies' in s and ('expired' in s or 'invalid' in s or 'login' in s): return 'COOKIE_ERROR'
    if 'this live event will begin' in s or 'premieres in' in s: return 'NOT_STARTED'
    if 'is not currently live' in s or 'not live' in s or 'this video is unavailable' in s: return 'NOT_LIVE'
    if 'private video' in s: return 'PRIVATE'
    if 'video unavailable' in s or 'unavailable' in s: return 'UNAVAILABLE'
    if 'unsupported url' in s: return 'UNSUPPORTED'
    return 'OTHER'


def short_error(stderr):
    lines=[x.strip() for x in (stderr or '').splitlines() if x.strip()]
    return ' | '.join(lines[-3:])[:500]


def direct_url(page):
    last_reason=None
    for sel in ['best[protocol^=m3u8]','best']:
        try:
            p=run(base_cmd()+['--extractor-args','youtube:player_client=default,web_safari,web','--no-playlist','--match-filter','is_live','-f',sel,'-g',page],CMD_TIMEOUT)
        except subprocess.TimeoutExpired:
            last_reason=('TIMEOUT','direct URL timeout'); continue
        urls=[x.strip() for x in p.stdout.splitlines() if x.strip().startswith(('http://','https://'))]
        if p.returncode==0 and len(urls)==1: return urls[0],None
        last_reason=(classify_error(p.stderr),short_error(p.stderr))
    return None,last_reason or ('OTHER','direct URL取得失敗')


def channel_live(page, scan=30):
    if not page or '/@' not in page: return None,('CHANNEL_SKIP','channel URLではない')
    base=page.rstrip('/')
    if base.endswith('/live'): base=base[:-5]
    reasons=[]
    # /live 自体の解決に失敗しても、streams/videos の新着を広めに検査する。
    for listing in [base+'/streams',base+'/videos']:
        try:
            p=run(base_cmd()+['--flat-playlist','--dump-json','--playlist-end',str(scan),listing],SEARCH_TIMEOUT)
        except subprocess.TimeoutExpired:
            reasons.append(('TIMEOUT','channel listing timeout')); continue
        if p.returncode!=0:
            reasons.append((classify_error(p.stderr),short_error(p.stderr))); continue
        live_first=[]; others=[]
        for line in p.stdout.splitlines():
            try: item=json.loads(line)
            except Exception: continue
            vid=item.get('id')
            if not vid: continue
            status=(item.get('live_status') or '').lower()
            (live_first if status=='is_live' else others).append(vid)
        # live_status が欠落するケースもあるので新着候補も直接 is_live 判定する。
        for vid in live_first+others[:15]:
            url,reason=direct_url('https://www.youtube.com/watch?v='+vid)
            if url: return url,None
            if reason: reasons.append(reason)
    return (None,reasons[-1]) if reasons else (None,('CHANNEL_EMPTY','チャンネル配信一覧から候補なし'))


def search_live(query, count=10):
    try:
        p=run(base_cmd()+['--flat-playlist','--dump-json','--playlist-end',str(count),f'ytsearch{count}:{query}'],SEARCH_TIMEOUT)
    except subprocess.TimeoutExpired: return None,('TIMEOUT','search timeout')
    if p.returncode!=0: return None,('SEARCH_ERROR',short_error(p.stderr))
    reasons=[]
    for line in p.stdout.splitlines():
        try: item=json.loads(line)
        except Exception: continue
        vid=item.get('id')
        if not vid: continue
        url,reason=direct_url('https://www.youtube.com/watch?v='+vid)
        if url: return url,None
        if reason: reasons.append(reason)
    if not reasons: return None,('SEARCH_EMPTY','検索結果なし')
    for code in ['RATE_LIMIT','BOT_CHECK','COOKIE_ERROR','TIMEOUT','NOT_STARTED','NOT_LIVE','PRIVATE','UNAVAILABLE','UNSUPPORTED','OTHER']:
        for r in reasons:
            if r[0]==code: return None,r
    return None,reasons[0]


def existing_logos():
    logos={}
    for path in (FREEWIFI,OUT):
        if not path.exists(): continue
        text=path.read_text(encoding='utf-8-sig',errors='replace')
        for line in text.splitlines():
            if not line.startswith('#EXTINF:'): continue
            mid=re.search(r'tvg-id="([^"]+)"',line); ml=re.search(r'tvg-logo="([^"]+)"',line)
            if mid and ml and ml.group(1).strip(): logos.setdefault(mid.group(1).strip(),ml.group(1).strip())
    return logos


def resolve_item(index,item):
    name=item['name']; url=None; reason=None; page=item.get('page')
    print(f'CHECK {index+1}: {name}',flush=True)
    try:
        if page: url,reason=direct_url(page)
        if not url and item.get('id')=='youtube.kana_tube':
            # 華奈tube専用: /live -> streams/videos -> 複数検索語 の順で粘る。
            url,reason=channel_live(page,30)
            if not url:
                for q in [item.get('query'),'華奈tube LIVE','かなチューブ 競輪 LIVE','華奈tube 競輪']:
                    if not q: continue
                    url,reason=search_live(q,15)
                    if url: break
        elif not url:
            url,reason=search_live(item.get('query') or name,10)
    except Exception as e: reason=('EXCEPTION',str(e)[:300])
    print(('OK   ' if url else 'FAIL ')+name+(f' [{reason[0]}]' if reason and not url else ''),flush=True)
    return index,item,url,reason


def build():
    items=json.loads(SRC.read_text(encoding='utf-8')); active=[(i,x) for i,x in enumerate(items) if x.get('id') not in SKIP_IDS]
    old_logos=existing_logos(); results=[]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for f in as_completed([ex.submit(resolve_item,i,item) for i,item in active]): results.append(f.result())
    results.sort(key=lambda x:x[0]); out=['#EXTM3U','']; got=[]; failed=[]; seen=set()
    for _,item,url,reason in results:
        name=item['name']
        if not url:
            code,detail=reason or ('NO_LIVE','LIVE URL取得なし'); failed.append((name,code,detail)); continue
        key=url.split('?')[0]
        if key in seen: failed.append((name,'DUPLICATE','同一LIVE URLのため重複除外')); continue
        seen.add(key); tvg=item['id']; group=item.get('group','一般YouTube LIVE'); logo=(item.get('logo') or old_logos.get(tvg) or '').strip()
        attrs=f'tvg-id="{tvg}" tvg-name="{name}"'
        if logo: attrs+=f' tvg-logo="{logo}"'
        attrs+=f' group-title="{group}"'; out += [f'#EXTINF:-1 {attrs},{name}',url,'']; got.append((name,group))
    text='\n'.join(out).rstrip()+'\n'; OUT.write_text(text,encoding='utf-8'); return text,got,failed


def merge_freewifi(general):
    base=FREEWIFI.read_text(encoding='utf-8-sig',errors='replace') if FREEWIFI.exists() else '#EXTM3U\n'
    pattern=re.compile(re.escape(START)+r'.*?'+re.escape(END),re.S); body='\n'.join(general.splitlines()[1:]).strip(); block=START+'\n'+body+'\n'+END if body else START+'\n'+END
    FREEWIFI.write_text(pattern.sub(block,base) if pattern.search(base) else base.rstrip()+'\n\n'+block+'\n',encoding='utf-8')


def main():
    text,got,failed=build(); merge_freewifi(text)
    print('=== General YouTube LIVE diagnostic ==='); print('SUCCESS:',len(got))
    for n,g in got: print(f' + OK [{g}] {n}')
    print('SKIP/FAIL:',len(failed))
    for n,code,detail in failed:
        print(f' - {code}: {n}')
        if detail: print('   ',detail)
    groups={}
    for _,g in got: groups[g]=groups.get(g,0)+1
    print('=== GROUP COUNTS ===')
    for g in ['愛媛県内ライブカメラ','交通','動物','その他LIVE','かなチューブ']: print(f'{g}: {groups.get(g,0)}')
    serious=[x for x in failed if x[1] in ('RATE_LIMIT','BOT_CHECK','COOKIE_ERROR')]
    if serious:
        print('=== WARNING: YouTube access restriction suspected ===')
        for n,code,detail in serious: print(f' ! {code}: {n} :: {detail}')

if __name__=='__main__': main()
