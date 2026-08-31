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
#EXTINF:-1 tvg-id="ecatv.machicam24" group-title="愛媛CATV" tvg-logo="https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/ehime_catv/03_machicam24.png",街カメ24
https://cdn.e-catv.ne.jp/mpeg-dash/hc_machi_cam_24/dash.mpd
#EXTINF:-1 tvg-id="ecatv.info" group-title="愛媛CATV" tvg-logo="https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/ehime_catv/04_info.png",お知らせチャンネル
https://cdn-ecatv-stream.durasite.net/live/plala.info/playlist.m3u8
#EXTINF:-1 tvg-id="ecatv.program_promo" group-title="愛媛CATV" tvg-logo="https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/ehime_catv/05_program_promo.png",番組宣伝ch
https://cdn-ecatv-stream.durasite.net/live/plala.machisuki/playlist.m3u8
#EXTINF:-1 tvg-id="ecatv.event_premium" group-title="愛媛CATV" tvg-logo="https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/ehime_catv/06_event_premium.png",イベントプレミアム
https://cdn-ecatv-stream.durasite.net/live/plala.event/playlist.m3u8
#EXTINF:-1 tvg-id="ecatv.event_selection" group-title="愛媛CATV" tvg-logo="https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/ehime_catv/07_event_selection.png",イベントセレクション
https://cdn.e-catv.ne.jp/mpeg-dash/hc_eventsel_channel/dash.mpd
#EXTINF:-1 tvg-id="ecatv.ehime_channel" group-title="愛媛CATV" tvg-logo="https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/ehime_catv/08_ehime_channel.png",えひめチャンネル
https://cdn.e-catv.ne.jp/mpeg-dash/hc_ehime_channel/dash.mpd
#EXTINF:-1 tvg-id="ecatv.bousai" group-title="愛媛CATV" tvg-logo="https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/ehime_catv/09_ehime_bousai.png",えひめ・防災チャンネル
https://cdn.e-catv.ne.jp/mpeg-dash/hc_bousai_channel/dash.mpd
#EXTINF:-1 tvg-id="囲碁・将棋チャンネル_jp" group-title="愛媛CATV" tvg-logo="https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/ehime_catv/10_igo_shogi.png",囲碁・将棋チャンネル(eCATV)
https://cdn.e-catv.ne.jp/mpeg-dash/hc_gosho_channel/dash.mpd
#EXTINF:-1 tvg-id="日経CNBC_jp" group-title="愛媛CATV" tvg-logo="https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/ehime_catv/13_nikkei_cnbc.png",日経CNBC(eCATV)
https://cdn4.nikkei-cnbc.co.jp/live-ch01/livestream/ts:playlist.m3u8
#EXTINF:-1 tvg-id="ecatv.matsuyama_gikai" group-title="愛媛CATV" tvg-logo="https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/ehime_catv/14_matsuyama_gikai.png",松山市議会中継
https://cdn-ecatv-stream.durasite.net/live/ms_gikai/chunklist_w152985868.m3u8
#EXTINF:-1 tvg-id="ecatv.ehime_gikai" group-title="愛媛CATV" tvg-logo="https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/ehime_catv/15_ehime_gikai.png",愛媛県議会中継
https://cdn-ecatv-stream.durasite.net/live/kengikai/chunklist_w1364306427.m3u8
# === EHIME_CATV_END ==='''


def suspend_5002(text):
    lines = text.splitlines()
    out = []
    i = 0
    removed = 0
    while i < len(lines):
        if lines[i].startswith('#EXTINF:') and i + 1 < len(lines) and '58.82.168.138:5002/' in lines[i + 1]:
            removed += 1
            i += 2
            continue
        out.append(lines[i])
        i += 1
    print('5002 suspended entries:', removed)
    return '\n'.join(out).rstrip() + '\n'


def _clean_haruka_name(extinf):
    if ',' not in extinf:
        return extinf
    meta, name = extinf.rsplit(',', 1)
    name = re.sub(r'\s*\((?:haruka|ハルカ)(?:\s*[12])?\)\s*$', '', name, flags=re.I)
    return meta + ',' + name.strip()


def patch_haruka_sources(text):
    lines = text.splitlines()
    out = []
    seen = set()
    i = 0
    generated = 0

    while i < len(lines):
        line = lines[i]
        if line.startswith('#EXTINF:') and i + 1 < len(lines):
            url = lines[i + 1].strip()
            if any(base in url for base in (HARUKA_OLD_BASE, HARUKA_1_BASE, HARUKA_2_BASE)):
                m = re.search(r'(/stream/[^\s]+)', url)
                if m:
                    stream_path = m.group(1)
                    tvg = re.search(r'tvg-id="([^"]*)"', line)
                    key = ((tvg.group(1) if tvg else ''), stream_path)
                    if key not in seen:
                        seen.add(key)
                        base_info = _clean_haruka_name(line)
                        meta, name = base_info.rsplit(',', 1)
                        out.extend([
                            f'{meta},{name} (ハルカ1)',
                            HARUKA_1_BASE + stream_path,
                            f'{meta},{name} (ハルカ2)',
                            HARUKA_2_BASE + stream_path,
                        ])
                        generated += 1
                    i += 2
                    continue
        out.append(line)
        i += 1

    print('HARUKA channel pairs:', generated)
    return '\n'.join(out).rstrip() + '\n'


def replace_managed_block(text, start, end, block, anchor='## 競馬\n'):
    text = re.sub(re.escape(start) + r'.*?' + re.escape(end) + r'\n?', '', text, flags=re.S)
    if block:
        text = text.replace(anchor, anchor + '\n' + block + '\n', 1) if anchor in text else text.rstrip() + '\n\n' + block + '\n'
    return text


