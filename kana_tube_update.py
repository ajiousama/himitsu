from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

FREEWIFI = Path('freewifi')
OUT = Path('kana_tube.m3u')
COOKIES = Path('youtube_cookies.txt')
CHANNEL = 'https://www.youtube.com/@kanatubechannel'
LIVE_PAGE = CHANNEL + '/live'
ID = 'youtube.kana_tube'
NAME = 'かなチューブ'
LOGO = 'https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/youtube/yt43_01_kana_tube.png'
START = '# === KANA_TUBE_MANAGED_START ==='
END = '# === KANA_TUBE_MANAGED_END ==='


def base_cmd() -> list[str]:
    cmd = ['yt-dlp','--js-runtimes','node','--no-warnings','--no-cache-dir','--socket-timeout','10','--retries','1','--fragment-retries','1']
    if COOKIES.exists() and COOKIES.stat().st_size > 20:
        cmd += ['--cookies', str(COOKIES)]
    return cmd


def direct(page: str) -> str | None:
    for fmt in ('best[protocol^=m3u8]','best'):
        p = subprocess.run(base_cmd()+['--extractor-args','youtube:player_client=default,web_safari,web','--no-playlist','--match-filter','is_live','-f',fmt,'-g',page], capture_output=True, text=True, timeout=35)
        urls=[x.strip() for x in p.stdout.splitlines() if x.strip().startswith(('http://','https://'))]
        if p.returncode == 0 and len(urls) == 1:
            return urls[0]
    return None


def find_live() -> str | None:
    # First ask the channel's canonical /live endpoint. This follows whatever
    # video ID Kana Tube is currently using, so a new broadcast does not break
    # detection when the old watch URL changes.
    url = direct(LIVE_PAGE)
    if url:
        return url

    # Fallback: inspect the actual channel listings (not a watch URL + /streams).
    # Keep the same small request footprint as before: at most two listings.
    for listing in (CHANNEL+'/streams', CHANNEL+'/videos'):
        p = subprocess.run(base_cmd()+['--flat-playlist','--dump-json','--playlist-end','30',listing], capture_output=True, text=True, timeout=35)
        if p.returncode != 0:
            continue
        ids=[]
        for line in p.stdout.splitlines():
            try:
                item=json.loads(line)
            except Exception:
                continue
            if (item.get('live_status') or '').lower() == 'is_live' and item.get('id'):
                ids.append(item['id'])
        for vid in ids:
            url=direct('https://www.youtube.com/watch?v='+vid)
            if url:
                return url
    return None


def strip_entry(text: str, tvg_id: str) -> str:
    text = re.sub(re.escape(START)+r'.*?'+re.escape(END)+r'\n?', '', text, flags=re.S)
    lines=text.splitlines(); out=[]; i=0
    while i < len(lines):
        line=lines[i]
        if line.startswith('#EXTINF:') and f'tvg-id="{tvg_id}"' in line:
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i < len(lines) and lines[i].strip().startswith(('http://','https://')):
                i += 1
            continue
        out.append(line); i += 1
    return '\n'.join(out).rstrip()+'\n'


def entry(url: str) -> str:
    return (f'#EXTINF:-1 tvg-id="{ID}" tvg-name="{NAME}" tvg-logo="{LOGO}" group-title="かなチューブ",{NAME}\n'
            f'{url}\n')


def normalized_urls(text: str) -> set[str]:
    return {ln.strip().split('?',1)[0] for ln in text.splitlines() if ln.strip().startswith(('http://','https://'))}


def main() -> int:
    base=FREEWIFI.read_text(encoding='utf-8-sig',errors='replace') if FREEWIFI.exists() else '#EXTM3U\n'
    clean=strip_entry(base, ID)
    url=find_live()
    if url:
        key=url.split('?',1)[0]
        if key in normalized_urls(clean):
            raise RuntimeError('Kana tube live URL duplicates an existing channel URL; refusing duplicate insertion')
        block=START+'\n'+entry(url)+END+'\n'
        anchor='# === GENERAL_YOUTUBE_MANAGED_START ==='
        if anchor in clean:
            clean=clean.replace(anchor, block+'\n'+anchor, 1)
        else:
            clean=clean.rstrip()+'\n\n'+block
        OUT.write_text('#EXTM3U\n\n'+entry(url),encoding='utf-8')
        print('Kana tube: LIVE published')
    else:
        OUT.write_text('#EXTM3U\n',encoding='utf-8')
        print('Kana tube: not live; removed from FreeWiFi')
    if clean.count(f'tvg-id="{ID}"') > 1:
        raise RuntimeError('duplicate Kana tube tvg-id detected')
    FREEWIFI.write_text(clean.rstrip()+'\n',encoding='utf-8')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
