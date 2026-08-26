from pathlib import Path
from datetime import datetime, timezone, timedelta
import json
import re
import urllib.request
import xml.etree.ElementTree as ET

FREEWIFI = Path('freewifi')
JRA_STATUS = Path('today_jra_status.json')
HARUKA_OLD_BASE = 'http://ha-ip.f5.si:9394'
HARUKA_1_BASE = 'http://haruka-ip.f5.si:9394'
HARUKA_2_BASE = 'http://42.118.247.37:9394'

JRA_YT_LOGO = 'https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/youtube/jra_youtube_free.jpg'
JRA_GCH_LOGO = 'https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/youtube/jra_gch_free.jpg'
GUINEA_LOGO = 'https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/youtube/guinea_youtube.jpg'
GUINEA_PAGE = 'https://www.youtube.com/watch?v=sYCG1BPYWXk'
GCH_URL = 'https://manifest.streaks.jp/v4/gch-jra/97d99803d82b49bd9fc73cb568b219df/a214b09df7e04c22a15b4feba869b01d/hls/v3/manifest.m3u8?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJwcCI6IjNhZWVhMzU2ZmQ0MzQyMzE4ZjRhNDg2OWUwMzFiMDZiIiwiZGMiOiJjYTlmZDAwYTRiMmU0YTg1OGEyNmM1MTY5ZDIwY2U0ZiIsImVkZ2UiOiIzYjY5ZGJiYjYwMmI0M2NlODFmYjdkNGI3NjE0NjEzMCIsImNvZGVjcyI6ImF1dG8iLCJleHAiOjE3ODc1NDA0MDAsImlvcyI6MTgsInBwdyI6IjRwaiJ9.5EL6z0Gaoaj0haNQ3B1tui-B5vpNbxdb0t3dTHYFySE'
PUBLIC_EPG_URL = 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/epg.xml'
JST = timezone(timedelta(hours=9))

GCH_START = '# === JRA_GCH_FREE_START ==='
GCH_END = '# === JRA_GCH_FREE_END ==='
GUINEA_START = '# === GUINEA_YOUTUBE_START ==='
GUINEA_END = '# === GUINEA_YOUTUBE_END ==='
ECATV_START = '# === EHIME_CATV_START ==='
ECATV_END = '# === EHIME_CATV_END ==='

ECATV_BLOCK = '''# === EHIME_CATV_START ===
## 愛媛CATV

#EXTINF:-1 tvg-id="ecatv.town_premium" group-title="愛媛CATV" tvg-logo="https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/ehime_catv/01_town_premium.png",たうんプレミアム
https://cdn-ecatv-stream.durasite.net/live/plala.town/playlist.m3u8

#EXTINF:-1 tvg-id="ecatv.town_news24" group-title="愛媛CATV" tvg-logo="https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/ehime_catv/02_town_news24.png",たうんNews24
https://cdn.e-catv.ne.jp/mpeg-dash/hc_town_news_24/dash.mpd

#EXTINF:-1 group-title="愛媛CATV" tvg-logo="https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/ehime_catv/03_machicam24.png",街カメ24
https://cdn.e-catv.ne.jp/mpeg-dash/hc_machi_cam_24/dash.mpd

#EXTINF:-1 group-title="愛媛CATV" tvg-logo="https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/ehime_catv/04_info.png",お知らせチャンネル
https://cdn-ecatv-stream.durasite.net/live/plala.info/playlist.m3u8

#EXTINF:-1 group-title="愛媛CATV" tvg-logo="https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/ehime_catv/05_program_promo.png",番組宣伝ch
https://cdn-ecatv-stream.durasite.net/live/plala.machisuki/playlist.m3u8

#EXTINF:-1 tvg-id="ecatv.event_premium" group-title="愛媛CATV" tvg-logo="https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/ehime_catv/06_event_premium.png",イベントプレミアム
https://cdn-ecatv-stream.durasite.net/live/plala.event/playlist.m3u8

#EXTINF:-1 tvg-id="ecatv.event_selection" group-title="愛媛CATV" tvg-logo="https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/ehime_catv/07_event_selection.png",イベントセレクション
https://cdn.e-catv.ne.jp/mpeg-dash/hc_eventsel_channel/dash.mpd

#EXTINF:-1 group-title="愛媛CATV" tvg-logo="https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/ehime_catv/08_ehime_channel.png",えひめチャンネル
https://cdn.e-catv.ne.jp/mpeg-dash/hc_ehime_channel/dash.mpd

#EXTINF:-1 tvg-id="ecatv.bousai" group-title="愛媛CATV" tvg-logo="https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/ehime_catv/09_ehime_bousai.png",えひめ・防災チャンネル
https://cdn.e-catv.ne.jp/mpeg-dash/hc_bousai_channel/dash.mpd

#EXTINF:-1 tvg-id="囲碁・将棋チャンネル_jp" group-title="愛媛CATV" tvg-logo="https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/ehime_catv/10_igo_shogi.png",囲碁・将棋チャンネル(eCATV)
https://cdn.e-catv.ne.jp/mpeg-dash/hc_gosho_channel/dash.mpd

#EXTINF:-1 tvg-id="日経CNBC_jp" group-title="愛媛CATV" tvg-logo="https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/ehime_catv/13_nikkei_cnbc.png",日経CNBC(eCATV)
https://cdn4.nikkei-cnbc.co.jp/live-ch01/livestream/ts:playlist.m3u8

#EXTINF:-1 group-title="愛媛CATV" tvg-logo="https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/ehime_catv/14_matsuyama_gikai.png",松山市議会中継
https://cdn-ecatv-stream.durasite.net/live/ms_gikai/chunklist_w152985868.m3u8

#EXTINF:-1 group-title="愛媛CATV" tvg-logo="https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/ehime_catv/15_ehime_gikai.png",愛媛県議会中継
https://cdn-ecatv-stream.durasite.net/live/kengikai/chunklist_w1364306427.m3u8
# === EHIME_CATV_END ==='''


