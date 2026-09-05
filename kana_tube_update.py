from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

FREEWIFI = Path('freewifi')
OUT = Path('kana_tube.m3u')
COOKIES = Path('youtube_cookies.txt')
CHANNELS = (
    'https://www.youtube.com/channel/UCmHdGDdZGf4cMWRBmEw4Xww',
    'https://www.youtube.com/@kana_tube',
)
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
        p = subprocess.run(
            base_cmd()+[
                '--extractor-args','youtube:player_client=default,web_safari,web',
                '--no-playlist','--match-filter','is_live','-f',fmt,'-g',page
            ],
            capture_output=True, text=True, timeout=35,
        )
        urls=[x.strip() for x in p.stdout.splitlines() if x.strip().startswith(('http://','https://'))]
        if p.returncode == 0 and len(urls) == 1:
            return urls[0]
    return None


def candidate_ids_from_listing(listing: str, limit: int = 20) -> list[str]:
    """Return likely video ids even when flat-playlist omits live_status.

    YouTube sometimes leaves live_status blank in channel/search listings. The
    old detector discarded those rows before testing the watch page, causing a
    false 'not live'. Prefer rows explicitly marked live, but also validate a
    small number of unknown/upcoming/recent rows with direct(), which itself
    uses --match-filter is_live as the final truth check.
    """
    p = subprocess.run(
        base_cmd()+['--flat-playlist','--dump-json','--playlist-end',str(limit),listing],
        capture_output=True, text=True, timeout=40,
    )
    if p.returncode != 0:
        return []
    live=[]; other=[]
    for line in p.stdout.splitlines():
        try:
            item=json.loads(line)
        except Exception:
            continue
        vid=item.get('id')
        if not vid:
            continue
        vid=str(vid)
        status=(item.get('live_status') or '').lower()
        if status == 'is_live':
            live.append(vid)
        elif status not in {'was_live'}:
            other.append(vid)
    ordered=[]
    for vid in live + other:
        if vid not in ordered:
            ordered.append(vid)
    return ordered[:8]


def find_live() -> str | None:
    # 1) Prefer the immutable channel ID, with the current handle as fallback.
    for channel in CHANNELS:
        url = direct(channel + '/live')
        if url:
            print('Kana tube detector: canonical /live', channel)
            return url

    # 2) Check streams/videos on both channel identities. Do not require
    # flat-playlist to report is_live; direct() validates the actual watch page.
    checked_ids=set()
    for channel in CHANNELS:
        for listing in (channel+'/streams', channel+'/videos'):
            for vid in candidate_ids_from_listing(listing):
                if vid in checked_ids:
                    continue
                checked_ids.add(vid)
                url=direct('https://www.youtube.com/watch?v='+vid)
                if url:
                    print('Kana tube detector: channel listing', channel, vid)
                    return url

    # 3) Handle-independent fallbacks. Search recent results by the official
    # channel name, then let direct() decide whether each candidate is live.
    searches = (
        'ytsearchdate20:華奈tube 競輪',
        'ytsearch20:華奈tube 競輪 LIVE',
        'ytsearch20:かなチューブ 競輪 LIVE',
    )
    checked=set()
    for search in searches:
        p = subprocess.run(
            base_cmd()+['--flat-playlist','--dump-json','--playlist-end','20',search],
            capture_output=True, text=True, timeout=45,
        )
        if p.returncode != 0:
            continue
        for line in p.stdout.splitlines():
            try:
                item=json.loads(line)
            except Exception:
                continue
            if not item.get('id'):
                continue
            owner=' '.join(str(item.get(k) or '') for k in ('channel','uploader','channel_url','uploader_url'))
            title=str(item.get('title') or '')
            # Avoid publishing somebody else's keirin stream.
            if not any(key in owner or key in title for key in ('華奈tube','華奈','かなチューブ')):
                continue
            vid=str(item['id'])
            if vid in checked:
                continue
            checked.add(vid)
            url=direct('https://www.youtube.com/watch?v='+vid)
            if url:
                print('Kana tube detector: YouTube search fallback', vid, title)
                return url
            if len(checked) >= 12:
                break
        if len(checked) >= 12:
            break

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
