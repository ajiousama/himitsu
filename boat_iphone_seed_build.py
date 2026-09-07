#!/usr/bin/env python3
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import urllib.error
import urllib.parse
import urllib.request

import boat_v2_build as b

STATUS_FILES = [Path('today_boat_status.json'), Path('boat_v2_state.json')]
FREEWIFI = Path('freewifi')
OLD_HEADER = '## 今日の開催場 / BOAT v2 resolver'
NEW_HEADER = '## 今日の開催場 / BOAT current-day verified hybrid'
JST = timezone(timedelta(hours=9))
RENDER_PREFIX = b.RESOLVER_BASE.rstrip('/') + '/'
PROBE_DIAGNOSTICS = {}
RETRY_RESOLVER_IDS = set()


def disable_global_cloud_resolver():
    # Never let boat_v2_build blindly publish the same resolver pattern for all
    # venues. We inject verified routes per venue, plus a tightly scoped night
    # retry route only after that venue's display window has opened.
    print('BOAT global resolver disabled; verified fallback + night-window retry only')
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
    """Accept only a Streaks session whose JWT `start` is today in JST."""
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


def compact_debug(data, http_status):
    """Keep enough resolver detail to diagnose failures without bloating status."""
    if not isinstance(data, dict):
        return {'http_status': http_status, 'parse_error': True}
    out = {
        'http_status': http_status,
        'ok': bool(data.get('ok')),
        'playable': bool(data.get('playable')),
        'source': str(data.get('source') or ''),
    }
    probe = data.get('probe')
    if isinstance(probe, dict):
        out['probe'] = {
            k: probe.get(k)
            for k in ('status', 'content_type', 'playlist', 'error')
            if probe.get(k) not in (None, '')
        }
    details = data.get('details')
    if isinstance(details, dict):
        compact = {}
        for key in ('streaks', 'jlc', 'sakura'):
            value = details.get(key)
            if isinstance(value, list):
                compact[key] = [str(x)[:240] for x in value[-4:]]
            elif value not in (None, '', []):
                compact[key] = str(value)[:500]
        if compact:
            out['details'] = compact
    return out


def probe_verified_resolver(jcd):
    endpoint = f'{RENDER_PREFIX}{jcd}'
    debug = endpoint + '?debug=1'
    req = urllib.request.Request(
        debug,
        headers={'User-Agent': b.UA, 'Accept': 'application/json', 'Cache-Control': 'no-cache'},
    )
    raw = b''
    status = 0
    try:
        with urllib.request.urlopen(req, timeout=35) as r:
            status = int(getattr(r, 'status', 200))
            raw = r.read()
    except urllib.error.HTTPError as e:
        status = int(e.code)
        try:
            raw = e.read()
        except Exception:
            raw = b''
    except Exception as e:
        diag = {'http_status': 0, 'transport_error': f'{type(e).__name__}:{e}'}
        return '', '', f'{type(e).__name__}:{e}', diag

    try:
        data = json.loads(raw.decode('utf-8', 'replace')) if raw else {}
    except Exception as e:
        data = {}
        diag = {'http_status': status, 'parse_error': f'{type(e).__name__}:{e}', 'body': raw[:300].decode('utf-8', 'replace')}
        return '', '', f'HTTP {status} invalid debug JSON', diag

    diag = compact_debug(data, status)
    if status == 200 and data.get('ok') is True and data.get('playable') is True:
        return endpoint, str(data.get('source') or 'resolver'), '', diag
    detail = data.get('probe') or data.get('details') or {}
    return '', '', f'HTTP {status} playable={data.get("playable")} detail={detail}', diag


def night_retry_window_open(races):
    if not races or b.mode(races) != 'night':
        return False
    now = datetime.now(JST)
    show_from = races[0][1] - timedelta(minutes=b.PRESTART_MINUTES)
    remove_after = races[-1][1] + timedelta(minutes=b.GRACE_MINUTES)
    activation_now = now + timedelta(seconds=b.START_TOLERANCE_SECONDS)
    return show_from <= activation_now and now < remove_after


