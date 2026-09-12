const http = require('node:http');
const { Readable } = require('node:stream');
const dns = require('node:dns').promises;
const net = require('node:net');

const PORT = Number(process.env.PORT || 10000);
const MAX_REDIRECTS = 5;
const FETCH_TIMEOUT_MS = 20000;

const ALLOWED_HOST_SUFFIXES = [
  'streaks.jp',
  'googlevideo.com',
  'youtube.com',
  'youtu.be',
  'youtube-nocookie.com',
  'ytimg.com',
  'charandom.blog',
  'jp-primehome.com',
  'boatrace.jp',
  'boatrace-bb.jlc.ne.jp',
  'jlc.ne.jp',
  'githubusercontent.com',
  'github.com',
];
const ALLOWED_EXACT_HOSTS = new Set(['118.68.167.114']);

function isPrivateIPv4(ip) {
  const p = ip.split('.').map(Number);
  if (p.length !== 4 || p.some(n => !Number.isInteger(n) || n < 0 || n > 255)) return true;
  const [a,b] = p;
  return a === 0 || a === 10 || a === 127 || (a === 169 && b === 254) ||
    (a === 172 && b >= 16 && b <= 31) || (a === 192 && b === 168) ||
    (a === 100 && b >= 64 && b <= 127) || a >= 224;
}
function isPrivateIPv6(ip) {
  const s = ip.toLowerCase();
  return s === '::' || s === '::1' || s.startsWith('fc') || s.startsWith('fd') ||
    s.startsWith('fe8') || s.startsWith('fe9') || s.startsWith('fea') || s.startsWith('feb');
}
function isPrivateIp(ip) {
  const f = net.isIP(ip);
  return f === 4 ? isPrivateIPv4(ip) : f === 6 ? isPrivateIPv6(ip) : true;
}
function isAllowedHost(host) {
  host = String(host || '').toLowerCase().replace(/\.$/, '');
  if (ALLOWED_EXACT_HOSTS.has(host)) return true;
  return ALLOWED_HOST_SUFFIXES.some(s => host === s || host.endsWith('.' + s));
}
async function assertPublicTarget(urlString) {
  let u;
  try { u = new URL(urlString); } catch { throw new Error('invalid url'); }
  if (!['http:', 'https:'].includes(u.protocol)) throw new Error('unsupported protocol');
  if (u.username || u.password) throw new Error('credentials in URL are not allowed');
  const host = u.hostname.toLowerCase();
  if (!host || host === 'localhost' || host.endsWith('.localhost') || host.endsWith('.local')) throw new Error('local target blocked');
  if (!isAllowedHost(host)) throw new Error('target host not allowed');
  if (net.isIP(host)) {
    if (isPrivateIp(host)) throw new Error('private target blocked');
    return u;
  }
  let records;
  try { records = await dns.lookup(host, { all: true, verbatim: true }); }
  catch { throw new Error('DNS lookup failed'); }
  if (!records.length || records.some(r => isPrivateIp(r.address))) throw new Error('private target blocked');
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
    } finally { clearTimeout(timer); }
    if (r.status >= 300 && r.status < 400 && r.headers.get('location')) {
      if (i === MAX_REDIRECTS) throw new Error('too many redirects');
      current = await assertPublicTarget(new URL(r.headers.get('location'), current).href);
      continue;
    }
    return r;
  }
  throw new Error('redirect loop');
}
function proxyLink(abs) { return '/proxy?url=' + encodeURIComponent(abs); }
function rewriteUriAttrs(line, baseUrl) {
  return line
    .replace(/URI="([^"]+)"/g, (_, uri) => 'URI="' + proxyLink(new URL(uri, baseUrl).href) + '"')
    .replace(/URI='([^']+)'/g, (_, uri) => "URI='" + proxyLink(new URL(uri, baseUrl).href) + "'");
}
function rewriteManifest(text, baseUrl) {
  return text.split(/\r?\n/).map(line => {
    if (!line) return line;
    if (line.startsWith('#')) return rewriteUriAttrs(line, baseUrl);
    try { return proxyLink(new URL(line.trim(), baseUrl).href); }
    catch { return line; }
  }).join('\n');
}
function setCors(res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, HEAD, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Range, Content-Type, Accept');
  res.setHeader('Access-Control-Expose-Headers', 'Content-Length, Content-Range, Accept-Ranges, Content-Type');
  res.setHeader('Cross-Origin-Resource-Policy', 'cross-origin');
  res.setHeader('X-Content-Type-Options', 'nosniff');
}
function copyHeader(up, res, name) { const v = up.headers.get(name); if (v) res.setHeader(name, v); }

