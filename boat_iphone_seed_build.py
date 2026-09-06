#!/usr/bin/env python3
from __future__ import annotations

import base64
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import urllib.parse

import boat_v2_build as b

STATUS_FILES = [Path('today_boat_status.json'), Path('boat_v2_state.json')]
FREEWIFI = Path('freewifi')
OLD_HEADER = '## 今日の開催場 / BOAT v2 resolver'
NEW_HEADER = '## 今日の開催場 / BOAT iPhone one-click Streaks seed'
JST = timezone(timedelta(hours=9))


def disable_cloud_resolver():
    print('BOAT iPhone seed mode: GitHub/Render Streaks resolver is disabled')
    return False, 0


def jwt_payload(url):
    try:
        token = (urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get('token') or [None])[0]
        if not token or token.count('.') < 2:
            return {}
        payload = token.split('.')[1]
        payload += '=' * (-len(payload) % 4)
        return json.loads(base64.urlsafe_b64decode(payload.encode()).decode('utf-8'))
    except Exception:
        return {}


def seed_started_today(url):
    """Accept only an iPhone-captured Streaks session created for today in JST.

    Streaks tokens can keep an exp time in the future even after the event/session
    itself is no longer usable.  The iPhone one-click intentionally retains old
    venue URLs when a fresh session is not available yet, so `exp` alone is not
    enough to decide that a BOAT URL is playable today.
    """
    payload = jwt_payload(url)
    try:
        start = int(payload.get('start') or 0)
    except Exception:
        start = 0
    if not start:
        return False
    started = datetime.fromtimestamp(start, JST)
    return started.date() == datetime.now(JST).date()


def iphone_streaks_seed_urls():
    # Only accept direct Streaks HLS captured by iPhone Scriptable, and only a
    # session whose JWT `start` belongs to today in JST.  Previous-day retained
    # seeds are archive/fallback data, not a currently playable venue URL.
    urls = ORIGINAL_SEED_URLS()
    out = {}
    stale = []
    for tvg_id, url in urls.items():
        if not (url.startswith('https://manifest.streaks.jp/') and '.m3u8' in url):
            continue
        if seed_started_today(url):
            out[tvg_id] = url
        else:
            stale.append(tvg_id)
    print(f'BOAT iPhone direct Streaks seed: {len(out)} current-JST-date venue URL(s)')
    if stale:
        print('BOAT stale retained seed ignored:', ', '.join(sorted(stale)))
    return out


def normalize_status():
    for path in STATUS_FILES:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding='utf-8'))
        data['system'] = 'boat-v2-iphone-seed'
        data['stream_source'] = 'boat_stream_seed.m3u from iPhone Scriptable one-click / direct Streaks only'
        data['seed_freshness_rule'] = 'JWT start date must equal current JST date'
        data['resolver_ready'] = False
        data['resolver_probe_status'] = 0
        data.pop('resolver_base', None)
        for item in (data.get('venues') or {}).values():
            url = item.get('url') or ''
            if url.startswith('https://manifest.streaks.jp/'):
                item['source'] = 'iPhone one-click direct Streaks seed (current JST date)'
            elif item.get('stream_window') in {'live_or_vtr', 'epg_ready'}:
                item['visible'] = False
                item.pop('url', None)
                item['source'] = 'iPhone direct Streaks seed pending, expired, or retained from another JST date'
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    if FREEWIFI.exists():
        text = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
        text = text.replace(OLD_HEADER, NEW_HEADER)
        text = text.replace('## 今日の開催場 / BOAT iPhone one-click seed', NEW_HEADER)
        FREEWIFI.write_text(text.rstrip() + '\n', encoding='utf-8')


def main():
    # Reuse the established schedule/window/freewifi builder, but force it to
    # consume only direct Streaks URLs already stored in boat_stream_seed.m3u.
    # No GitHub runner or Render service is allowed to resolve Streaks itself.
    b.resolver_ready = disable_cloud_resolver
    b.seed_urls = iphone_streaks_seed_urls
    rc = b.main()
    normalize_status()
    return rc


ORIGINAL_SEED_URLS = b.seed_urls


if __name__ == '__main__':
    raise SystemExit(main())
