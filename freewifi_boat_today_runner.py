import json
import os
from pathlib import Path
import freewifi_boat_today as boat

headers = {
    'User-Agent': boat.UA,
    'Accept': 'application/json',
    'Origin': 'https://players.streaks.jp',
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
raise SystemExit(boat.main())
