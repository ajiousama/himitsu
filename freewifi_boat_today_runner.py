import os
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
print('BOAT playback headers: current STREAKS origin' + (' + API key' if api_key else ''))
raise SystemExit(boat.main())
