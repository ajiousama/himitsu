#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import boat_v2_build as b

STATUS_FILES = [Path('today_boat_status.json'), Path('boat_v2_state.json')]
FREEWIFI = Path('freewifi')
OLD_HEADER = '## 今日の開催場 / BOAT v2 resolver'
NEW_HEADER = '## 今日の開催場 / BOAT iPhone one-click seed'


def disable_cloud_resolver():
    print('BOAT iPhone seed mode: GitHub/Render Streaks resolver is disabled')
    return False, 0


def normalize_status():
    for path in STATUS_FILES:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding='utf-8'))
        data['system'] = 'boat-v2-iphone-seed'
        data['stream_source'] = 'boat_stream_seed.m3u from iPhone Scriptable one-click'
        data['resolver_ready'] = False
        data['resolver_probe_status'] = 0
        data.pop('resolver_base', None)
        for item in (data.get('venues') or {}).values():
            if item.get('url'):
                item['source'] = 'iPhone one-click seed'
            elif item.get('stream_window') == 'live_or_vtr':
                item['source'] = 'iPhone one-click seed missing or expired'
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    if FREEWIFI.exists():
        text = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
        text = text.replace(OLD_HEADER, NEW_HEADER)
        FREEWIFI.write_text(text.rstrip() + '\n', encoding='utf-8')


def main():
    # Reuse the established schedule/window/freewifi builder, but force it to
    # consume boat_stream_seed.m3u directly. This intentionally prevents any
    # GitHub runner or Render service from resolving Streaks playback URLs.
    b.resolver_ready = disable_cloud_resolver
    rc = b.main()
    normalize_status()
    return rc


if __name__ == '__main__':
    raise SystemExit(main())
