#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

import boat_v2_build as b

STATUS_FILES = [Path('today_boat_status.json'), Path('boat_v2_state.json')]
FREEWIFI = Path('freewifi')
OLD_HEADER = '## 今日の開催場 / BOAT v2 resolver'
NEW_HEADER = '## 今日の開催場 / BOAT iPhone one-click Streaks seed'


def disable_cloud_resolver():
    print('BOAT iPhone seed mode: GitHub/Render Streaks resolver is disabled')
    return False, 0


def iphone_streaks_seed_urls():
    # Only accept the direct Streaks HLS captured by iPhone Scriptable.
    # Legacy YouTube/googlevideo or resolver URLs are intentionally ignored.
    urls = ORIGINAL_SEED_URLS()
    out = {}
    for tvg_id, url in urls.items():
        if url.startswith('https://manifest.streaks.jp/') and '.m3u8' in url:
            out[tvg_id] = url
    print(f'BOAT iPhone direct Streaks seed: {len(out)} valid venue URL(s)')
    return out


def normalize_status():
    for path in STATUS_FILES:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding='utf-8'))
        data['system'] = 'boat-v2-iphone-seed'
        data['stream_source'] = 'boat_stream_seed.m3u from iPhone Scriptable one-click / direct Streaks only'
        data['resolver_ready'] = False
        data['resolver_probe_status'] = 0
        data.pop('resolver_base', None)
        for item in (data.get('venues') or {}).values():
            url = item.get('url') or ''
            if url.startswith('https://manifest.streaks.jp/'):
                item['source'] = 'iPhone one-click direct Streaks seed'
            elif item.get('stream_window') == 'live_or_vtr':
                item['visible'] = False
                item.pop('url', None)
                item['source'] = 'iPhone direct Streaks seed missing or expired'
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