const server = http.createServer(async (req, res) => {
  setCors(res);
  const base = 'http://' + (req.headers.host || 'localhost');
  const parsed = new URL(req.url, base);
  if (req.method === 'OPTIONS') { res.statusCode = 204; return res.end(); }
  if (parsed.pathname === '/' || parsed.pathname === '/health') {
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.setHeader('Cache-Control', 'no-store');
    return res.end(JSON.stringify({ ok: true, service: 'iptv-9x-browser-proxy' }));
  }
  if (parsed.pathname !== '/proxy') { res.statusCode = 404; return res.end('not found'); }
  if (!['GET','HEAD'].includes(req.method)) { res.statusCode = 405; return res.end('method not allowed'); }
  const target = parsed.searchParams.get('url');
  if (!target) { res.statusCode = 400; return res.end('missing url'); }
  try {
    const upstream = await fetchFollowingValidatedRedirects(target, req);
    const finalUrl = upstream.url || target;
    const ctype = (upstream.headers.get('content-type') || '').toLowerCase();
    let pathname = '';
    try { pathname = new URL(finalUrl).pathname.toLowerCase(); } catch {}
    res.statusCode = upstream.status;
    for (const n of ['content-type','content-range','accept-ranges','etag','last-modified']) copyHeader(upstream, res, n);
    if (req.method === 'HEAD') { copyHeader(upstream, res, 'content-length'); return res.end(); }
    const isManifest = ctype.includes('mpegurl') || pathname.endsWith('.m3u8');
    if (isManifest) {
      const body = await upstream.text();
      res.setHeader('Content-Type', 'application/vnd.apple.mpegurl; charset=utf-8');
      res.setHeader('Cache-Control', 'no-store, max-age=0');
      res.removeHeader('content-length');
      return res.end(rewriteManifest(body, finalUrl));
    }
    const manifestish = /(?:manifest|playlist|master)/i.test(pathname);
    if (ctype.startsWith('text/') || (!ctype && manifestish)) {
      const body = await upstream.text().catch(() => '');
      if (body.startsWith('#EXTM3U')) {
        res.setHeader('Content-Type', 'application/vnd.apple.mpegurl; charset=utf-8');
        res.setHeader('Cache-Control', 'no-store, max-age=0');
        res.removeHeader('content-length');
        return res.end(rewriteManifest(body, finalUrl));
      }
      res.setHeader('Content-Type', upstream.headers.get('content-type') || 'text/plain; charset=utf-8');
      res.setHeader('Cache-Control', upstream.headers.get('cache-control') || 'no-store');
      return res.end(body);
    }
    copyHeader(upstream, res, 'content-length');
    res.setHeader('Cache-Control', upstream.headers.get('cache-control') || 'public, max-age=5, stale-while-revalidate=30');
    if (!upstream.body) return res.end();
    const stream = Readable.fromWeb(upstream.body);
    stream.on('error', err => res.destroy(err));
    stream.pipe(res);
  } catch (e) {
    res.statusCode = 502;
    res.setHeader('Content-Type', 'text/plain; charset=utf-8');
    res.setHeader('Cache-Control', 'no-store');
    res.end('proxy error: ' + (e && e.message ? e.message : 'unknown'));
  }
});
server.listen(PORT, '0.0.0.0', () => console.log('IPTV browser proxy listening on', PORT));