def ensure_ecatv(text):
    text = re.sub(re.escape(ECATV_START) + r'.*?' + re.escape(ECATV_END) + r'\n?', '', text, flags=re.S)
    text = re.sub(r'\n## 愛媛CATV\n.*?(?=\n## |\n# === GENERAL_YOUTUBE_MANAGED_START ===|\Z)', '\n', text, flags=re.S)
    anchor = '# === GENERAL_YOUTUBE_MANAGED_START ==='
    return text.replace(anchor, ECATV_BLOCK + '\n\n' + anchor, 1) if anchor in text else text.rstrip() + '\n\n' + ECATV_BLOCK + '\n'


def patch_jra_youtube(text):
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.startswith('#EXTINF:') and 'tvg-id="jra.official"' in line:
            lines[i] = f'#EXTINF:-1 tvg-id="jra.official" tvg-name="JRA公式（YouTube）無料版" tvg-logo="{JRA_YT_LOGO}" group-title="競馬",JRA公式（YouTube）無料版'
    return '\n'.join(lines).rstrip() + '\n'


def parse_xmltv_time(s):
    if not s:
        return None
    m = re.match(r'^(\d{14})\s*([+-]\d{4})?', s.strip())
    if not m:
        return None
    base = datetime.strptime(m.group(1), '%Y%m%d%H%M%S')
    off = m.group(2)
    if off:
        sign = 1 if off[0] == '+' else -1
        return base.replace(tzinfo=timezone(sign * timedelta(hours=int(off[1:3]), minutes=int(off[3:5]))))
    return base.replace(tzinfo=JST)


def is_jra_race_day():
    try:
        if JRA_STATUS.exists():
            data = json.loads(JRA_STATUS.read_text(encoding='utf-8'))
            generated = data.get('generated_at')
            if generated and datetime.fromisoformat(generated).astimezone(JST).date() == datetime.now(JST).date():
                return int(data.get('active_count') or 0) > 0
    except Exception as e:
        print('JRA verified status check failed:', e)
    try:
        req = urllib.request.Request(PUBLIC_EPG_URL, headers={'User-Agent': 'FreeWiFi-GCH-DayCheck/1.0', 'Cache-Control': 'no-cache'})
        with urllib.request.urlopen(req, timeout=60) as r:
            root = ET.fromstring(r.read())
        today = datetime.now(JST).date()
        for p in root.findall('programme'):
            if (p.get('channel') or '') not in {'jra.east', 'jra.west', 'jra.hokkaido'}:
                continue
            start = parse_xmltv_time(p.get('start'))
            title = (p.findtext('title') or '').strip()
            if start and start.astimezone(JST).date() == today and title and not any(w in title for w in ('非開催', '休止', '準備中', 'データ取得準備中')):
                return True
        return False
    except Exception as e:
        print('JRA race-day check failed:', e)
        return False


def get_guinea_hls():
    try:
        from general_youtube_update import direct_url
        url, _ = direct_url(GUINEA_PAGE)
        return url
    except Exception as e:
        print('Guinea LIVE lookup failed:', e)
        return None


def validate_before_write(original, updated):
    original_count = original.count('#EXTINF:')
    updated_count = updated.count('#EXTINF:')
    if not updated.startswith('#EXTM3U'):
        raise RuntimeError('Refusing to write: #EXTM3U header disappeared')
    if updated_count < 50:
        raise RuntimeError(f'Refusing to write: only {updated_count} channels remain')
    if original_count >= 50 and updated_count < original_count * 0.60:
        raise RuntimeError(f'Refusing to write: channel count collapsed {original_count} -> {updated_count}')
    if len(updated) < 10000:
        raise RuntimeError(f'Refusing to write: output unexpectedly small ({len(updated)} bytes)')


def main():
    original = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    if not original.strip():
        raise RuntimeError('Refusing to process: freewifi is empty')

    text = suspend_5002(original)
    text = patch_haruka_sources(text)
    text = patch_jra_youtube(text)
    text = ensure_ecatv(text)

    if is_jra_race_day():
        ext = f'#EXTINF:-1 tvg-id="jra.gch.free" tvg-name="JRA公式（GCH）無料版【開催中のみ】" tvg-logo="{JRA_GCH_LOGO}" group-title="競馬",JRA公式（GCH）無料版【開催中のみ】'
        block = f'{GCH_START}\n{ext}\n{GCH_URL}\n{GCH_END}'
    else:
        block = ''
    text = replace_managed_block(text, GCH_START, GCH_END, block, '## 競馬\n')

    guinea = get_guinea_hls()
    block = f'{GUINEA_START}\n#EXTINF:-1 tvg-id="youtube.guinea" tvg-name="モルモット配信（YouTube）" tvg-logo="{GUINEA_LOGO}" group-title="動物",モルモット配信（YouTube）\n{guinea}\n{GUINEA_END}' if guinea else ''
    text = replace_managed_block(text, GUINEA_START, GUINEA_END, block, '# === GENERAL_YOUTUBE_MANAGED_END ===\n')

    validate_before_write(original, text)
    FREEWIFI.write_text(text.rstrip() + '\n', encoding='utf-8')
    print('Custom FreeWiFi channels applied safely; 5002 suspended; HARUKA1/2 canonicalized')

    try:
        from freewifi_today_public_sports import main as sync_today_public_sports
        sync_today_public_sports()
    except Exception as e:
        print('Today public sports sync failed:', e)
    try:
        from apply_verified_status import main as apply_verified_status
        apply_verified_status()
    except Exception as e:
        print('Verified status override failed:', e)
    try:
        from freewifi_keirin_repair import main as repair_keirin
        repair_keirin()
    except Exception as e:
        print('Keirin fallback repair failed:', e)


if __name__ == '__main__':
    main()
