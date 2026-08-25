from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from zoneinfo import ZoneInfo
import json, re, subprocess, threading, time

SRC=Path('general_youtube_sources.json')
OUT=Path('general_youtube.m3u')
FREEWIFI=Path('freewifi')
COOKIES=Path('youtube_cookies.txt')
START='# === GENERAL_YOUTUBE_MANAGED_START ==='
END='# === GENERAL_YOUTUBE_MANAGED_END ==='
SKIP_IDS={'youtube.kobe_waterfront2','youtube.narita_t1'}
CMD_TIMEOUT=22
SEARCH_TIMEOUT=18
MAX_WORKERS=2
MIN_CALL_INTERVAL=1.25
JST=ZoneInfo('Asia/Tokyo')
SERIOUS_CODES={'RATE_LIMIT','BOT_CHECK','COOKIE_ERROR'}
KANA_ID='youtube.kana_tube'
KANA_PAGE='https://www.youtube.com/@kana_tube/live'
_call_lock=threading.Lock()
_last_call_at=0.0


def kana_focus_time():
    now=datetime.now(JST); minute=now.hour*60+now.minute
    return (12*60+45 <= minute <= 16*60+45) or (20*60+15 <= minute <= 23*60+45)


def run(cmd, timeout):
    global _last_call_at
    safe=list(cmd)
    if safe and safe[0]=='yt-dlp':
        safe[1:1]=['--socket-timeout','10','--retries','1','--fragment-retries','1']
        with _call_lock:
            wait=MIN_CALL_INTERVAL-(time.monotonic()-_last_call_at)
            if wait>0: time.sleep(wait)
            _last_call_at=time.monotonic()
    return subprocess.run(safe,capture_output=True,text=True,timeout=timeout)


def base_cmd():
    cmd=['yt-dlp','--js-runtimes','node','--no-warnings','--no-cache-dir']
    if COOKIES.exists() and COOKIES.stat().st_size>20:
        cmd += ['--cookies',str(COOKIES)]
    return cmd


def classify_error(stderr):
    s=(stderr or '').lower()
    if ('429' in s or 'too many requests' in s or 'rate limit' in s or
        'maximum number of requests' in s or 'maximum requests' in s or
        ('try again' in s and 'hour' in s)):
        return 'RATE_LIMIT'
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
        if p.returncode==0 and len(urls)==1:
            return urls[0],None
        last_reason=(classify_error(p.stderr),short_error(p.stderr))
        if last_reason[0] in SERIOUS_CODES:
            break
    return None,last_reason or ('OTHER','direct URL取得失敗')


def channel_live(page, scan=20, live_only=False):
    if not page or '/@' not in page:
        return None,('CHANNEL_SKIP','channel URLではない')
    base=page.rstrip('/')
    if base.endswith('/live'):
        base=base[:-5]
    reasons=[]
    for listing in [base+'/streams',base+'/videos']:
        try:
            p=run(base_cmd()+['--flat-playlist','--dump-json','--playlist-end',str(scan),listing],SEARCH_TIMEOUT)
        except subprocess.TimeoutExpired:
            reasons.append(('TIMEOUT','channel listing timeout')); continue
        if p.returncode!=0:
            r=(classify_error(p.stderr),short_error(p.stderr)); reasons.append(r)
            if r[0] in SERIOUS_CODES:
                return None,r
            continue
        live=[]; others=[]
        for line in p.stdout.splitlines():
            try: item=json.loads(line)
            except Exception: continue
            vid=item.get('id')
            if not vid: continue
            status=(item.get('live_status') or '').lower()
            if status=='is_live': live.append(vid)
            elif not live_only: others.append(vid)
        for vid in live + ([] if live_only else others[:5]):
            url,reason=direct_url('https://www.youtube.com/watch?v='+vid)
            if url: return url,None
            if reason:
                reasons.append(reason)
                if reason[0] in SERIOUS_CODES:
                    return None,reason
    if live_only:
        return None,('NOT_LIVE','公式チャンネル内に現在LIVEなし')
    return (None,reasons[-1]) if reasons else (None,('CHANNEL_EMPTY','チャンネル配信一覧から候補なし'))


