"""Reapply the BOAT-owned blocks to the latest shared files.

When run as a command by the continuous worker, also refresh the short-lived
GameCenter CX2 KICK playback URL before publishing the BOAT-owned blocks.
"""
import json
import re
import subprocess
import xml.etree.ElementTree as ET
import boat_auto_system as boat


def refresh_cx2():
    try:
        result = subprocess.run(['python', 'kick_gccx2_sync.py'], timeout=60)
        if result.returncode != 0:
            print(f'::warning::CX2 KICK refresh exited {result.returncode}; keeping current entry')
    except Exception as exc:
        print(f'::warning::CX2 KICK refresh failed: {type(exc).__name__}; keeping current entry')


def overlay_state(epg_only=False):
    state = boat.json_read(boat.STATE)
    now = boat.now_jst()
    if state.get('date') != now.date().isoformat():
        raise RuntimeError('refuse previous-day BOAT state')
    cards = boat.cached_cards(state, now.date())
    cancelled = {str(jcd).zfill(2) for jcd in (state.get('cancelled_jcd') or [])}
    venues, rows, _ = boat.build_venue_state(cards, state.get('streams') or {}, now, cancelled)
    if not epg_only:
        boat.update_playlist(rows)
    for path in (boat.LOCAL_EPG, boat.GUIDES):
        if path.exists():
            boat.overlay_epg_file(path, cards, now.date(), cancelled)
    validate(state, cards)


def validate(state=None, cards=None):
    state = state or boat.json_read(boat.STATE)
    day = boat.now_jst().date()
    cards = cards if cards is not None else boat.cached_cards(state, day)
    if state.get('date') != day.isoformat():
        raise RuntimeError('stale BOAT status')
    text = boat.FREEWIFI.read_text(encoding='utf-8-sig')
    ids = re.findall(r'^#EXTINF:.*?tvg-id="(boat\.[^"]+)"', text, re.M)
    if len(ids) != len(set(ids)):
        raise RuntimeError('duplicate BOAT playlist channel')
    if len(ids) != state.get('visible_count'):
        raise RuntimeError('BOAT playlist/status count mismatch')
    urls = boat.managed_playlist_urls()
    if len(set(urls.values())) != len(urls):
        raise RuntimeError('same stream assigned to multiple venues')
    if any(not boat.current_day_stream(url, day) for url in urls.values()):
        raise RuntimeError('previous-day or non-BOAT stream rejected')
    for path in (boat.LOCAL_EPG, boat.GUIDES):
        root = ET.parse(path).getroot()
        cancelled = {str(jcd).zfill(2) for jcd in (state.get('cancelled_jcd') or [])}
        for jcd, races in cards.items():
            cid = boat.VENUES[jcd][1]
            programmes = sorted((p for p in root.findall('programme')
                                 if p.get('channel') == cid and p.get('start', '').startswith(day.strftime('%Y%m%d'))),
                                key=lambda p: p.get('start'))
            titles = [p.findtext('title', '') for p in programmes]
            if jcd in cancelled:
                if titles != ['本日の開催は中止になりました']:
                    raise RuntimeError(f'{path}: cancellation EPG missing: {cid}')
                continue
            if sum('発走' in title for title in titles) != len(races):
                raise RuntimeError(f'{path}: missing/duplicate races: {cid}')
            if any(a.get('stop') > b.get('start') for a, b in zip(programmes, programmes[1:])):
                raise RuntimeError(f'{path}: overlapping EPG: {cid}')
    print(f'BOAT output validated: venues={len(cards)} visible={len(ids)}')


if __name__ == '__main__':
    import sys
    refresh_cx2()
    overlay_state(epg_only='--epg-only' in sys.argv)
