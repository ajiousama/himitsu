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

# 1局が詰まっても全体を長時間止めない。
CMD_TIMEOUT=12
SEARCH_TIMEOUT=10
MAX_WORKERS=4


def run(cmd, timeout):
    safe=list(cmd)
    if safe and safe[0]=='yt-dlp':
        safe[1:1]=['--socket-timeout','6','--retries','0','--fragment-retries','0']
    return subprocess.run(safe,capture_output=True,text=True,timeout=timeout)


def base_cmd():
    cmd=['yt-dlp','--js-runtimes','node','--no-warnings']
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
    try:
        p=run(base_cmd()+['--extractor-args','youtube:player_client=default,web_safari','--no-playlist','--match-filter','is_live','-f','best[protocol^=m3u8]/best','-g',page],CMD_TIMEOUT)
    except subprocess.TimeoutExpired:
        return None,('TIMEOUT','direct URL timeout')
    urls=[x.strip() for x in p.stdout.splitlines() if x.strip().startswith(('http://','https://'))]
    if p.returncode==0 and len(urls)==1:
        return urls[0],None
    return None,(classify_error(p.stderr),short_error(p.stderr))


def search_live(query):
    try:
        p=run(base_cmd()+['--flat-playlist','--dump-json','--playlist-end','1',f'ytsearch1:{query}'],SEARCH_TIMEOUT)
    except subprocess.TimeoutExpired:
        return None,('TIMEOUT','search timeout')
    if p.returncode!=0:
        return None,('SEARCH_ERROR',short_error(p.stderr))
    page=None
    for line in p.stdout.splitlines():
        try: item=json.loads(line)
        except Exception: continue
        vid=item.get('id')
        if vid:
            page='https://www.youtube.com/watch?v='+vid
            break
    if not page:
        return None,('SEARCH_EMPTY','検索結果なし')
    return direct_url(page)


def existing_logos():
    logos={}
    for path in (FREEWIFI,OUT):
        if not path.exists(): continue
        text=path.read_text(encoding='utf-8-sig',errors='replace')
        for line in text.splitlines():
            if not line.startswith('#EXTINF:'): continue
            mid=re.search(r'tvg-id="([^"]+)"',line)
            ml=re.search(r'tvg-logo="([^"]+)"',line)
            if mid and ml and ml.group(1).strip():
                logos.setdefault(mid.group(1).strip(),ml.group(1).strip())
    return logos


def resolve_item(index,item):
    name=item['name']; url=None; reason=None
    print(f'CHECK {index+1}: {name}',flush=True)
    page=item.get('page')
    try:
        if page:
            url,reason=direct_url(page)
        if not url:
            url,reason=search_live(item.get('query') or name)
    except Exception as e:
        reason=('EXCEPTION',str(e)[:300])
    print(('OK   ' if url else 'FAIL ')+name,flush=True)
    return index,item,url,reason


def build():
    items=json.loads(SRC.read_text(encoding='utf-8'))
    active=[(i,x) for i,x in enumerate(items) if x.get('id') not in SKIP_IDS]
    old_logos=existing_logos(); results=[]

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures=[ex.submit(resolve_item,i,item) for i,item in active]
        for f in as_completed(futures):
            results.append(f.result())
    results.sort(key=lambda x:x[0])

    out=['#EXTM3U','']; got=[]; failed=[]; seen=set()
    for _,item,url,reason in results:
        name=item['name']
        if not url:
            code,detail=reason or ('NO_LIVE','LIVE URL取得なし')
            failed.append((name,code,detail)); continue
        key=url.split('?')[0]
        if key in seen:
            failed.append((name,'DUPLICATE','同一LIVE URLのため重複除外')); continue
        seen.add(key)
        tvg=item['id']; group=item.get('group','一般YouTube LIVE')
        logo=(item.get('logo') or old_logos.get(tvg) or '').strip()
        attrs=f'tvg-id="{tvg}" tvg-name="{name}"'
        if logo: attrs+=f' tvg-logo="{logo}"'
        attrs+=f' group-title="{group}"'
        out += [f'#EXTINF:-1 {attrs},{name}',url,'']
        got.append((name,group))
    text='\n'.join(out).rstrip()+'\n'
    OUT.write_text(text,encoding='utf-8')
    return text,got,failed


def merge_freewifi(general):
    base=FREEWIFI.read_text(encoding='utf-8-sig',errors='replace') if FREEWIFI.exists() else '#EXTM3U\n'
    pattern=re.compile(re.escape(START)+r'.*?'+re.escape(END),re.S)
    body='\n'.join(general.splitlines()[1:]).strip()
    block=START+'\n'+body+'\n'+END if body else START+'\n'+END
    merged=pattern.sub(block,base) if pattern.search(base) else base.rstrip()+'\n\n'+block+'\n'
    FREEWIFI.write_text(merged,encoding='utf-8')


def main():
    text,got,failed=build(); merge_freewifi(text)
    print('=== General YouTube LIVE diagnostic ===')
    print('SUCCESS:',len(got))
    for n,g in got: print(f' + OK [{g}] {n}')
    print('SKIP/FAIL:',len(failed))
    for n,code,detail in failed:
        print(f' - {code}: {n}')
        if detail: print('   ',detail)
    groups={}
    for _,g in got: groups[g]=groups.get(g,0)+1
    print('=== GROUP COUNTS ===')
    for g in ['愛媛県内ライブカメラ','交通','動物','その他LIVE','かなチューブ']:
        print(f'{g}: {groups.get(g,0)}')
    serious=[x for x in failed if x[1] in ('RATE_LIMIT','BOT_CHECK','COOKIE_ERROR')]
    if serious:
        print('=== WARNING: YouTube access restriction suspected ===')
        for n,code,detail in serious:
            print(f' ! {code}: {n} :: {detail}')

if __name__=='__main__': main()
