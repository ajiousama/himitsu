from copy import deepcopy
from pathlib import Path
import datetime
import re
import xml.etree.ElementTree as ET

EPG = Path(__file__).resolve().parent / 'epg.xml'
JRA_PREFIX = 'jra.'
XMLTV_RE = re.compile(r'^(\d{14})(?:\s+([+-]\d{4}))?$')
NEAR_DUPLICATE_SECONDS = 10


def parse_xmltv(value):
    m = XMLTV_RE.match(str(value or '').strip())
    if not m:
        return None, None
    digits, offset = m.groups()
    if offset:
        dt = datetime.datetime.strptime(f'{digits} {offset}', '%Y%m%d%H%M%S %z')
    else:
        dt = datetime.datetime.strptime(digits, '%Y%m%d%H%M%S')
    return dt, offset


def format_xmltv(dt, offset):
    digits = dt.strftime('%Y%m%d%H%M%S')
    return f'{digits} {offset}' if offset else digits


def child_signature(node):
    return (
        node.tag,
        tuple(sorted(node.attrib.items())),
        (node.text or '').strip(),
        tuple(child_signature(c) for c in list(node)),
    )


def programme_signature(prog):
    return (
        tuple(sorted(prog.attrib.items())),
        tuple(child_signature(c) for c in list(prog)),
    )


def merge_missing_children(dst, src):
    existing = {child_signature(c) for c in list(dst)}
    for child in list(src):
        sig = child_signature(child)
        if child.tag == 'title':
            continue
        if sig not in existing:
            dst.append(deepcopy(child))
            existing.add(sig)


def main():
    if not EPG.exists():
        raise SystemExit('epg.xml not found')

    tree = ET.parse(EPG)
    root = tree.getroot()
    repaired = 0
    exact_removed = 0
    near_merged = 0

    # Repair malformed JRA stop times. If the source carries yesterday's date
    # or an overnight stop without the next date, move stop forward by days.
    for prog in root.findall('programme'):
        if not prog.get('channel', '').startswith(JRA_PREFIX):
            continue
        start, _ = parse_xmltv(prog.get('start'))
        stop, stop_offset = parse_xmltv(prog.get('stop'))
        if start is None or stop is None:
            continue
        if stop <= start:
            for _ in range(3):
                stop += datetime.timedelta(days=1)
                if stop > start:
                    break
            if stop <= start:
                raise SystemExit(f'Unable to repair JRA time: {prog.attrib}')
            prog.set('stop', format_xmltv(stop, stop_offset))
            repaired += 1

    # Remove byte-for-byte semantic duplicates after time repair.
    seen = set()
    for prog in list(root.findall('programme')):
        if not prog.get('channel', '').startswith(JRA_PREFIX):
            continue
        sig = programme_signature(prog)
        if sig in seen:
            root.remove(prog)
            exact_removed += 1
        else:
            seen.add(sig)

    # Some GCH sources describe the same programme twice with a 4-second
    # offset: one entry has description/category and the other has an image.
    # Merge those into one programme and retain all useful child metadata.
    by_title = {}
    for prog in list(root.findall('programme')):
        channel = prog.get('channel', '')
        if not channel.startswith(JRA_PREFIX):
            continue
        title = (prog.findtext('title') or '').strip()
        start, _ = parse_xmltv(prog.get('start'))
        stop, _ = parse_xmltv(prog.get('stop'))
        if not title or start is None or stop is None:
            continue

        key = (channel, title)
        match = None
        for keeper, kstart, kstop in reversed(by_title.get(key, [])[-6:]):
            if (
                abs((start - kstart).total_seconds()) <= NEAR_DUPLICATE_SECONDS
                and abs((stop - kstop).total_seconds()) <= NEAR_DUPLICATE_SECONDS
            ):
                match = keeper
                break

        if match is not None:
            merge_missing_children(match, prog)
            root.remove(prog)
            near_merged += 1
        else:
            by_title.setdefault(key, []).append((prog, start, stop))

    # Final safety check: no JRA programme may finish before it starts.
    invalid = []
    for prog in root.findall('programme'):
        if not prog.get('channel', '').startswith(JRA_PREFIX):
            continue
        start, _ = parse_xmltv(prog.get('start'))
        stop, _ = parse_xmltv(prog.get('stop'))
        if start is not None and stop is not None and stop <= start:
            invalid.append(prog.attrib)
    if invalid:
        raise SystemExit(f'Invalid JRA programme times remain: {invalid[:3]}')

    ET.indent(tree, space='  ')
    tree.write(EPG, encoding='utf-8', xml_declaration=True)
    print(
        'JRA EPG sanitized: '
        f'exact_removed={exact_removed} near_merged={near_merged} time_repaired={repaired}'
    )


if __name__ == '__main__':
    main()
