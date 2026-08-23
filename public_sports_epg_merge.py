from pathlib import Path
import re
import urllib.request
import xml.etree.ElementTree as ET

FREEWIFI = Path('freewifi')
GUIDES = Path('guides.xml')
PUBLIC_EPG_URL = 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/epg.xml'
PREFIXES = ('keirin.', 'chihou.', 'boat.', 'auto.')


def wanted_ids():
    ids = set()
    text = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    for line in text.splitlines():
        if not line.startswith('#EXTINF:'):
            continue
        m = re.search(r'tvg-id="([^"]+)"', line)
        if m and m.group(1).startswith(PREFIXES):
            ids.add(m.group(1))
    return ids


def fetch_public_epg():
    req = urllib.request.Request(PUBLIC_EPG_URL, headers={'User-Agent': 'FreeWiFi-PublicSports-EPG/1.0'})
    with urllib.request.urlopen(req, timeout=60) as r:
        return ET.fromstring(r.read())


def main():
    wanted = wanted_ids()
    if not wanted:
        print('Public sports EPG: no target channels in FreeWiFi')
        return

    dst = ET.parse(GUIDES).getroot()
    src = fetch_public_epg()

    # epg_build.py may have created fallback entries for these IDs.
    for el in list(dst):
        if el.tag == 'channel' and el.get('id') in wanted:
            dst.remove(el)
        elif el.tag == 'programme' and el.get('channel') in wanted:
            dst.remove(el)

    channels = 0
    programmes = 0
    for ch in src.findall('channel'):
        cid = ch.get('id')
        if cid in wanted:
            dst.append(ET.fromstring(ET.tostring(ch, encoding='utf-8')))
            channels += 1

    for p in src.findall('programme'):
        cid = p.get('channel')
        if cid in wanted:
            dst.append(ET.fromstring(ET.tostring(p, encoding='utf-8')))
            programmes += 1

    ET.indent(dst, space='  ')
    GUIDES.write_bytes(ET.tostring(dst, encoding='utf-8', xml_declaration=True))
    print(f'Public sports EPG merged: channels={channels}, programmes={programmes}, wanted={len(wanted)}')


if __name__ == '__main__':
    main()