def verified_effective_urls():
    direct = iphone_streaks_seed_urls()
    out = dict(direct)
    day = datetime.now(JST).date()
    PROBE_DIAGNOSTICS.clear()
    RETRY_RESOLVER_IDS.clear()

    try:
        cards = b.cards_from_snapshot(b.fetch_snapshot(day), day)
    except Exception as e:
        print(f'BOAT verified resolver schedule lookup failed: {type(e).__name__}: {e}')
        PROBE_DIAGNOSTICS['_schedule'] = {'error': f'{type(e).__name__}:{e}'}
        return out

    targets = []
    for jcd in sorted(cards):
        _name, tvg_id, _logo = b.VENUES[jcd]
        if tvg_id not in out:
            targets.append(jcd)

    if not targets:
        print('BOAT verified resolver: no missing held venue needs fallback')
        return out

    print('BOAT verified resolver probing:', ', '.join(targets))
    verified = 0
    retry = 0
    with ThreadPoolExecutor(max_workers=min(4, len(targets))) as pool:
        futures = {pool.submit(probe_verified_resolver, jcd): jcd for jcd in targets}
        for future in as_completed(futures):
            jcd = futures[future]
            name, tvg_id, _logo = b.VENUES[jcd]
            try:
                endpoint, source, error, diag = future.result()
            except Exception as e:
                endpoint, source, error, diag = '', '', f'{type(e).__name__}:{e}', {'worker_error': f'{type(e).__name__}:{e}'}
            PROBE_DIAGNOSTICS[tvg_id] = {'jcd': jcd, 'name': name, **diag}
            if endpoint:
                out[tvg_id] = endpoint
                verified += 1
                print(f'BOAT {name}: verified resolver playable source={source}')
            elif night_retry_window_open(cards.get(jcd) or []):
                # Night venues must appear automatically when their display
                # window opens. Publish the stable per-venue Render endpoint so
                # an actual player request can retry upstream discovery even if
                # the scheduled preflight happened during a temporary 403/503.
                out[tvg_id] = f'{RENDER_PREFIX}{jcd}'
                RETRY_RESOLVER_IDS.add(tvg_id)
                PROBE_DIAGNOSTICS[tvg_id]['retry_enabled'] = True
                retry += 1
                print(f'BOAT {name}: night on-demand resolver retry enabled after preflight miss: {error}')
            else:
                print(f'BOAT {name}: resolver not playable: {error}')

    print(f'BOAT verified resolver fallback: {verified}/{len(targets)} missing held venue(s) playable; night retry={retry}')
    return out


def normalize_status():
    for path in STATUS_FILES:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding='utf-8'))
        data['system'] = 'boat-v2-iphone-seed'
        data['stream_source'] = 'current-JST-date iPhone direct Streaks + verified per-venue Render resolver + night-window on-demand retry'
        data['seed_freshness_rule'] = 'JWT start date must equal current JST date'
        data['resolver_ready'] = False
        data['resolver_probe_status'] = 0
        data['verified_resolver_base'] = b.RESOLVER_BASE
        data['resolver_diagnostics'] = PROBE_DIAGNOSTICS
        data.pop('resolver_base', None)
        verified_count = 0
        retry_count = 0
        for tvg_id, item in (data.get('venues') or {}).items():
            url = item.get('url') or ''
            if url.startswith('https://manifest.streaks.jp/'):
                item['source'] = 'iPhone one-click direct Streaks seed (current JST date)'
                item.pop('verified_resolver', None)
                item.pop('resolver_retry', None)
            elif url.startswith(RENDER_PREFIX):
                if tvg_id in RETRY_RESOLVER_IDS:
                    item['source'] = 'Render BOAT resolver (night on-demand retry)'
                    item['resolver_retry'] = True
                    item.pop('verified_resolver', None)
                    retry_count += 1
                else:
                    item['source'] = 'verified Render BOAT resolver (debug playable=true)'
                    item['verified_resolver'] = True
                    item.pop('resolver_retry', None)
                    verified_count += 1
            elif item.get('stream_window') in {'live_or_vtr', 'epg_ready'}:
                item['visible'] = False
                item.pop('url', None)
                item.pop('verified_resolver', None)
                item.pop('resolver_retry', None)
                item['source'] = 'current-day direct seed unavailable and resolver not verified playable'
            if tvg_id in PROBE_DIAGNOSTICS:
                item['resolver_debug'] = PROBE_DIAGNOSTICS[tvg_id]
        data['verified_resolver_count'] = verified_count
        data['resolver_retry_count'] = retry_count
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    if FREEWIFI.exists():
        text = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
        text = text.replace(OLD_HEADER, NEW_HEADER)
        text = text.replace('## 今日の開催場 / BOAT iPhone one-click seed', NEW_HEADER)
        text = text.replace('## 今日の開催場 / BOAT iPhone one-click Streaks seed', NEW_HEADER)
        FREEWIFI.write_text(text.rstrip() + '\n', encoding='utf-8')


def main():
    # Keep blanket resolver publishing disabled. b.main receives a synthetic
    # mapping of current-day direct Streaks URLs, verified resolver routes, and
    # night-only retry routes after the venue's display window opens.
    b.resolver_ready = disable_global_cloud_resolver
    b.seed_urls = verified_effective_urls
    rc = b.main()
    normalize_status()
    return rc


ORIGINAL_SEED_URLS = b.seed_urls


if __name__ == '__main__':
    raise SystemExit(main())
