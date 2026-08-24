from pathlib import Path
import json
import re
import urllib.request

FREEWIFI = Path('freewifi')
PUBLIC_STATUS = Path('today_public_sports_status.json')
JRA_STATUS = Path('today_jra_status.json')
PUBLIC_M3U_URL = 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/public_sports.m3u'
START = '# === TODAY_PUBLIC_SPORTS_START ==='
END = '# === TODAY_PUBLIC_SPORTS_END ==='
GROUP = '今日の開催場'


def fetch_text(url):
    req = urllib.request.Request(url, headers={'User-Agent':'FreeWiFi-Verified-Status/1.0'})
    with urllib.request.urlopen(req, timeout=45) as r:
        return r.read().decode('utf-8-sig', errors='replace')


def parse_entries(text):
    out = {}
    lines = text.splitlines(); i = 0
    while i < len(lines):
        line = lines[i]
        if not line.startswith('#EXTINF:'):
            i += 1; continue
        block = [line]; j = i + 1
        while j < len(lines) and not lines[j].startswith('#EXTINF:') and not lines[j].startswith('## '):
            if lines[j].strip(): block.append(lines[j])
            j += 1
        m = re.search(r'tvg-id="([^"]+)"', line)
        if m: out[m.group(1)] = block
        i = j
    return out


def rewrite_group(extinf):
    if 'group-title=' in extinf:
        return re.sub(r'group-title="[^"]*"', f'group-title="{GROUP}"', extinf, count=1)
    comma = extinf.find(',')
    return extinf[:comma] + f' group-title="{GROUP}"' + extinf[comma:] if comma >= 0 else extinf


def replace_public_block(text, blocks):
    body = []
    for block in blocks:
        b = block[:]
        b[0] = rewrite_group(b[0])
        body.extend(b); body.append('')
    payload = '\n'.join(body).rstrip()
    managed = START + '\n## 今日の開催場\n' + payload + ('\n' if payload else '') + END
    pat = re.compile(re.escape(START) + r'.*?' + re.escape(END) + r'\n?', re.S)
    if pat.search(text):
        return pat.sub(managed + '\n', text, count=1)
    anchor = '# === GENERAL_YOUTUBE_MANAGED_START ==='
    return text.replace(anchor, managed + '\n\n' + anchor, 1) if anchor in text else text.rstrip() + '\n\n' + managed + '\n'


def strip_entries(text, ids):
    lines = text.splitlines(); out = []; i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('#EXTINF:') and any(f'tvg-id="{cid}"' in line for cid in ids):
            i += 1
            while i < len(lines) and not lines[i].startswith('#EXTINF:') and not lines[i].startswith('## ') and not lines[i].startswith('# ==='):
                i += 1
            continue
        out.append(line); i += 1
    return '\n'.join(out)


def main():
    if not FREEWIFI.exists() or not PUBLIC_STATUS.exists():
        return
    text = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    status = json.loads(PUBLIC_STATUS.read_text(encoding='utf-8-sig'))
    wanted = list((status.get('channels') or {}).keys())
    entries = parse_entries(fetch_text(PUBLIC_M3U_URL))
    blocks = [entries[cid] for cid in wanted if cid in entries]
    text = replace_public_block(text, blocks)

    jra = {}
    if JRA_STATUS.exists():
        try:
            jra = json.loads(JRA_STATUS.read_text(encoding='utf-8-sig'))
        except Exception:
            jra = {}
    if int(jra.get('active_count') or 0) == 0:
        text = re.sub(r'# === JRA_GCH_FREE_START ===.*?# === JRA_GCH_FREE_END ===\n?', '', text, flags=re.S)
        text = re.sub(r'# === JRA_OFFICIAL_YOUTUBE_START ===.*?# === JRA_OFFICIAL_YOUTUBE_END ===\n?', '', text, flags=re.S)
        text = strip_entries(text, {'jra.east','jra.west','jra.hokkaido','jra.official','jra.gch.free'})

    FREEWIFI.write_text(text.rstrip() + '\n', encoding='utf-8')
    print('Verified status override applied:', len(blocks), 'public sports channels; JRA active=', int(jra.get('active_count') or 0))


if __name__ == '__main__':
    main()
