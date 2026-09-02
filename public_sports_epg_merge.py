from pathlib import Path
from datetime import datetime, timezone, timedelta
import json
import re
import xml.etree.ElementTree as ET

GUIDES = Path('guides.xml')
LOCAL_EPG = Path('public_sports_epg_local.xml')
STATUS_JSON = Path('today_public_sports_status.json')
VERIFIED_JSON = Path('verified_daily_status.json')
PREFIXES = ('keirin.', 'chihou.', 'boat.', 'auto.')
JST = timezone(timedelta(hours=9))
FULLWIDTH = str.maketrans('0123456789', '０１２３４５６７８９')


def load_json(path):
    try: return json.loads(path.read_text(encoding='utf-8-sig'))
    except Exception: return {}


def wanted_ids():
    status = load_json(STATUS_JSON).get('channels', {})
    ids = {cid for cid in status if cid.startswith(PREFIXES)}
    cfg = load_json(VERIFIED_JSON)
    if cfg.get('date') == datetime.now(JST).date().isoformat():
        for section in ('競輪','地方競馬','ボートレース','オートレース'):
            pass
    if ids: return ids
    if not LOCAL_EPG.exists(): return set()
    root = ET.parse(LOCAL_EPG).getroot(); today = datetime.now(JST).strftime('%Y%m%d')
    return {p.get('channel') for p in root.findall('programme') if (p.get('channel') or '').startswith(PREFIXES) and (p.get('start') or '').startswith(today)}


def normalize_title(p):
    t = p.find('title')
    if t is None or not (t.text or '').strip(): return
    text = t.text.strip().translate(str.maketrans('０１２３４５６７８９Ｒ','0123456789R'))
    m = re.search(r'(?:【\s*)?(1[0-2]|[1-9])\s*R(?:\s*】)?', text)
    if not m: return
    n = int(m.group(1)); marker = f'【{str(n).translate(FULLWIDTH)}Ｒ】'
    tm = re.search(r'([0-2]?\d:[0-5]\d)\s*発走', text)
    original = (t.text or '').strip()
    rest = re.sub(r'^(?:【\s*)?[０-９0-9]{1,2}\s*[ＲR](?:\s*】)?\s*', '', original, count=1).strip()
    if tm:
        rest = re.sub(rf'^\s*{re.escape(tm.group(1))}\s*発走\s*', '', rest).strip()
        t.text = f'{marker} {tm.group(1)}発走' + (f'  {rest}' if rest else '')
    else:
        t.text = marker + (f'  {rest}' if rest else '')


def main():
    if not GUIDES.exists() or not LOCAL_EPG.exists(): raise SystemExit('guides/local public EPG missing')
    wanted = wanted_ids()
    if not wanted: raise SystemExit('Public sports EPG: no active local channels')
    dst = ET.parse(GUIDES); root = dst.getroot(); src = ET.parse(LOCAL_EPG).getroot()
    for el in list(root):
        cid = el.get('id') if el.tag == 'channel' else el.get('channel') if el.tag == 'programme' else ''
        if cid and cid.startswith(PREFIXES): root.remove(el)
    channels = {c.get('id'):c for c in src.findall('channel') if c.get('id') in wanted}
    progs = {}
    for p in src.findall('programme'):
        cid = p.get('channel')
        if cid in wanted: progs.setdefault(cid, []).append(p)
    missing=[]; pc=0
    for cid in sorted(wanted):
        if cid not in channels or not progs.get(cid): missing.append(cid); continue
        root.append(ET.fromstring(ET.tostring(channels[cid], encoding='utf-8')))
        for p in progs[cid]:
            cp = ET.fromstring(ET.tostring(p, encoding='utf-8')); normalize_title(cp); root.append(cp); pc += 1
    if missing: raise SystemExit(f'Local public sports EPG missing active channels: {missing}')
    ET.indent(dst, space='  '); dst.write(GUIDES, encoding='utf-8', xml_declaration=True)
    print(f'Public sports LOCAL EPG merged: channels={len(wanted)} programmes={pc}')

if __name__ == '__main__': main()
