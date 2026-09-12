const { Readable } = require('node:stream');
const dns = require('node:dns').promises;
const net = require('node:net');

const MAX_REDIRECTS = 5;
const FETCH_TIMEOUT_MS = 20000;

function one(v) {
  return Array.isArray(v) ? v[0] : v;
}

function isPrivateIPv4(ip) {
  const p = ip.split('.').map(Number);
  if (p.length !== 4 || p.some(n => !Number.isInteger(n) || n < 0 || n > 255)) return true;
  const [a,b] = p;
  return (
    a === 0 ||
    a === 10 ||
    a === 127 ||
    (a === 169 && b === 254) ||
    (a === 172 && b >= 16 && b <= 31) ||
    (a === 192 && b === 168) ||
    (a === 100 && b >= 64 && b <= 127) ||
    a >= 224
  );
}

function isPrivateIPv6(ip) {
  const s = ip.toLowerCase();
  return (
    s === '::' ||
    s === '::1' ||
    s.startsWith('fc') ||
    s.startsWith('fd') ||
    s.startsWith('fe8') ||
    s.startsWith('fe9') ||
    s.startsWith('fea') ||
    s.startsWith('feb')
  );
}

function isPrivateIp(ip) {
  const family = net.isIP(ip);
  if (family === 4) return isPrivateIPv4(ip);
  if (family === 6) return isPrivateIPv6(ip);
  return true;
}

const ALLOWED_HOST_SUFFIXES = [
  'streaks.jp',
  'googlevideo.com',
  'youtube.com',
  'youtu.be',
  'ytimg.com',
  'charandom.blog',
  'jp-primehome.com',
  'boatrace.jp',
  'boatrace-bb.jlc.ne.jp',
  'jlc.ne.jp',
  'githubusercontent.com',
  'github.com',
];
const ALLOWED_EXACT_HOSTS = new Set([
  '118.68.167.114',
]);

function isAllowedHost(host) {
  host = String(host || '').toLowerCase().replace(/\.$/, '');
  if (ALLOWED_EXACT_HOSTS.has(host)) return true;
  return ALLOWED_HOST_SUFFIXES.some(sfx => host === sfx || host.endsWith('.' + sfx));
}

async function assertPublicTarget(urlString) {
  let u;
  try {
    u = new URL(urlString);
  } catch {
    throw new Error('invalid url');
  }

  if (!['http:', 'https:'].includes(u.protocol)) throw new Error('unsupported protocol');
  if (u.username || u.password) throw new Error('credentials in URL are not allowed');

  const host = u.hostname.toLowerCase();
  if (!host || host === 'localhost' || host.endsWith('.localhost') || host.endsWith('.local')) {
    throw new Error('local target blocked');
  }
  if (!isAllowedHost(host)) {
    throw new Error('target host not allowed');
  }

  if (net.isIP(host)) {
    if (isPrivateIp(host)) throw new Error('private target blocked');
    return u;
  }

  let records;
  try {
    records = await dns.lookup(host, { all: true, verbatim: true });
  } catch {
    throw new Error('DNS lookup failed');
  }
  if (!records.length || records.some(r => isPrivateIp(r.address))) {
    throw new Error('private target blocked');
  }
  return u;
}

function upstreamHeaders(target, req) {
  const h = new Headers();
  h.set('User-Agent', 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152 Safari/537.36');
  h.set('Accept', req.headers.accept || '*/*');
  h.set('Accept-Language', req.headers['accept-language'] || 'ja,en-US;q=0.9,en;q=0.8');
  h.set('Cache-Control', 'no-cache');
  h.set('Pragma', 'no-cache');

  if (req.headers.range) h.set('Range', req.headers.range);

  const host = target.hostname.toLowerCase();
  const full = target.href.toLowerCase();

  if (host.endsWith('streaks.jp')) {
    if (full.includes('boatrace') || full.includes('cp-boatrace-prod')) {
      h.set('Referer', 'https://www.boatrace.jp/');
      h.set('Origin', 'https://www.boatrace.jp');
    } else {
      h.set('Referer', 'https://tver.jp/');
      h.set('Origin', 'https://tver.jp');
    }
  } else if (host.endsWith('googlevideo.com') || host.endsWith('youtube.com') || host === 'youtu.be') {
    h.set('Referer', 'https://www.youtube.com/');
    h.set('Origin', 'https://www.youtube.com');
  } else if (host.endsWith('charandom.blog')) {
    h.set('Referer', 'https://haru.charandom.blog/');
  }

  return h;
}

async function fetchFollowingValidatedRedirects(initialUrl, req) {
  let current = await assertPublicTarget(initialUrl);

  for (let i = 0; i <= MAX_REDIRECTS; i++) {
    const ac = new AbortController();
    const timer = setTimeout(() => ac.abort(), FETCH_TIMEOUT_MS);

    let r;
    try {
      r = await fetch(current, {
        method: req.method === 'HEAD' ? 'HEAD' : 'GET',
        headers: upstreamHeaders(current, req),
        redirect: 'manual',
        signal: ac.signal,
      });
    } finally {
      clearTimeout(timer);
    }

    if (r.status >= 300 && r.status < 400 && r.headers.get('location')) {
      if (i === MAX_REDIRECTS) throw new Error('too many redirects');
      const next = new URL(r.headers.get('location'), current).href;
      current = await assertPublicTarget(next);
      continue;
    }
    return r;
  }
  throw new Error('redirect loop');
}

function proxyLink(abs) {
  return '/api/iptv-proxy?url=' + encodeURIComponent(abs);
}

function rewriteUriAttrs(line, baseUrl) {
  return line
    .replace(/URI="([^"]+)"/g, (_, uri) => {
      const abs = new URL(uri, baseUrl).href;
      return 'URI="' + proxyLink(abs) + '"';
    })
    .replace(/URI='([^']+)'/g, (_, uri) => {
      const abs = new URL(uri, baseUrl).href;
      return "URI='" + proxyLink(abs) + "'";
    });
}

