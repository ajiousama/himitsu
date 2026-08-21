from pathlib import Path
import copy
import urllib.request
import xml.etree.ElementTree as ET

GUIDES = Path('guides.xml')
PUBLIC_EPG = 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/epg.xml'
TARGET_ID = 'jra.official'
SOURCE_IDS = {'jra.east', 'jra.west', 'jra.hokkaido'}


def fetch_public_epg():
    req = urllib.request.Request(PUBLIC_EPG, headers={'User-Agent': 'FreeWiFi-JRA-EPG/1.0', 'Cache-Control': 'no-cache'})
    with urllib.request.urlopen(req, timeout=90) as r:
        return ET.fromstring(r.read())


def main():
    if not GUIDES.exists():
        raise SystemExit('guides.xml not found')

    tree = ET.parse(GUIDES)
    root = tree.getroot()

    # Remove an older generated copy before rebuilding.
    for ch in list(root.findall('channel')):
        if ch.get('id') == TARGET_ID:
            root.remove(ch)
    for p in list(root.findall('programme')):
        if p.get('channel') == TARGET_ID:
            root.remove(p)

    ch = ET.Element('channel', {'id': TARGET_ID})
    ET.SubElement(ch, 'display-name').text = 'JRA公式YouTube'
    root.insert(0, ch)

    src = fetch_public_epg()
    programmes = []
    for p in src.findall('programme'):
        if p.get('channel') not in SOURCE_IDS:
            continue
        q = copy.deepcopy(p)
        q.set('channel', TARGET_ID)
        programmes.append(q)

    # EAST/WEST/HOKKAIDO are independent streams. For the single official
    # YouTube channel, sort every race by its actual EPG start time and keep
    # one programme per start slot. This produces a unified race timeline.
    programmes.sort(key=lambda p: (p.get('start', ''), p.get('stop', '')))
    seen = set()
    added = 0
    for p in programmes:
        title = p.findtext('title') or ''
        key = (p.get('start', ''), title)
        if key in seen:
            continue
        seen.add(key)
        root.append(p)
        added += 1

    ET.indent(tree, space='  ')
    tree.write(GUIDES, encoding='utf-8', xml_declaration=True)
    print(f'JRA official YouTube EPG merged: {added} programmes')


if __name__ == '__main__':
    main()