def search_live(query, count=6):
    try:
        p=run(base_cmd()+['--flat-playlist','--dump-json','--playlist-end',str(count),f'ytsearch{count}:{query}'],SEARCH_TIMEOUT)
    except subprocess.TimeoutExpired:
        return None,('TIMEOUT','search timeout')
    if p.returncode!=0:
        return None,(classify_error(p.stderr),short_error(p.stderr))
    reasons=[]
    for line in p.stdout.splitlines():
        try: item=json.loads(line)
        except Exception: continue
        vid=item.get('id')
        if not vid: continue
        url,reason=direct_url('https://www.youtube.com/watch?v='+vid)
        if url: return url,None
        if reason:
            reasons.append(reason)
            if reason[0] in SERIOUS_CODES:
                return None,reason
    if not reasons:
        return None,('SEARCH_EMPTY','検索結果なし')
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
            mid=re.search(r'tvg-id="([^"]+)"',line)
            ml=re.search(r'tvg-logo="([^"]+)"',line)
            if mid and ml and ml.group(1).strip():
                logos.setdefault(mid.group(1).strip(),ml.group(1).strip())
    return logos


def old_urls_by_id(text):
    result={}; lines=text.splitlines()
    for i,line in enumerate(lines):
        if not line.startswith('#EXTINF:'): continue
        m=re.search(r'tvg-id="([^"]+)"',line)
        if not m: continue
        j=i+1
        while j<len(lines) and not lines[j].strip(): j+=1
        if j<len(lines) and lines[j].strip().startswith(('http://','https://')):
            result[m.group(1)]=lines[j].strip()
    return result


def make_entry(item,url,old_logos):
    tvg=item['id']; name=item['name']; group=item.get('group','一般YouTube LIVE')
    logo=(item.get('logo') or old_logos.get(tvg) or '').strip()
    attrs=f'tvg-id="{tvg}" tvg-name="{name}"'+(f' tvg-logo="{logo}"' if logo else '')+f' group-title="{group}"'
    return [f'#EXTINF:-1 {attrs},{name}',url,'']


def apply_source_logos(text):
    wanted={}
    for item in json.loads(SRC.read_text(encoding='utf-8')):
        cid=(item.get('id') or '').strip(); logo=(item.get('logo') or '').strip()
        if cid and logo: wanted[cid]=logo
    out=[]
    for line in text.splitlines():
        if line.startswith('#EXTINF:'):
            m=re.search(r'tvg-id="([^"]+)"',line)
            logo=wanted.get(m.group(1)) if m else None
            if logo:
                if re.search(r'tvg-logo="[^"]*"',line):
                    line=re.sub(r'tvg-logo="[^"]*"',f'tvg-logo="{logo}"',line,count=1)
                else:
                    line=line.replace(' group-title=',f' tvg-logo="{logo}" group-title=',1)
        out.append(line)
    return '\n'.join(out).rstrip()+'\n'


def resolve_item(index,item):
    name=item['name']; tvg=item.get('id'); url=None; reason=None
    page=item.get('page')
    print(f'CHECK {index+1}: {name}',flush=True)
    try:
        if tvg==KANA_ID:
            # 華奈tubeは公式 @kana_tube 内の現在LIVEだけを採用。
            # 一般YouTube検索へは絶対にフォールバックしない。
            focus=kana_focus_time()
            print(f' KANA official-only focus={focus}',flush=True)
            url,reason=direct_url(KANA_PAGE)
            if not url and not (reason and reason[0] in SERIOUS_CODES):
                url,reason=channel_live(KANA_PAGE,30 if focus else 15,live_only=True)
        else:
            if page: url,reason=direct_url(page)
            if not url and not (reason and reason[0] in SERIOUS_CODES):
                url,reason=search_live(item.get('query') or name,6)
    except Exception as e:
        reason=('EXCEPTION',str(e)[:300])
    print(('OK   ' if url else 'FAIL ')+name+(f' [{reason[0]}]' if reason and not url else ''),flush=True)
    return index,item,url,reason


