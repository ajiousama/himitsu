from __future__ import annotations

from datetime import datetime
import os
import urllib.parse

import boat_cloud_resolver as base

# This module keeps base.handle_request / relay logic, but replaces only the
# expensive source-resolution stage. The old resolver could spend tens of
# seconds on three Streaks attempts and a 40-page crawl before reaching JLC.
# Render would then return 502 or the caller would time out. For live BOAT,
# prefer the official JLC live page first and keep every probe bounded.

MAX_ROOT_SECONDS = 4
MAX_CHILD_SECONDS = 4
MAX_CHILDREN = 8
MAX_GRANDCHILDREN = 6


def _fetch_page(url, timeout):
    return base.fetch_text(url, headers=base.upstream_headers(url), timeout=timeout)


def _direct_candidates(raw, final_url):
    return base.m3u8_candidates(raw, final_url)


def _useful_links(raw, final_url, limit):
    links = []
    for url in base.linked_candidates(raw, final_url):
        host = (urllib.parse.urlsplit(url).hostname or '').lower()
        path = urllib.parse.urlsplit(url).path.lower()
        # Prefer player / JLC / BOATCAST / Uliza / Streaks resources. Static
        # assets are already filtered by linked_candidates.
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


def bounded_crawl(roots, label):
    errors = []
    for root in roots:
        if not base.allowed_upstream(root):
            continue
        try:
            raw, final_url, _status = _fetch_page(root, MAX_ROOT_SECONDS)
        except Exception as e:
            errors.append(f'{label}:root:{type(e).__name__}:{getattr(e, "code", "") or e}')
            continue

        direct = _direct_candidates(raw, final_url)
        if direct:
            return direct[0], label, errors

        for child in _useful_links(raw, final_url, MAX_CHILDREN):
            try:
                body, child_final, _status = _fetch_page(child, MAX_CHILD_SECONDS)
            except Exception as e:
                errors.append(f'{label}:child:{urllib.parse.urlsplit(child).path}:{type(e).__name__}:{getattr(e, "code", "") or e}')
                continue
            direct = _direct_candidates(body, child_final)
            if direct:
                return direct[0], label, errors

            # One extra bounded level catches iframe -> player.js/API layouts
            # without the unbounded 40-page crawl that was timing out Render.
            for grand in _useful_links(body, child_final, MAX_GRANDCHILDREN):
                try:
                    gbody, gfinal, _status = _fetch_page(grand, MAX_CHILD_SECONDS)
                except Exception as e:
                    errors.append(f'{label}:grand:{urllib.parse.urlsplit(grand).path}:{type(e).__name__}:{getattr(e, "code", "") or e}')
                    continue
                direct = _direct_candidates(gbody, gfinal)
                if direct:
                    return direct[0], label, errors
    return '', '', errors


def fast_jlc_url(jcd):
    # Search results and BOAT RACE venue pages point to these official JLC URLs.
    # Smartphone live first: it is a narrower page than the desktop shell.
    roots = [
        f'https://livebb.jlc.ne.jp/bb_top/sp_bb/live_{jcd}.php',
        f'https://livebb.jlc.ne.jp/bb_top/new_bb/index.php?tpl={jcd}',
        f'https://live.boatcast.jp/boatcastsp/live_{jcd}.php',
        f'https://live.boatcast.jp/boatcastpc/index.php?tpl={jcd}',
    ]
    return bounded_crawl(roots, 'jlc-fast')


def fast_sakura_url(slug):
    root = f'https://boatrace.sakura.tv/{slug}/'
    return bounded_crawl([root], 'sakura-fast')


def fast_streaks_url(code, ymd):
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
    try:
        data = base.fetch_json(endpoint, headers=headers, timeout=4)
        for item in data.get('sources') or []:
            if isinstance(item, dict):
                src = str(item.get('src') or '').strip()
                if src.startswith(('http://', 'https://')) and base.allowed_upstream(src):
                    return src, 'streaks-fast', errors
    except Exception as e:
        errors.append(f'{type(e).__name__}:{getattr(e, "code", "") or e}')
    return '', '', errors


def fast_resolve(jcd):
    code, tvg_id, slug = base.VENUES[jcd]
    ymd = datetime.now(base.JST).strftime('%Y%m%d')

    # Current direct iPhone seed is fastest and most reliable. The seed file is
    # already pruned daily by the GitHub freshness guard.
    url, source = base.file_fallback(tvg_id, slug)
    if url and source == base.SEED.name:
        return url, source, {'seed': ['current direct seed']}

    # Missing direct seed: go to official JLC first rather than spending 30+ s
    # on Streaks retries that caused Render 502/timeouts.
    url, source, jlc_errors = fast_jlc_url(jcd)
    if url:
        return url, source, {'jlc': jlc_errors}

    # boatrace.sakura.tv exposes the official live link and can reveal alternate
    # player resources when JLC's shell changes.
    url, source, sakura_errors = fast_sakura_url(slug)
    if url:
        return url, source, {'jlc': jlc_errors, 'sakura': sakura_errors}

    # One short Streaks attempt remains as a last dynamic source.
    url, source, streaks_errors = fast_streaks_url(code, ymd)
    if url:
        return url, source, {'jlc': jlc_errors, 'sakura': sakura_errors, 'streaks': streaks_errors}

    # Last-known non-seed fallback (currently official YouTube where configured).
    url, source = base.file_fallback(tvg_id, slug)
    if url:
        return url, source, {'jlc': jlc_errors, 'sakura': sakura_errors, 'streaks': streaks_errors}

    return '', '', {'jlc': jlc_errors, 'sakura': sakura_errors, 'streaks': streaks_errors}


# Patch once at import. All request/relay/security logic remains the proven base
# implementation; only source discovery is replaced.
base.resolve = fast_resolve
handle_request = base.handle_request
