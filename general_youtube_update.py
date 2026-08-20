from pathlib import Path
import json, re, subprocess

SRC=Path('general_youtube_sources.json')
OUT=Path('general_youtube.m3u')
FREEWIFI=Path('freewifi')
COOKIES=Path('youtube_cookies.txt')
START='# === GENERAL_YOUTUBE_MANAGED_START ==='
END='# === GENERAL_YOUTUBE_MANAGED_END ==='


def run(cmd, timeout=90):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def base_cmd():
    cmd=['yt-dlp','--js-runtimes','node','--no-warnings']
    if COOKIES.exists() and COOKIES.stat().st_size>20:
        cmd += ['--cookies',str(COOKIES)]
    return cmd


def direct_url(page):
    selectors=['best[protocol^=m3u8][vcodec!=none][acodec!=none]','96/95/94/93/92/91','best[protocol^=m3u8]','best']
    for sel in selectors:
        p=run(base_cmd()+['--extractor-args','youtube:player_client=default,web_safari','--no-playlist','--match-filter','is_live','-f',sel,'-g',page],120)
        urls=[x.strip() for x in p.stdout.splitlines() if x.strip().startswith(('http://','https://'))]
        if p.returncode==0 and len(urls)==1:
            return urls[0]
    return None


def search_live(query):
    p=run(base_cmd()+['--flat-playlist','--dump-json','--playlist-end','6',f'ytsearch6:{query}'],90)
    pages=[]
    for line in p.stdout.splitlines():
        try: item=json.loads(line)
        except Exception: continue
        vid=item.get('id')
        if vid: pages.append('https://www.youtube.com/watch?v='+vid)
    for page in pages:
        try: u=direct_url(page)
        except Exception: u=None
        if u: return u
    return None


def build():
    items=json.loads(SRC.read_text(encoding='utf-8'))
    out=['#EXTM3U','']
    got=[]
    seen=set()
    for item in items:
        url=None
        page=item.get('page')
        if page:
            try: url=direct_url(page)
            except Exception: url=None
        if not url:
            q=item.get('query') or item.get('name')
            try: url=search_live(q)
            except Exception: url=None
        if not url: continue
        key=url.split('?')[0]
        if key in seen: continue
        seen.add(key)
        tvg=item['id']; name=item['name']; group=item.get('group','一般YouTube LIVE')
        out.append(f'#EXTINF:-1 tvg-id="{tvg}" tvg-name="{name}" group-title="{group}",{name}')
        out.append(url); out.append('')
        got.append(name)
    text='\n'.join(out).rstrip()+'\n'
    OUT.write_text(text,encoding='utf-8')
    return text,got


def merge_freewifi(general):
    base=FREEWIFI.read_text(encoding='utf-8-sig',errors='replace') if FREEWIFI.exists() else '#EXTM3U\n'
    pattern=re.compile(re.escape(START)+r'.*?'+re.escape(END),re.S)
    body='\n'.join(general.splitlines()[1:]).strip()
    block=START+'\n'+body+'\n'+END if body else START+'\n'+END
    if pattern.search(base):
        merged=pattern.sub(block,base)
    else:
        merged=base.rstrip()+'\n\n'+block+'\n'
    FREEWIFI.write_text(merged,encoding='utf-8')


def main():
    text,got=build()
    merge_freewifi(text)
    print('General YouTube LIVE:',len(got))
    for n in got: print(' +',n)

if __name__=='__main__':
    main()
