import json
import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path

import freewifi_boat_today as boat
import repair_boat_local_epg_openapi

# BOATCAST's playback endpoint accepts the public front-player origin. Keep
# this aligned with the header set used by the player.
headers = {
    'User-Agent': boat.UA,
    'Accept': 'application/json',
    'Origin': 'https://front.player.boatrace-cdn.jp',
    'Referer': 'https://front.player.boatrace-cdn.jp/',
}
api_key = os.getenv('BOATRACE_STREAKS_API_KEY', '').strip()
if api_key:
    headers['X-Streaks-Api-Key'] = api_key
boat.PLAYER_HEADERS = headers

stream_map = {}
p = Path('boat_stream_urls.json')
if p.exists():
    try:
        obj = json.loads(p.read_text(encoding='utf-8-sig'))
        if isinstance(obj, dict):
            stream_map = {str(k): str(v) for k, v in obj.items() if v}
    except Exception as e:
        print('BOAT PowerShell stream map read failed:', e)

original_playback_url = boat.playback_url

def playback_url(code, ymd):
    url = stream_map.get(code, '')
    if url:
        return url, None
    return original_playback_url(code, ymd)

boat.playback_url = playback_url
print(f'BOAT prefetched PowerShell streams: {len(stream_map)}')

# Make sure today's local BOAT grid contains all races. The main generator
# prefers BOAT RACE official pages; when Actions cannot reach them, the helper
# replaces only today's incomplete cards with the current OpenAPI snapshot.
repair_boat_local_epg_openapi.main()

LOCAL_EPG = Path('public_sports_epg_local.xml')
JCD_TO_ID = {jcd: tvg_id for jcd, _name, _code, tvg_id, _slug, _logo in boat.VENUES}
LOCAL_TIMES = {}

if LOCAL_EPG.exists():
    try:
        root = ET.parse(LOCAL_EPG).getroot()
        for jcd, tvg_id in JCD_TO_ID.items():
            races = {}
            for prog in root.findall('programme'):
                if prog.get('channel') != tvg_id:
                    continue
                title = (prog.findtext('title') or '').strip()
                mr = re.search(r'(?:【\s*)?([０-９0-9]{1,2})\s*[ＲR](?:\s*】)?', title)
                mt = re.search(r'([0-9]{1,2}:[0-5][0-9])\s*発走', title)
                if not mr or not mt:
                    continue
                trans = str.maketrans('０１２３４５６７８９', '0123456789')
                try:
                    rno = int(mr.group(1).translate(trans))
                except Exception:
                    continue
                if 1 <= rno <= 12:
                    races[rno] = mt.group(1)
            if races:
                LOCAL_TIMES[jcd] = races
        print('BOAT local EPG schedules:', {jcd: len(races) for jcd, races in LOCAL_TIMES.items()})
    except Exception as e:
        print('BOAT local EPG schedule read failed:', e)


def race_times(jcd, ymd):
    local = LOCAL_TIMES.get(jcd)
    if local:
        return dict(local), None
    return {}, 'local_epg:no_schedule'

boat.race_times = race_times

raise SystemExit(boat.main())