def patch_haruka_sources(text):
    """Keep both working HARUKA endpoints as separate playlist entries."""
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('#EXTINF:') and i + 1 < len(lines):
            url = lines[i + 1].strip()
            if any(base in url for base in (HARUKA_OLD_BASE, HARUKA_1_BASE, HARUKA_2_BASE)):
                path = re.search(r'(/stream/[^\s]+)', url)
                if path:
                    stream_path = path.group(1)
                    info1 = re.sub(r',([^,]*)$', lambda m: ',' + re.sub(r'\s*\(haruka[^)]*\)', '', m.group(1), flags=re.I) + ' (ハルカ1)', line)
                    info2 = re.sub(r',([^,]*)$', lambda m: ',' + re.sub(r'\s*\(haruka[^)]*\)', '', m.group(1), flags=re.I) + ' (ハルカ2)', line)
                    out.extend([info1, HARUKA_1_BASE + stream_path, info2, HARUKA_2_BASE + stream_path])
                    i += 2
                    continue
        out.append(line)
        i += 1
    return '\n'.join(out).rstrip() + '\n'


def replace_managed_block(text, start, end, block, anchor='## 競馬\n'):
    pat = re.compile(re.escape(start) + r'.*?' + re.escape(end) + r'\n?', re.S)
    text = pat.sub('', text)
    if block:
        if anchor in text:
            text = text.replace(anchor, anchor + '\n' + block + '\n', 1)
        else:
            text = text.rstrip() + '\n\n' + block + '\n'
    return text


def ensure_ecatv(text):
    text = re.sub(re.escape(ECATV_START) + r'.*?' + re.escape(ECATV_END) + r'\n?', '', text, flags=re.S)
    text = re.sub(r'\n## 愛媛CATV\n.*?(?=\n## |\n# === GENERAL_YOUTUBE_MANAGED_START ===|\Z)', '\n', text, flags=re.S)
    anchor = '# === GENERAL_YOUTUBE_MANAGED_START ==='
    if anchor in text:
        return text.replace(anchor, ECATV_BLOCK + '\n\n' + anchor, 1)
    return text.rstrip() + '\n\n' + ECATV_BLOCK + '\n'


def patch_jra_youtube(text):
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith('#EXTINF:') and 'tvg-id="jra.official"' in line:
            lines[i] = '#EXTINF:-1 tvg-id="jra.official" tvg-name="JRA公式（YouTube）無料版" tvg-logo="%s" group-title="競馬",JRA公式（YouTube）無料版' % JRA_YT_LOGO
    return '\n'.join(lines).rstrip() + '\n'