function rewriteManifest(text, baseUrl) {
  return text.split(/\r?\n/).map(line => {
    if (!line) return line;
    if (line.startsWith('#')) return rewriteUriAttrs(line, baseUrl);
    try {
      return proxyLink(new URL(line.trim(), baseUrl).href);
    } catch {
      return line;
    }
  }).join('\n');
}

function copyHeaderIfPresent(upstream, res, name) {
  const v = upstream.headers.get(name);
  if (v) res.setHeader(name, v);
}

function setCommonHeaders(res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, HEAD, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Range, Content-Type, Accept');
  res.setHeader('Access-Control-Expose-Headers', 'Content-Length, Content-Range, Accept-Ranges, Content-Type');
  res.setHeader('Cross-Origin-Resource-Policy', 'cross-origin');
  res.setHeader('X-Content-Type-Options', 'nosniff');
}

module.exports = async function handler(req, res) {
  setCommonHeaders(res);

  if (req.method === 'OPTIONS') {
    res.statusCode = 204;
    return res.end();
  }
  if (!['GET', 'HEAD'].includes(req.method)) {
    res.statusCode = 405;
    return res.end('method not allowed');
  }

  if (one(req.query && req.query.health) === '1') {
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.setHeader('Cache-Control', 'no-store');
    return res.end(JSON.stringify({ ok: true, mode: 'browser-web-proxy' }));
  }

  const target = one(req.query && req.query.url);
  if (!target) {
    res.statusCode = 400;
    return res.end('missing url');
  }

  try {
    const upstream = await fetchFollowingValidatedRedirects(target, req);
    const finalUrl = upstream.url || target;
    const ctype = (upstream.headers.get('content-type') || '').toLowerCase();
    const pathname = (() => {
      try { return new URL(finalUrl).pathname.toLowerCase(); } catch { return ''; }
    })();

    res.statusCode = upstream.status;
    copyHeaderIfPresent(upstream, res, 'content-type');
    copyHeaderIfPresent(upstream, res, 'content-range');
    copyHeaderIfPresent(upstream, res, 'accept-ranges');
    copyHeaderIfPresent(upstream, res, 'etag');
    copyHeaderIfPresent(upstream, res, 'last-modified');

    if (req.method === 'HEAD') {
      copyHeaderIfPresent(upstream, res, 'content-length');
      return res.end();
    }

    const manifestByType =
      ctype.includes('mpegurl') ||
      ctype.includes('application/vnd.apple.mpegurl') ||
      ctype.includes('application/x-mpegurl') ||
      pathname.endsWith('.m3u8');

    if (manifestByType) {
      const body = await upstream.text();
      const rewritten = rewriteManifest(body, finalUrl);
      res.setHeader('Content-Type', 'application/vnd.apple.mpegurl; charset=utf-8');
      res.setHeader('Cache-Control', 'no-store, max-age=0');
      res.removeHeader('content-length');
      return res.end(rewritten);
    }

    const manifestishPath = /(?:manifest|playlist|master)/i.test(pathname);
    if (ctype.startsWith('text/') || (!ctype && manifestishPath)) {
      const body = await upstream.text().catch(() => '');
      if (body.startsWith('#EXTM3U')) {
        const rewritten = rewriteManifest(body, finalUrl);
        res.setHeader('Content-Type', 'application/vnd.apple.mpegurl; charset=utf-8');
        res.setHeader('Cache-Control', 'no-store, max-age=0');
        res.removeHeader('content-length');
        return res.end(rewritten);
      }
      res.setHeader('Content-Type', upstream.headers.get('content-type') || 'text/plain; charset=utf-8');
      res.setHeader('Cache-Control', upstream.headers.get('cache-control') || 'no-store');
      return res.end(body);
    }

    copyHeaderIfPresent(upstream, res, 'content-length');
    res.setHeader('Cache-Control', upstream.headers.get('cache-control') || 'public, max-age=5, stale-while-revalidate=30');

    if (!upstream.body) return res.end();
    const nodeStream = Readable.fromWeb(upstream.body);
    nodeStream.on('error', err => {
      if (!res.headersSent) res.statusCode = 502;
      res.destroy(err);
    });
    nodeStream.pipe(res);
  } catch (e) {
    res.statusCode = 502;
    res.setHeader('Content-Type', 'text/plain; charset=utf-8');
    res.setHeader('Cache-Control', 'no-store');
    return res.end('proxy error: ' + (e && e.message ? e.message : 'unknown'));
  }
};