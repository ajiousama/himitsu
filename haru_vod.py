#!/usr/bin/env python3
from __future__ import annotations

import argparse, concurrent.futures, gzip, html, json, re, sys, unicodedata
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

JST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "haru_favorites.json"
OUT_JSON = ROOT / "haru_vod.json"
OUT_M3U = ROOT / "haru_vod.m3u"
REPLAY_RE = re.compile(r'<!--\s*(https://haru\.charandom\.blog/stream/jp/[^\s<]+?replay\.m3u8\?[^<]*?start=\d+)\s*-->\s*<programme\b([^>]*)>(.*?)</programme>', re.S | re.I)
TITLE_RE = re.compile(r'<title(?:\s+[^>]*)?>(.*?)</title>', re.S | re.I)
ATTR_RE = re.compile(r'([\w:-]+)="([^"]*)"')
EP_RE = re.compile(r'#\s*(\d+)')

@dataclass
class Item:
    favorite_id: str
    display: str
    title: str
    channel: str
    start_raw: str
    stop_raw: str
    start_jst: str
    stop_jst: str
    replay_url: str
    logo: str
    probe: str = "unknown"

def norm(s: str) -> str:
    return unicodedata.normalize("NFKC", html.unescape(s or "")).strip()

def strip_xml(s: str) -> str:
    return html.unescape(re.sub(r'<[^>]+>', '', s or '')).strip()

def xmltv_dt(s: str) -> datetime:
    m = re.match(r'^(\d{14})\s*([+-]\d{4})$', (s or '').strip())
    if not m:
        raise ValueError(s)
    return datetime.strptime(f'{m.group(1)} {m.group(2)}', '%Y%m%d%H%M%S %z')

def idna_url(url: str) -> str:
    p = urlsplit(url)
    if not p.hostname:
        return url
    try:
        host = p.hostname.encode('idna').decode('ascii')
    except Exception:
        return url
    port = f':{p.port}' if p.port else ''
    return urlunsplit((p.scheme, host + port, p.path, p.query, p.fragment))

def get_bytes(url: str, timeout=18, limit=32_000_000) -> bytes:
    req = Request(idna_url(url), headers={
        'User-Agent': 'Mozilla/5.0 HARU-VOD/1.0',
        'Accept': 'application/xml,text/xml,application/vnd.apple.mpegurl,application/x-mpegURL,*/*',
        'Accept-Encoding': 'gzip'
    })
    with urlopen(req, timeout=timeout) as r:
        data = r.read(limit + 1)
        if len(data) > limit:
            raise RuntimeError('download too large')
        if (r.headers.get('Content-Encoding') or '').lower() == 'gzip' or url.lower().endswith('.gz'):
            try: data = gzip.decompress(data)
            except OSError: pass
        return data

def discover_source(url: str) -> str | None:
    if not url:
        return None
    try:
        text = get_bytes(url, timeout=12, limit=2_000_000).decode('utf-8', 'replace')
        m = re.search(r'url-tvg="([^"]*kai-epg[^"]*)"', '\n'.join(text.splitlines()[:5]), re.I)
        return html.unescape(m.group(1).strip()) if m else None
    except Exception as e:
        print('[HARU VOD] discovery failed:', e, file=sys.stderr)
        return None

def fetch_epg(cfg: dict) -> tuple[bytes, str]:
    sources = list(cfg.get('epg_sources') or [])
    d = discover_source(cfg.get('discovery_playlist') or '')
    if d and d not in sources:
        sources.insert(0, d)
    errors = []
    for url in sources:
        try:
            print('[HARU VOD] trying EPG:', url)
            data = get_bytes(url)
            if b'haru.charandom.blog/stream/jp/' not in data:
                raise RuntimeError('no HARU replay comments')
            print(f'[HARU VOD] EPG OK: {len(data):,} bytes')
            return data, url
        except Exception as e:
            errors.append(f'{url}: {e}')
            print('[HARU VOD] EPG failed:', url, e, file=sys.stderr)
    raise RuntimeError('no HARU replay-capable EPG source\n' + '\n'.join(errors))

def pref_rank(fav: dict, channel: str) -> int:
    try: return (fav.get('preferred_channels') or []).index(channel)
    except ValueError: return 999

def candidates(xml: bytes, cfg: dict, now: datetime) -> list[Item]:
    rules = [(f, [re.compile(p, re.I) for p in f.get('patterns', [])]) for f in cfg.get('favorites', [])]
    max_age = timedelta(days=int(cfg.get('max_age_days', 14)))
    chosen = {}
    text = xml.decode('utf-8', 'replace')
    for m in REPLAY_RE.finditer(text):
        url, attrtxt, body = m.groups()
        attrs = dict(ATTR_RE.findall(attrtxt))
        tm = TITLE_RE.search(body)
        if not tm: continue
        title = strip_xml(tm.group(1)); nt = norm(title)
        try:
            st = xmltv_dt(attrs.get('start', '')); sp = xmltv_dt(attrs.get('stop', ''))
        except Exception:
            continue
        sj, ej = st.astimezone(JST), sp.astimezone(JST)
        if ej > now or now - ej > max_age:
            continue
        ch = attrs.get('channel', '')
        for fav, pats in rules:
            if not any(p.search(nt) for p in pats):
                continue
            it = Item(fav['id'], fav['display'], title, ch, attrs.get('start',''), attrs.get('stop',''), sj.isoformat(timespec='seconds'), ej.isoformat(timespec='seconds'), url, fav.get('logo',''))
            key = (fav['id'], sj.isoformat())
            rank = pref_rank(fav, ch)
            if key not in chosen or rank < chosen[key][0]:
                chosen[key] = (rank, it)
            break
    return [x[1] for x in chosen.values()]

