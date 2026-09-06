from __future__ import annotations

from datetime import datetime
import os
import time
import urllib.parse

import boat_cloud_resolver as base

# Keep base.handle_request / relay / allow-list logic, but replace the expensive
# discovery stage. Every /boat/XX resolve now has one absolute deadline so a
# venue can never spend tens of seconds crawling JLC/Streaks and trigger a
# Render 502 before debug probing even begins.
RESOLVE_BUDGET_SECONDS = 8.5
ROOT_TIMEOUT = 2.5
CHILD_TIMEOUT = 1.6
MAX_CHILDREN = 4


def _remaining(deadline, cap):
    left = deadline - time.monotonic()
    if left <= 0.35:
        return 0.0
    return max(0.35, min(float(cap), left - 0.15))


def _fetch_page(url, deadline, cap):
    timeout = _remaining(deadline, cap)
    if timeout <= 0:
        raise TimeoutError('BOAT resolver deadline reached')
    return base.fetch_text(url, headers=base.upstream_headers(url), timeout=timeout)


def _direct_candidates(raw, final_url):
    return base.m3u8_candidates(raw, final_url)


def _useful_links(raw, final_url, limit):
    links = []
    for url in base.linked_candidates(raw, final_url):
        host = (urllib.parse.urlsplit(url).hostname or '').lower()
        path = urllib.parse.urlsplit(url).path.lower()
        priority = (
            'uliza' in host
            or 'streaks' in host
            or host.endswith('.jlc.ne.jp')
            or host.endswith('.boatcast.jp')
            or 'player' in path
            or 'live' in path
            or path.endswith(('.js', '.php', '.html'))
        )
        if priority and url not in links:
            links.append(url)
        if len(links) >= limit:
            break
    return links


def bounded_crawl(roots, label, deadline):
    errors = []
    for root in roots:
        if _remaining(deadline, 1) <= 0:
            errors.append(f'{label}:deadline')
            break
        if not base.allowed_upstream(root):
            continue
        try:
            raw, final_url, _status = _fetch_page(root, deadline, ROOT_TIMEOUT)
        except Exception as e:
            errors.append(f'{label}:root:{type(e).__name__}:{getattr(e, "code", "") or e}')
            continue

        direct = _direct_candidates(raw, final_url)
        if direct:
            return direct[0], label, errors

        # One bounded child level is enough for the common JLC iframe/player-js
        # layout. Do not recurse further: deep crawling was the cause of 502s.
        for child in _useful_links(raw, final_url, MAX_CHILDREN):
            if _remaining(deadline, 1) <= 0:
                errors.append(f'{label}:child-deadline')
                break
            try:
                body, child_final, _status = _fetch_page(child, deadline, CHILD_TIMEOUT)
            except Exception as e:
                errors.append(f'{label}:child:{urllib.parse.urlsplit(child).path}:{type(e).__name__}:{getattr(e, "code", "") or e}')
                continue
            direct = _direct_candidates(body, child_final)
            if direct:
                return direct[0], label, errors
    return '', '', errors


def fast_jlc_url(jcd, deadline):
    # The official JLC smartphone live page exists for each venue and is the
    # narrowest live-only shell, so try it first. BOATCAST mobile is the only
    # alternate root before we move on; desktop shells are deliberately skipped.
    roots = [
        f'https://livebb.jlc.ne.jp/bb_top/sp_bb/live_{jcd}.php',
        f'https://live.boatcast.jp/boatcastsp/live_{jcd}.php',
    ]
    return bounded_crawl(roots, 'jlc-fast', deadline)


def fast_sakura_url(slug, deadline):
    return bounded_crawl([f'https://boatrace.sakura.tv/{slug}/'], 'sakura-fast', deadline)


def fast_streaks_url(code, ymd, deadline):
    endpoint = (
        'https://playback.api.streaks.jp/v1/projects/cp-boatrace-prod/'
        f'medias/ref:lm-br-{code}-tokyo-{ymd}?audio_only=false'
    )
    headers = {
        'User-Agent': base.UA,
        'Accept': 'application/json',
        'Origin': 'https://front.player.boatrace-cdn.jp',
        'Referer': 'https://front.player.boatrace-cdn.jp/',
    }
    api_key = os.getenv('BOATRACE_STREAKS_API_KEY', '').strip()
    if api_key:
        headers['X-Streaks-Api-Key'] = api_key
    errors = []
    timeout = _remaining(deadline, 2.0)
    if timeout <= 0:
        return '', '', ['deadline']
    try:
        data = base.fetch_json(endpoint, headers=headers, timeout=timeout)
        for item in data.get('sources') or []:
            if isinstance(item, dict):
                src = str(item.get('src') or '').strip()
                if src.startswith(('http://', 'https://')) and base.allowed_upstream(src):
                    return src, 'streaks-fast', errors
    except Exception as e:
        errors.append(f'{type(e).__name__}:{getattr(e, "code", "") or e}')
    return '', '', errors


def fast_resolve(jcd):
    deadline = time.monotonic() + RESOLVE_BUDGET_SECONDS
    code, tvg_id, slug = base.VENUES[jcd]
    ymd = datetime.now(base.JST).strftime('%Y%m%d')

    # Current direct iPhone seed remains first and returns immediately.
    url, source = base.file_fallback(tvg_id, slug)
    if url and source == base.SEED.name:
        return url, source, {'seed': ['current direct seed']}

    url, source, jlc_errors = fast_jlc_url(jcd, deadline)
    if url:
        return url, source, {'jlc': jlc_errors}

    # One short Streaks attempt before Sakura. On Render this sometimes succeeds
    # even when the GitHub runner cannot obtain a current-day direct seed.
    url, source, streaks_errors = fast_streaks_url(code, ymd, deadline)
    if url:
        return url, source, {'jlc': jlc_errors, 'streaks': streaks_errors}

    url, source, sakura_errors = fast_sakura_url(slug, deadline)
    if url:
        return url, source, {'jlc': jlc_errors, 'streaks': streaks_errors, 'sakura': sakura_errors}

    # Existing non-seed file fallback (e.g. an official YouTube fallback) is
    # cheap and safe to consult at the end.
    url, source = base.file_fallback(tvg_id, slug)
    if url:
        return url, source, {'jlc': jlc_errors, 'streaks': streaks_errors, 'sakura': sakura_errors}

    return '', '', {
        'jlc': jlc_errors,
        'streaks': streaks_errors,
        'sakura': sakura_errors,
        'deadline_seconds': RESOLVE_BUDGET_SECONDS,
    }


base.resolve = fast_resolve
handle_request = base.handle_request