def parse_xmltv_time(s):
    if not s: return None
    m = re.match(r'^(\d{14})\s*([+-]\d{4})?', s.strip())
    if not m: return None
    base = datetime.strptime(m.group(1), '%Y%m%d%H%M%S')
    off = m.group(2)
    if off:
        sign = 1 if off[0] == '+' else -1
        tz = timezone(sign * timedelta(hours=int(off[1:3]), minutes=int(off[3:5])))
        return base.replace(tzinfo=tz)
    return base.replace(tzinfo=JST)


def is_jra_race_day():
    try:
        if JRA_STATUS.exists():
            data = json.loads(JRA_STATUS.read_text(encoding='utf-8'))
            generated = data.get('generated_at')
            if generated:
                stamp = datetime.fromisoformat(generated).astimezone(JST)
                if stamp.date() == datetime.now(JST).date(): return int(data.get('active_count') or 0) > 0
    except Exception as e: print('JRA verified status check failed:', e)
    try:
        req = urllib.request.Request(PUBLIC_EPG_URL, headers={'User-Agent': 'FreeWiFi-GCH-DayCheck/1.0', 'Cache-Control': 'no-cache'})
        with urllib.request.urlopen(req, timeout=60) as r: root = ET.fromstring(r.read())
        today = datetime.now(JST).date(); source_ids = {'jra.east', 'jra.west', 'jra.hokkaido'}
        for p in root.findall('programme'):
            if (p.get('channel') or '') not in source_ids: continue
            start = parse_xmltv_time(p.get('start'))
            if not start or start.astimezone(JST).date() != today: continue
            title = (p.findtext('title') or '').strip()
            if title and not any(w in title for w in ('非開催', '休止', '準備中', 'データ取得準備中')): return True
        return False
    except Exception as e: print('JRA race-day check failed:', e); return False


def get_guinea_hls():
    try:
        from general_youtube_update import direct_url
        url, _ = direct_url(GUINEA_PAGE); return url
    except Exception as e: print('Guinea LIVE lookup failed:', e); return None


def main():
    text = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    text = patch_haruka_sources(text)
    text = patch_jra_youtube(text)
    text = ensure_ecatv(text)
    if is_jra_race_day():
        gch_extinf = '#EXTINF:-1 tvg-id="jra.gch.free" tvg-name="JRA公式（GCH）無料版【開催中のみ】" tvg-logo="%s" group-title="競馬",JRA公式（GCH）無料版【開催中のみ】' % JRA_GCH_LOGO
        gch_block = f'{GCH_START}\n{gch_extinf}\n{GCH_URL}\n{GCH_END}'
    else: gch_block = ''
    text = replace_managed_block(text, GCH_START, GCH_END, gch_block, '## 競馬\n')
    guinea_url = get_guinea_hls()
    if guinea_url:
        guinea_extinf = '#EXTINF:-1 tvg-id="youtube.guinea" tvg-name="モルモット配信（YouTube）" tvg-logo="%s" group-title="動物",モルモット配信（YouTube）' % GUINEA_LOGO
        guinea_block = f'{GUINEA_START}\n{guinea_extinf}\n{guinea_url}\n{GUINEA_END}'
    else: guinea_block = ''
    text = replace_managed_block(text, GUINEA_START, GUINEA_END, guinea_block, '# === GENERAL_YOUTUBE_MANAGED_END ===\n')
    FREEWIFI.write_text(text.rstrip() + '\n', encoding='utf-8')
    print('Custom FreeWiFi channels applied')
    try:
        from freewifi_today_public_sports import main as sync_today_public_sports
        sync_today_public_sports()
    except Exception as e: print('Today public sports sync failed:', e)
    try:
        from apply_verified_status import main as apply_verified_status
        apply_verified_status()
    except Exception as e: print('Verified status override failed:', e)
    try:
        from freewifi_keirin_repair import main as repair_keirin
        repair_keirin()
    except Exception as e: print('Keirin fallback repair failed:', e)


if __name__ == '__main__': main()
