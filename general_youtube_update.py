from pathlib import Path
import json, re, subprocess

SRC=Path('general_youtube_sources.json')
OUT=Path('general_youtube.m3u')
FREEWIFI=Path('freewifi')
COOKIES=Path('youtube_cookies.txt')
START='# === GENERAL_YOUTUBE_MANAGED_START ==='
END='# === GENERAL_YOUTUBE_MANAGED_END ==='
SKIP_IDS={'youtube.kobe_waterfront2','youtube.narita_t1'}

# GitHub Actions で1局が固まって全体を止めないための上限。
CMD_TIMEOUT=20
SEARCH_TIMEOUT=20


def run(cmd, timeout=CMD_TIMEOUT):
    # yt-dlp 内部のHTTP待ちも短くする。subprocess側でも必ず打ち切る。
    safe=list(cmd)
    if safe and safe[0]=='yt-dlp':
        safe[1:1]=['--socket-timeout','8','--retries','1','--fragment-retries','1']
    return subprocess.run(safe, capture_output=True, text=True, timeout=timeout)


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


def direct_url(page, label=''):
    # まずHLSを広く1回だけ取得。以前の4 selector連続試行は1動画最大8分待ちになり得た。
    selectors=['best[protocol^=m3u8]','best']
    last_err=''
    for sel in selectors:
        try:
            p=run(base_cmd()+['--extractor-args','youtube:player_client=default,web_safari','--no-playlist','--match-filter','is_live','-f',sel,'-g',page],CMD_TIMEOUT)
        except subprocess.TimeoutExpired:
            last_err='yt-dlp direct URL timeout'
            continue
        urls=[x.strip() for x in p.stdout.splitlines() if x.strip().startswith(('http://','https://'))]
        if p.returncode==0 and len(urls)==1:
            return urls[0], None
        if p.stderr: last_err=p.stderr
    if last_err=='yt-dlp direct URL timeout':
        return None, ('TIMEOUT',last_err)
    return None, (classify_error(last_err), short_error(last_err))


def search_live(query, label=''):
    try:
        p=run(base_cmd()+['--flat-playlist','--dump-json','--playlist-end','3',f'ytsearch3:{query}'],SEARCH_TIMEOUT)
    except subprocess.TimeoutExpired:
        return None, ('TIMEOUT','YouTube search timeout')
    if p.returncode!=0:
        return None, ('SEARCH_ERROR', short_error(p.stderr))
    pages=[]
    for line in p.stdout.splitlines():
        try: item=json.loads(line)
        except Exception: continue
        vid=item.get('id')
        if vid: pages.append('https://www.youtube.com/watch?v='+vid)
    if not pages: return None, ('SEARCH_EMPTY','検索結果なし')
    reasons=[]
    for page in pages:
        try: u,err=direct_url(page,label)
        except Exception as e:
            reasons.append(('EXCEPTION',str(e)[:300])); continue
        if u: return u,None
        if err: reasons.append(err)
    priority=['RATE_LIMIT','BOT_CHECK','COOKIE_ERROR','TIMEOUT','NOT_STARTED','NOT_LIVE','PRIVATE','UNAVAILABLE','UNSUPPORTED','OTHER']
    for code in priority:
        for r in reasons:
            if r[0]==code: return None,r
    return None,('NO_LIVE','LIVE URL取得なし')


def jra_channel_live():
    candidates=[]; last_err=''
    # JRAは既知ページを先に使い、重いチャンネル全走査はしない。
    for source in ['https://www.youtube.com/@jraofficial/live']:
        try:
            p=run(base_cmd()+['--flat-playlist','--dump-json','--playlist-end','8',source],SEARCH_TIMEOUT)
        except subprocess.TimeoutExpired:
            last_err='JRA channel scan timeout'; continue
        if p.stderr: last_err=p.stderr
        for line in p.stdout.splitlines():
            try: item=json.loads(line)
            except Exception: continue
            vid=item.get('id')
            if vid:
                page='https://www.youtube.com/watch?v='+vid
                if page not in candidates: candidates.append(page)
    reasons=[]
    for page in candidates[:4]:
        u,err=direct_url(page,'JRA公式YouTube')
        if u: return u,None
        if err: reasons.append(err)
    if reasons: return None,reasons[0]
    return None,('JRA_SCAN_EMPTY',short_error(last_err) or 'JRA公式チャンネルからLIVE取得なし')


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


def build():
    items=json.loads(SRC.read_text(encoding='utf-8')); old_logos=existing_logos()
    out=['#EXTM3U','']; got=[]; failed=[]; seen=set()
    for item in items:
        if item.get('id') in SKIP_IDS: continue
        name=item['name']; url=None; reason=None; page=item.get('page')
        print('CHECK:',name,flush=True)
        try:
            if item.get('id')=='jra.official': url,reason=jra_channel_live()
            if not url and page: url,reason=direct_url(page,name)
            if not url:
                url,sr=search_live(item.get('query') or name,name)
                if sr: reason=sr
        except subprocess.TimeoutExpired:
            reason=('TIMEOUT','channel timeout')
        except Exception as e:
            reason=('EXCEPTION',str(e)[:300])
        if not url:
            code,detail=reason or ('NO_LIVE','LIVE URL取得なし'); failed.append((name,code,detail)); continue
        key=url.split('?')[0]
        if key in seen:
            failed.append((name,'DUPLICATE','同一LIVE URLのため重複除外')); continue
        seen.add(key)
        tvg=item['id']; group=item.get('group','一般YouTube LIVE'); logo=(item.get('logo') or old_logos.get(tvg) or '').strip()
        attrs=f'tvg-id="{tvg}" tvg-name="{name}"'
        if logo: attrs+=f' tvg-logo="{logo}"'
        attrs+=f' group-title="{group}"'
        out += [f'#EXTINF:-1 {attrs},{name}',url,'']; got.append((name,group))
    text='\n'.join(out).rstrip()+'\n'; OUT.write_text(text,encoding='utf-8'); return text,got,failed


def merge_freewifi(general):
    base=FREEWIFI.read_text(encoding='utf-8-sig',errors='replace') if FREEWIFI.exists() else '#EXTM3U\n'
    pattern=re.compile(re.escape(START)+r'.*?'+re.escape(END),re.S)
    body='\n'.join(general.splitlines()[1:]).strip(); block=START+'\n'+body+'\n'+END if body else START+'\n'+END
    merged=pattern.sub(block,base) if pattern.search(base) else base.rstrip()+'\n\n'+block+'\n'
    FREEWIFI.write_text(merged,encoding='utf-8')


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
