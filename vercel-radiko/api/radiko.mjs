import crypto from 'node:crypto';

const AUTH_KEY = 'bcd151073c03b352e1ef2fd66c32209da9ca0afa';
const DEFAULT_STATION = 'ABC';
const BASE_HEADERS = {
  'X-Radiko-App': 'pc_html5',
  'X-Radiko-App-Version': '0.0.1',
  'X-Radiko-Device': 'pc',
  'X-Radiko-User': 'dummy_user',
  'User-Agent': 'Mozilla/5.0',
};

const CACHE = globalThis.__radikoPremiumCache || (globalThis.__radikoPremiumCache = {
  session: null,
  sessionAt: 0,
  token: null,
  tokenAt: 0,
  detectedArea: 'OUT',
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

function credentials() {
  const mail = String(process.env.RADIKO_MAIL || '').trim();
  const password = String(process.env.RADIKO_PASSWORD || '').trim();
  if (!mail || !password) throw new Error('RADIKO_MAIL / RADIKO_PASSWORD are required');
  return { mail, password };
}

async function premiumLogin(force = false) {
  const now = Date.now();
  if (!force && CACHE.session && now - CACHE.sessionAt < 40 * 60 * 1000) return CACHE.session;

  const { mail, password } = credentials();
  const body = new URLSearchParams({ mail, pass: password }).toString();
  const r = await fetch('https://radiko.jp/v4/api/member/login', {
    method: 'POST',
    headers: {
      'User-Agent': 'Mozilla/5.0',
      'Content-Type': 'application/x-www-form-urlencoded',
    },
    body,
    cache: 'no-store',
  });
  if (!r.ok) throw new Error(`Premium login failed: HTTP ${r.status}`);

  let obj;
  try {
    obj = await r.json();
  } catch {
    throw new Error('Premium login failed: invalid JSON response');
  }

  const session = String(obj?.radiko_session || '').trim();
  const areafree = String(obj?.areafree || '0') === '1';
  if (!session) throw new Error('Premium login failed: radiko_session was not returned');
  if (!areafree) throw new Error('Premium login succeeded but area-free is not enabled');

  CACHE.session = session;
  CACHE.sessionAt = now;
  CACHE.token = null;
  CACHE.tokenAt = 0;
  return session;
}

async function authPremium(force = false) {
  const now = Date.now();
  if (!force && CACHE.token && now - CACHE.tokenAt < 35 * 60 * 1000) {
    return { token: CACHE.token, detectedArea: CACHE.detectedArea };
  }

  const session = await premiumLogin(force);
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
  const auth2Url = `https://api.radiko.jp/v2/api/auth2?radiko_session=${encodeURIComponent(session)}`;
  const auth2 = await fetch(auth2Url, {
    headers: {
      ...BASE_HEADERS,
      'X-Radiko-AuthToken': token,
      'X-Radiko-PartialKey': partial,
    },
    cache: 'no-store',
  });
  const text = (await auth2.text()).trim();
  const detectedArea = text.split(',', 1)[0].trim();
  if (!auth2.ok || !/^JP\d{1,2}$/.test(detectedArea)) {
    throw new Error(`auth2 failed: ${auth2.status} ${text.slice(0, 80)}`);
  }

  CACHE.token = token;
  CACHE.tokenAt = now;
  CACHE.detectedArea = detectedArea;
  return { token, detectedArea };
}

function mediaHeaders(token) {
  // Premium area-free playback intentionally does NOT send X-Radiko-AreaId.
  return {
    'X-Radiko-AuthToken': token,
    'User-Agent': 'Mozilla/5.0',
    'Referer': 'https://radiko.jp/',
  };
}

async function fetchAuthorized(url, force = false) {
  const { token } = await authPremium(force);
  const r = await fetch(url, {
    headers: mediaHeaders(token),
    cache: 'no-store',
    redirect: 'follow',
  });
  if ((r.status === 401 || r.status === 403) && !force) return fetchAuthorized(url, true);
  return r;
}

async function streamBases(station) {
  const cached = CACHE.streamBases.get(station);
  if (cached && Date.now() - cached.at < 6 * 60 * 60 * 1000) return cached.urls;

  const candidates = [
    `https://radiko.jp/v3/station/stream/pc_html5/${encodeURIComponent(station)}.xml`,
    `https://api.radiko.jp/v3/station/stream/pc_html5/${encodeURIComponent(station)}.xml`,
  ];
  const urls = [];

  for (const candidate of candidates) {
    try {
      const r = await fetch(candidate, {
        headers: { 'User-Agent': 'Mozilla/5.0' },
        cache: 'no-store',
      });
      if (!r.ok) continue;
      const xml = await r.text();
      for (const m of xml.matchAll(/<url\b([^>]*)>([\s\S]*?)<\/url>/g)) {
        const attrs = m[1] || '';
        const body = m[2] || '';
        const areafree = attrs.match(/areafree="([^"]+)"/)?.[1] || '0';
        const timefree = attrs.match(/timefree="([^"]+)"/)?.[1] || '0';
        if (areafree !== '1' || timefree === '1') continue;
        const raw = body.match(/<playlist_create_url>([\s\S]*?)<\/playlist_create_url>/)?.[1];
        const url = xmlDecode(raw).trim();
        if (url && !urls.includes(url)) urls.push(url);
      }
      if (urls.length) break;
    } catch {
      // Try the alternate Radiko host.
    }
  }

  if (!urls.length) throw new Error(`no Premium area-free live URL for ${station}`);
  CACHE.streamBases.set(station, { at: Date.now(), urls });
  return urls;
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
  throw new Error(`no playable Premium HLS for ${station}: ${errors.slice(-8).join(',')}`);
}