def build():
    old_text=OUT.read_text(encoding='utf-8-sig',errors='replace') if OUT.exists() else ''
    old_count=old_text.count('#EXTINF:')
    old_urls=old_urls_by_id(old_text)
    items=json.loads(SRC.read_text(encoding='utf-8'))
    active=[(i,x) for i,x in enumerate(items) if x.get('id') not in SKIP_IDS]
    old_logos=existing_logos(); results=[]
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        for f in as_completed([ex.submit(resolve_item,i,item) for i,item in active]):
            results.append(f.result())
    results.sort(key=lambda x:x[0])
    out=['#EXTM3U','']; got=[]; failed=[]; seen=set(); fallback_count=0; duplicate_repairs=0
    active_ids={x.get('id') for _,x in active}

    for _,item,url,reason in results:
        name=item['name']; tvg=item['id']; code=(reason or ('NO_LIVE',''))[0]
        old_url=old_urls.get(tvg)

        # 華奈tubeは終了時に消す。古いHLSを復活させない。
        allow_old_fallback=(tvg!=KANA_ID and tvg in active_ids)
        if not url and code in SERIOUS_CODES and old_url and allow_old_fallback:
            url=old_url; fallback_count+=1
            failed.append((name,code,(reason or ('',''))[1]+' [previous URL kept]'))
        elif not url:
            c,d=reason or ('NO_LIVE','LIVE URL取得なし'); failed.append((name,c,d)); continue

        key=url.split('?')[0]
        if key in seen:
            if old_url and allow_old_fallback and old_url.split('?')[0] not in seen:
                url=old_url; key=url.split('?')[0]; duplicate_repairs+=1
                failed.append((name,'DUPLICATE_REPAIRED','新規検索が他局と重複したため前回URLを維持'))
            else:
                failed.append((name,'DUPLICATE','同一LIVE URLのため重複除外')); continue

        seen.add(key)
        out += make_entry(item,url,old_logos)
        got.append((name,item.get('group','一般YouTube LIVE')))

    text='\n'.join(out).rstrip()+'\n'
    output_count=len(got)
    serious=[x for x in failed if x[1] in SERIOUS_CODES]
    # 品質ゲート。ただし華奈tubeの非LIVEだけを理由に古い版へ巻き戻さない。
    if old_count>0 and serious and output_count<old_count:
        print(f'QUALITY GATE: keeping previous playlist ({old_count}) because rebuilt output is {output_count}.',flush=True)
        kept=apply_source_logos(old_text)
        OUT.write_text(kept,encoding='utf-8')
        return kept,got,failed

    OUT.write_text(text,encoding='utf-8')
    print(f'FALLBACK previous URLs: {fallback_count} / duplicate repairs: {duplicate_repairs}',flush=True)
    return text,got,failed


def merge_freewifi(general):
    base=FREEWIFI.read_text(encoding='utf-8-sig',errors='replace') if FREEWIFI.exists() else '#EXTM3U\n'
    pattern=re.compile(re.escape(START)+r'.*?'+re.escape(END),re.S)
    body='\n'.join(general.splitlines()[1:]).strip()
    block=START+'\n'+body+'\n'+END if body else START+'\n'+END
    FREEWIFI.write_text(pattern.sub(block,base) if pattern.search(base) else base.rstrip()+'\n\n'+block+'\n',encoding='utf-8')


def main():
    text,got,failed=build(); merge_freewifi(text)
    print('=== General YouTube LIVE diagnostic ===')
    print('OUTPUT ENTRIES:',text.count('#EXTINF:'))
    print('SUCCESS/KEPT:',len(got))
    for n,g in got: print(f' + OK [{g}] {n}')
    print('SKIP/FAIL/REPAIRED:',len(failed))
    for n,code,detail in failed:
        print(f' - {code}: {n}')
        if detail: print('   ',detail)
    groups={}
    for _,g in got: groups[g]=groups.get(g,0)+1
    print('=== GROUP COUNTS ===')
    for g in ['愛媛県内ライブカメラ','交通','動物','その他LIVE','かなチューブ','空港','競馬']:
        print(f'{g}: {groups.get(g,0)}')
    serious=[x for x in failed if x[1] in SERIOUS_CODES]
    if serious:
        print('=== WARNING: YouTube access restriction detected; previous per-channel URLs were preferred where safe ===')
        for n,code,detail in serious: print(f' ! {code}: {n} :: {detail}')

if __name__=='__main__': main()
