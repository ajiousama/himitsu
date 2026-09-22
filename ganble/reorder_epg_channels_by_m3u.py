from pathlib import Path
import re
import xml.etree.ElementTree as ET

M3U = Path('public_sports.m3u')
EPG = Path('epg.xml')
TVG_ID_RE = re.compile(r'tvg-id="([^"]+)"', re.I)


def m3u_channel_order():
    order = []
    seen = set()
    for line in M3U.read_text(encoding='utf-8-sig').splitlines():
        if not line.startswith('#EXTINF:'):
            continue
        m = TVG_ID_RE.search(line)
        if not m:
            continue
        cid = m.group(1).strip()
        if cid and cid not in seen:
            seen.add(cid)
            order.append(cid)
    return order


def main():
    order = m3u_channel_order()
    rank = {cid: i for i, cid in enumerate(order)}

    tree = ET.parse(EPG)
    root = tree.getroot()
    channels = list(root.findall('channel'))

    original_rank = {id(ch): i for i, ch in enumerate(channels)}
    channels.sort(
        key=lambda ch: (
            rank.get((ch.get('id') or '').strip(), 10**9),
            original_rank[id(ch)],
        )
    )

    for ch in list(root.findall('channel')):
        root.remove(ch)

    insert_at = 0
    for ch in channels:
        root.insert(insert_at, ch)
        insert_at += 1

    try:
        ET.indent(tree, space='    ')
    except AttributeError:
        pass

    tree.write(EPG, encoding='utf-8', xml_declaration=True)
    matched = sum(1 for ch in channels if (ch.get('id') or '').strip() in rank)
    print(f'EPG channel order synced to current public_sports.m3u: matched={matched}/{len(channels)}')


if __name__ == '__main__':
    main()
