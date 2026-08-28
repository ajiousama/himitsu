import crypto from 'node:crypto';

const AUTH_KEY = 'bcd151073c03b352e1ef2fd66c32209da9ca0afa';
const AREA = 'JP13';
const BASE_HEADERS = {
  'X-Radiko-App': 'pc_html5',
  'X-Radiko-App-Version': '0.0.1',
  'X-Radiko-Device': 'pc',
  'X-Radiko-User': 'dummy_user',
  'User-Agent': 'Mozilla/5.0',
};

const CACHE = globalThis.__radikoTokyoCache || (globalThis.__radikoTokyoCache = {
  token: null,
  tokenAt: 0,
  stations: null,
  stationsAt: 0,
  streamBases: new Map(),
});

function xmlDecode(value) {
  return String(value || '')
    .replaceAll('&amp;', '&')
    .replaceAll('&lt;', '<')
    .replaceAll('&gt;', '>')
    .replaceAll('&quot;', '"')
    .replaceAll('&#39;', "'");
}

async function authTokyo(force = false) {
  const now = Date.now();
  if (!force && CACHE.token && now - CACHE.tokenAt < 25 * 60 * 1000) {
    return CACHE.token;
  }

  const auth1 = await fetch('https://api.radiko.jp/v2/api/auth1', {
    headers: BASE_HEADERS,
    cache: 'no-store',
  });
  const token = auth1.headers.get('x-radiko-authtoken');
  const off = Number(auth1.headers.get('x-radiko-keyoffset'));
  const len = Number(auth1.headers.get('x-radiko-keylength'));
  if (!auth1.ok || !token || !Number.isFinite(off) || !Number.isFinite(len)) {
    throw new Error(`auth1 failed: ${auth1.status}`);
  }

  const partial = Buffer.from(AUTH_KEY.slice(off, off + len), 'utf8').toString('base64');
  const auth2 = await fetch('https://api.radiko.jp/v2/api/auth2', {
    headers: {
      ...BASE_HEADERS,
      'X-Radiko-AuthToken': token,
      'X-Radiko-PartialKey': partial,
    },
    cache: 'no-store',
  });
  const body = (await auth2.text()).trim();
  if (!auth2.ok || !body.startsWith(`${AREA},`)) {
    throw new Error(`auth2 failed: ${auth2.status} ${body.slice(0, 80)}`);
  }

  CACHE.token = token;
  CACHE.tokenAt = now;
  return token;
}

async function tokyoStations() {
  const now = Date.now();
  if (CACHE.stations && now - CACHE.stationsAt < 6 * 60 * 60 * 1000) return CACHE.stations;

  const r = await fetch(`https://radiko.jp/v3/station/list/${AREA}.xml`, {
    headers: { 'User-Agent': 'Mozilla/5.0' },
    cache: 'no-store',
  });
  if (!r.ok) throw new Error(`station list failed: ${r.status}`);
  const xml = await r.text();
  const out = new Map();
  for (const block of xml.matchAll(/<station>([\s\S]*?)<\/station>/g)) {
    const id = xmlDecode(block[1].match(/<id>([\s\S]*?)<\/id>/)?.[1]).trim();
    const name = xmlDecode(block[1].match(/<name>([\s\S]*?)<\/name>/)?.[1]).trim();
    if (id) out.set(id, name || id);
  }
  if (!out.size) throw new Error('Tokyo station list was empty');
  CACHE.stations = out;
  CACHE.stationsAt = now;
  return out;
}

async function streamBases(station) {
  const cached = CACHE.streamBases.get(station);
  if (cached && Date.now() - cached.at < 6 * 60 * 60 * 1000) return cached.urls;

  const r = await fetch(`https://radiko.jp/v3/station/stream/pc_html5/${encodeURIComponent(station)}.xml`, {
    headers: { 'User-Agent': 'Mozilla/5.0' },
    cache: 'no-store',
  });
  if (!r.ok) throw new Error(`stream XML failed: ${r.status}`);
  const xml = await r.text();
  const preferred = [];
  const fallback = [];
  for (const m of xml.matchAll(/<url\b([^>]*)>([\s\S]*?)<\/url>/g)) {
    const attrs = m[1] || '';
    const body = m[2] || '';
    const timefree = attrs.match(/timefree="([^"]+)"/)?.[1] || '0';
    const areafree = attrs.match(/areafree="([^"]+)"/)?.[1] || '0';
    if (timefree === '1') continue;
    const raw = body.match(/<playlist_create_url>([\s\S]*?)<\/playlist_create_url>/)?.[1];
    const url = xmlDecode(raw).trim();
    if (!url) continue;
    (areafree === '0' ? preferred : fallback).push(url);
  }
  const urls = [...new Set([...preferred, ...fallback])];
  if (!urls.length) throw new Error(`no live playlist_create_url for ${station}`);
  CACHE.streamBases.set(station, { at: Date.now(), urls });
  return urls;
}

