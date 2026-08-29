from pathlib import Path
import copy
import urllib.request
import xml.etree.ElementTree as ET

GUIDES = Path('guides.xml')
GREEN_EPG = 'https://animenosekai.github.io/japanterebi-xmltv/guide.xml'
SOURCE_IDS = ('GreenChannel.jp', 'BS234', 'Ch.688')
TARGETS = {
    'jra.official': 'GCH無料版A（YouTube）',
    'jra.gch.free': 'GCH無料版B（グリーンチャンネルWeb）',
}


def fetch_green_epg():
    req = urllib.request.Request(
        GREEN_EPG,
        headers={'User-Agent': 'FreeWiFi-GCH-EPG/1.0', 'Cache-Control': 'no-cache'},
    )
    with urllib.request.urlopen(req, timeout=90) as r:
        return ET.fromstring(r.read())


def find_source_id(root):
    ids = {ch.get('id') for ch in root.findall('channel') if ch.get('id')}
    for source_id in SOURCE_IDS:
        if source_id in ids:
            return source_id
    for ch in root.findall('channel'):
        cid = ch.get('id')
        names = [x.text or '' for x in ch.findall('display-name')]
        if any('グリーンチャンネル' in name for name in names):
            return cid
    return None


def remove_target(root, target_id):
    for ch in list(root.findall('channel')):
        if ch.get('id') == target_id:
            root.remove(ch)
    for p in list(root.findall('programme')):
        if p.get('channel') == target_id:
            root.remove(p)


def main():
    if not GUIDES.exists():
        raise SystemExit('guides.xml not found')

    tree = ET.parse(GUIDES)
    root = tree.getroot()
    src = fetch_green_epg()
    source_id = find_source_id(src)
    if not source_id:
        raise SystemExit('Green Channel EPG source not found')

    source_programmes = [p for p in src.findall('programme') if p.get('channel') == source_id]
    if not source_programmes:
        raise SystemExit(f'No Green Channel programmes found for {source_id}')

    for target_id, display_name in TARGETS.items():
        remove_target(root, target_id)

        ch = ET.Element('channel', {'id': target_id})
        ET.SubElement(ch, 'display-name').text = display_name
        root.insert(0, ch)

        added = 0
        for p in source_programmes:
            q = copy.deepcopy(p)
            q.set('channel', target_id)
            root.append(q)
            added += 1
        print(f'{display_name} EPG synced from {source_id}: {added} programmes')

    ET.indent(tree, space='  ')
    tree.write(GUIDES, encoding='utf-8', xml_declaration=True)


if __name__ == '__main__':
    main()