function regionForPref(pref) {
  if (pref === 1) return '北海道';
  if (pref <= 7) return '東北';
  if (pref <= 14) return '関東';
  if (pref <= 20) return '甲信越';
  if (pref <= 24) return '東海';
  if (pref <= 30) return '近畿';
  if (pref <= 35) return '中国';
  if (pref <= 39) return '四国';
  return '九州沖縄';
}

async function fetchArea(pref) {
  try {
    const r = await fetch(`https://radiko.jp/v3/station/list/JP${pref}.xml`, {
      headers: { 'User-Agent': 'Mozilla/5.0' },
      cache: 'no-store',
    });
    if (!r.ok) return [];
    const xml = await r.text();
    const out = [];
    for (const block of xml.matchAll(/<station>([\s\S]*?)<\/station>/g)) {
      const id = xmlDecode(block[1].match(/<id>([\s\S]*?)<\/id>/)?.[1]).trim();
      const name = xmlDecode(block[1].match(/<name>([\s\S]*?)<\/name>/)?.[1]).trim();
      if (id) out.push([id, { name: name || id, pref, region: regionForPref(pref) }]);
    }
    return out;
  } catch {
    return [];
  }
}

async function allStations() {
  const now = Date.now();
  if (CACHE.stations && now - CACHE.stationsAt < 6 * 60 * 60 * 1000) return CACHE.stations;

  const results = await Promise.all(Array.from({ length: 47 }, (_, i) => fetchArea(i + 1)));
  const map = new Map();
  for (const area of results) {
    for (const [id, meta] of area) if (!map.has(id)) map.set(id, meta);
  }
  if (map.size < 100) throw new Error(`station discovery too small: ${map.size}`);
  CACHE.stations = map;
  CACHE.stationsAt = now;
  return map;
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
    if (s && !s.startsWith('#')) line = selfUrl(req, station, new URL(s, base).toString());
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

    if (String(req.query?.status || '') === '1') {
      const { detectedArea } = await authPremium(true);
      return send(res, 200, JSON.stringify({
        ok: true,
        mode: 'premium-area-free',
        areafree: true,
        detectedArea,
        region: process.env.VERCEL_REGION || null,
      }, null, 2), 'application/json; charset=utf-8');
    }

    if (String(req.query?.list || '') === '1') {
      await authPremium(false);
      const stations = await allStations();
      return send(res, 200, JSON.stringify({
        mode: 'premium-area-free',
        region: process.env.VERCEL_REGION || null,
        detectedArea: CACHE.detectedArea,
        stations: Object.fromEntries(stations.entries()),
      }, null, 2), 'application/json; charset=utf-8');
    }

    const station = String(req.query?.station || DEFAULT_STATION).trim();
    if (!/^[A-Za-z0-9_-]{2,32}$/.test(station)) {
      return send(res, 400, 'invalid station id\n', 'text/plain; charset=utf-8');
    }

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
        return send(res, 200, rewritePlaylist(data.toString('utf8'), r.url || upstream.toString(), req, station), 'application/vnd.apple.mpegurl; charset=utf-8');
      }
      return send(res, 200, data, ct);
    }

    const master = await createMaster(station);
    return send(res, 200, rewritePlaylist(master.text, master.url, req, station), 'application/vnd.apple.mpegurl; charset=utf-8');
  } catch (error) {
    return send(res, 502, JSON.stringify({
      ok: false,
      mode: 'premium-area-free',
      region: process.env.VERCEL_REGION || null,
      detectedArea: CACHE.detectedArea,
      error: `${error?.name || 'Error'}: ${error?.message || String(error)}`,
    }, null, 2), 'application/json; charset=utf-8');
  }
}