function mediaHeaders(token) {
  return {
    'X-Radiko-AuthToken': token,
    'X-Radiko-AreaId': AREA,
    'User-Agent': 'Mozilla/5.0',
    'Referer': 'https://radiko.jp/',
  };
}

async function fetchAuthorized(url, force = false) {
  const token = await authTokyo(force);
  const r = await fetch(url, { headers: mediaHeaders(token), cache: 'no-store', redirect: 'follow' });
  if ((r.status === 401 || r.status === 403) && !force) return fetchAuthorized(url, true);
  return r;
}

async function createMaster(station) {
  const bases = await streamBases(station);
  const errors = [];
  for (const base of bases) {
    for (const type of ['c', 'b']) {
      const q = new URLSearchParams({
        station_id: station,
        l: '15',
        lsid: crypto.randomBytes(16).toString('hex'),
        type,
      });
      const url = `${base}${base.includes('?') ? '&' : '?'}${q}`;
      try {
        const r = await fetchAuthorized(url);
        const text = await r.text();
        if (r.ok && text.includes('#EXTM3U')) return { url: r.url || url, text };
        errors.push(`${type}:${r.status}`);
      } catch (e) {
        errors.push(`${type}:${e?.name || 'Error'}`);
      }
    }
  }
  throw new Error(`no playable HLS for ${station}: ${errors.slice(-8).join(',')}`);
}

function allowedUpstream(raw) {
  let u;
  try { u = new URL(raw); } catch { return null; }
  if (u.protocol !== 'https:') return null;
  const h = u.hostname.toLowerCase();
  const ok = h === 'radiko.jp' || h.endsWith('.radiko.jp') || h.endsWith('.radiko-cf.com') || h.endsWith('.smartstream.ne.jp');
  return ok ? u : null;
}

function selfUrl(req, station, upstream) {
  const proto = String(req.headers['x-forwarded-proto'] || 'https').split(',')[0].trim();
  const host = req.headers.host;
  return `${proto}://${host}/api/radiko?station=${encodeURIComponent(station)}&u=${encodeURIComponent(upstream)}`;
}

function rewritePlaylist(text, source, req, station) {
  const base = new URL(source);
  const rewritten = [];
  for (let line of text.split(/\r?\n/)) {
    line = line.replace(/URI="([^"]+)"/g, (_, raw) => {
      const absolute = new URL(raw, base).toString();
      return `URI="${selfUrl(req, station, absolute)}"`;
    });
    const s = line.trim();
    if (s && !s.startsWith('#')) {
      line = selfUrl(req, station, new URL(s, base).toString());
    }
    rewritten.push(line);
  }
  return rewritten.join('\n');
}

function send(res, status, body, contentType) {
  res.statusCode = status;
  res.setHeader('Content-Type', contentType);
  res.setHeader('Cache-Control', 'no-store');
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.end(body);
}

export default async function handler(req, res) {
  try {
    if (req.method !== 'GET') return send(res, 405, 'method not allowed\n', 'text/plain; charset=utf-8');

    const stations = await tokyoStations();
    if (String(req.query?.list || '') === '1') {
      const obj = Object.fromEntries(stations.entries());
      return send(res, 200, JSON.stringify({ area: AREA, region: process.env.VERCEL_REGION || null, stations: obj }, null, 2), 'application/json; charset=utf-8');
    }

    const station = String(req.query?.station || 'TBS').trim();
    if (!stations.has(station)) return send(res, 404, `unknown Tokyo station: ${station}\n`, 'text/plain; charset=utf-8');

    const upstreamRaw = String(req.query?.u || '').trim();
    if (upstreamRaw) {
      const upstream = allowedUpstream(upstreamRaw);
      if (!upstream) return send(res, 403, 'upstream not allowed\n', 'text/plain; charset=utf-8');
      const r = await fetchAuthorized(upstream.toString());
      const data = Buffer.from(await r.arrayBuffer());
      if (!r.ok) return send(res, r.status, data, r.headers.get('content-type') || 'application/octet-stream');
      const ct = r.headers.get('content-type') || 'application/octet-stream';
      const looksM3u8 = upstream.pathname.toLowerCase().endsWith('.m3u8') || ct.toLowerCase().includes('mpegurl') || data.subarray(0, 64).toString('utf8').includes('#EXTM3U');
      if (looksM3u8) {
        const text = rewritePlaylist(data.toString('utf8'), r.url || upstream.toString(), req, station);
        return send(res, 200, text, 'application/vnd.apple.mpegurl; charset=utf-8');
      }
      return send(res, 200, data, ct);
    }

    const master = await createMaster(station);
    const body = rewritePlaylist(master.text, master.url, req, station);
    return send(res, 200, body, 'application/vnd.apple.mpegurl; charset=utf-8');
  } catch (error) {
    return send(
      res,
      502,
      JSON.stringify({
        ok: false,
        region: process.env.VERCEL_REGION || null,
        area: AREA,
        error: `${error?.name || 'Error'}: ${error?.message || String(error)}`,
      }, null, 2),
      'application/json; charset=utf-8',
    );
  }
}