def kick_gccx_numbers() -> set[str]:
    p = ROOT / 'kick_replay.m3u'
    if not p.exists(): return set()
    nums = set()
    for line in norm(p.read_text('utf-8', errors='replace')).splitlines():
        if 'ゲームセンターCX' in line:
            nums.update(EP_RE.findall(line))
    return nums

def dedupe_kick(items: list[Item], cfg: dict) -> list[Item]:
    nums = kick_gccx_numbers()
    enabled = {f['id'] for f in cfg.get('favorites', []) if f.get('dedupe_kick_episode_numbers')}
    out = []
    for it in items:
        m = EP_RE.search(norm(it.title))
        if it.favorite_id in enabled and m and m.group(1) in nums:
            print('[HARU VOD] KICK duplicate suppressed:', it.title)
            continue
        out.append(it)
    return out

def probe(url: str, timeout=9) -> tuple[bool, str]:
    req = Request(idna_url(url), headers={'User-Agent':'Mozilla/5.0 HARU-VOD/1.0','Accept':'application/vnd.apple.mpegurl,application/x-mpegURL,*/*','Range':'bytes=0-8191'})
    try:
        with urlopen(req, timeout=timeout) as r:
            text = r.read(8192).decode('utf-8', 'replace')
            return (True, f'ok:{r.status}') if r.status < 400 and '#EXTM3U' in text else (False, f'bad_playlist:{r.status}')
    except HTTPError as e: return False, f'http:{e.code}'
    except URLError as e: return False, f'network:{getattr(e, "reason", e)}'
    except Exception as e: return False, f'error:{type(e).__name__}:{e}'

def probe_all(items: list[Item], workers=4) -> tuple[list[Item], dict]:
    by_url = {}
    for it in items: by_url.setdefault(it.replay_url, []).append(it)
    ok_items, stats = [], {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as ex:
        futures = {ex.submit(probe, u): u for u in by_url}
        for f in concurrent.futures.as_completed(futures):
            url = futures[f]; ok, status = f.result(); key = status.split(':',1)[0]
            stats[key] = stats.get(key, 0) + 1
            for it in by_url[url]:
                it.probe = status
                if ok: ok_items.append(it)
    return ok_items, stats

def limit_items(items: list[Item], cfg: dict) -> list[Item]:
    limit = int(cfg.get('max_per_program', 12)); grouped = {}
    for it in items: grouped.setdefault(it.favorite_id, []).append(it)
    out = []
    for fav in cfg.get('favorites', []):
        arr = sorted(grouped.get(fav['id'], []), key=lambda x:x.start_jst, reverse=True)
        out += arr[:limit]
    return out

def label(it: Item) -> str:
    dt = datetime.fromisoformat(it.start_jst); ep = EP_RE.search(norm(it.title))
    return f'{it.display} #{ep.group(1)} {dt:%m/%d}' if ep else f'{it.display} {dt:%m/%d %H:%M}'

def esc(s: str) -> str:
    return (s or '').replace('"', "'").replace('\r',' ').replace('\n',' ')

def write(items: list[Item], cfg: dict, source: str, probed: bool, now: datetime):
    payload = {'generated_at':now.isoformat(timespec='seconds'),'source':source,'probed':probed,'count':len(items),'favorites':[f['display'] for f in cfg.get('favorites',[])],'items':[asdict(x) for x in items]}
    OUT_JSON.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+'\n', 'utf-8')
    lines = ['#EXTM3U', f'# HARU VOD generated {now.isoformat(timespec="seconds")} source={source}']
    group = cfg.get('group_title','HARU VOD')
    for it in items:
        tvgid = f'haru.vod.{it.favorite_id}.{int(datetime.fromisoformat(it.start_jst).timestamp())}'
        lines.append(f'#EXTINF:-1 tvg-id="{esc(tvgid)}" tvg-logo="{esc(it.logo)}" group-title="{esc(group)}",{esc(label(it))}')
        lines.append(it.replay_url)
    OUT_M3U.write_text('\n'.join(lines)+'\n', 'utf-8')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--config', default=str(CONFIG)); ap.add_argument('--epg-file'); ap.add_argument('--skip-probe', action='store_true'); ap.add_argument('--workers', type=int, default=4); ap.add_argument('--allow-empty', action='store_true')
    a = ap.parse_args(); cfg = json.loads(Path(a.config).read_text('utf-8')); now = datetime.now(JST)
    if a.epg_file: xml, source = Path(a.epg_file).read_bytes(), f'file:{Path(a.epg_file).name}'
    else: xml, source = fetch_epg(cfg)
    items = dedupe_kick(candidates(xml, cfg, now), cfg)
    print('[HARU VOD] matched ended candidates:', len(items))
    if a.skip_probe:
        for it in items: it.probe='skipped'
        playable = items
    else:
        playable, stats = probe_all(items, a.workers); print('[HARU VOD] probe stats:', stats, 'playable=', len(playable))
        if items and not playable and OUT_M3U.exists() and not a.allow_empty:
            raise RuntimeError('all replay probes failed; preserving previous shelf')
    playable = limit_items(playable, cfg); write(playable, cfg, source, not a.skip_probe, now)
    print('[HARU VOD] wrote', len(playable), 'items')

if __name__ == '__main__':
    try: main()
    except Exception as e:
        print('[HARU VOD] ERROR:', e, file=sys.stderr); raise
