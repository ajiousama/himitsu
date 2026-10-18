'use strict';
const fs = require('node:fs');
const path = require('node:path');
const http = require('node:http');
const { webcrypto, timingSafeEqual } = require('node:crypto');
globalThis.crypto ??= webcrypto;

const args = process.argv.slice(2);
function option(name, fallback) {
  const i = args.indexOf(name);
  if (i < 0) return fallback;
  if (!args[i + 1] || args[i + 1].startsWith('--')) throw Error(`${name}: value required`);
  return args[i + 1];
}
const channel = option('--channel', process.env.CHANNEL || 'nouvelle_paradise');
// Extra channel endpoints are opt-in tests, not part of the FreeWiFi playlist.
const trialChannels = new Set(['teletama', 'tvk']);
if (!/^[a-zA-Z0-9_()-]+$/.test(channel)) throw Error('Invalid channel name');
const upstream = new URL(option('--base-url', process.env.UPSTREAM_BASE || 'https://linxei.biz.id'));
if (!['http:', 'https:'].includes(upstream.protocol) || upstream.username || upstream.password) throw Error('Invalid upstream');
const port = Number(option('--port', process.env.PORT || '8765'));
if (!Number.isInteger(port) || port < 1 || port > 65535) throw Error('Invalid port');
const accessToken = process.env.ACCESS_TOKEN || '';
if (!/^[A-Za-z0-9_-]{32,}$/.test(accessToken)) throw Error('Set ACCESS_TOKEN to at least 32 letters, digits, underscore or hyphen');
const publicBase = new URL(process.env.PUBLIC_BASE_URL || 'http://127.0.0.1:' + port);
if (!['http:', 'https:'].includes(publicBase.protocol) || publicBase.username || publicBase.password || publicBase.search || publicBase.hash || publicBase.pathname !== '/') throw Error('PUBLIC_BASE_URL must be an HTTP(S) origin');
const authQuery = '?key=' + encodeURIComponent(accessToken);
function localURL(p) { return publicBase.origin + p + authQuery; }
function authorized(url) {
 const keys = url.searchParams.getAll('key');
 const got = Buffer.from(keys.length === 1 ? keys[0] : '');
 const expected = Buffer.from(accessToken);
 return got.length === expected.length && timingSafeEqual(got, expected);
}
const vendor = path.resolve(__dirname, option('--decoder-dir', 'vendor'));
const decoderOrigin = 'https://osaka-drift-srv1.wasmer.app';
const maxBody = 32 * 1024 * 1024;
const maxCache = 64 * 1024 * 1024;
const cache = new Map(), pending = new Map();
let cacheBytes = 0;

function sourceURL(value, parent = upstream) {
  const u = new URL(value, parent);
  if (u.origin !== upstream.origin || !u.pathname.startsWith('/stream/') || u.username || u.password) {
    throw Error('Upstream URL is outside /stream/ on the configured server');
  }
  u.hash = '';
  if (u.pathname !== '/stream/master.m3u') u.searchParams.set('locate_stream', 'web');
  return u;
}
function localResource(value, parent) {
  const u = sourceURL(value, parent);
  return localURL('/resource/' + Buffer.from(u.pathname + u.search).toString('base64url'));
}
function rewritePlaylist(text, parent) {
  if (!text.trimStart().startsWith('#EXTM3U')) throw Error('Decoded data is not an M3U playlist');
  return text.split(/\r?\n/).map(line => {
    if (!line.trim()) return line;
    if (line.startsWith('#')) return line.replace(/URI="([^"\r\n]+)"/g, (_, uri) => `URI="${localResource(uri, parent)}"`);
    return localResource(line.trim(), parent);
  }).join('\n');
}
async function download(url, limit = maxBody) {
  const res = await fetch(url, { signal: AbortSignal.timeout(20000), redirect: 'error' });
  if (!res.ok) {
    await res.body?.cancel();
    throw Error(`Upstream HTTP ${res.status}. Access was not bypassed; try from a network where the source normally works.`);
  }
  if (Number(res.headers.get('content-length')) > limit) {
    await res.body?.cancel(); throw Error('Upstream body exceeds size limit');
  }
  const chunks = []; let length = 0;
  try {
    for await (const chunk of res.body) {
      length += chunk.length;
      if (length > limit) throw Error('Upstream body exceeds size limit');
      chunks.push(chunk);
    }
  } catch (e) { throw Error(`Download incomplete: ${e.message}`); }
  return { data: Buffer.concat(chunks), mime: res.headers.get('content-type') || 'application/octet-stream' };
}
function putCache(key, value, ttl) {
  const old = cache.get(key);
  if (old) { cacheBytes -= old.data.length; cache.delete(key); }
  const now = Date.now();
  for (const [k, v] of cache) if (v.expires <= now) { cacheBytes -= v.data.length; cache.delete(k); }
  while (cache.size && cacheBytes + value.data.length > maxCache) {
    const k = cache.keys().next().value; cacheBytes -= cache.get(k).data.length; cache.delete(k);
  }
  if (value.data.length <= maxCache) { cache.set(key, { ...value, expires: now + ttl }); cacheBytes += value.data.length; }
}
function decode(data) {
  const magic = data.subarray(0, 4).toString('ascii');
  if (magic !== 'NTXP' && magic !== 'NTXS') return { data, magic };
  const fn = globalThis[magic === 'NTXP' ? 'natsuxDecodeNTXP' : 'natsuxDecodeNTXS'];
  const result = fn(new Uint8Array(data));
  if (!result?.ok) throw Error(`${magic}: ${result?.error || 'decode failed'}`);
  // Copy out of WASM-owned memory before another decoder call.
  return { data: Buffer.from(result.data), magic };
}
async function resource(url) {
  const key = url.href;
  const hit = cache.get(key);
  if (hit && hit.expires > Date.now()) return hit;
  if (pending.has(key)) return pending.get(key);
  const job = (async () => {
    const raw = await download(url);
    const output = decode(raw.data);
    const playlist = output.magic === 'NTXP' || output.data.subarray(0, 7).toString() === '#EXTM3U';
    const result = playlist
      ? { data: Buffer.from(rewritePlaylist(output.data.toString('utf8'), url)), mime: 'application/vnd.apple.mpegurl; charset=utf-8' }
      : { data: output.data, mime: output.magic === 'NTXS' ? 'video/mp2t' : raw.mime };
    putCache(key, result, playlist ? 750 : 60000);
    return result;
  })();
  pending.set(key, job);
  try { return await job; } finally { pending.delete(key); }
}
// Create a short replay playlist without storing any video media.
// HLS segments are atomic: the end boundary is accurate to a segment.
function clippedReplayPlaylist(input, maxSeconds) {
  const lines = input.replace(/\r/g, '').split('\n');
  if (lines[0]?.trim() !== '#EXTM3U') throw Error('Catch-up source is not a media playlist');
  const header = [], media = [];
  let tags = [], inf = null, foundMedia = false;
  for (const raw of lines) {
    const line = raw.trim();
    if (!line || line === '#EXT-X-ENDLIST') continue;
    if (line.startsWith('#EXTINF:')) {
      const seconds = Number((line.match(/^#EXTINF:([0-9.]+)/) || [])[1]);
      if (!Number.isFinite(seconds) || seconds <= 0) throw Error('Invalid replay segment duration');
      inf = { line, seconds };
      foundMedia = true;
      continue;
    }
    if (line.startsWith('#')) {
      if (!foundMedia && !tags.length && !inf) header.push(line);
      else tags.push(line);
      continue;
    }
    if (inf) media.push({ tags, inf, uri: line });
    inf = null;
    tags = [];
  }
  if (!media.length) throw Error('No replay media segments available');
  const out = header.map(x => x.startsWith('#EXT-X-PLAYLIST-TYPE:') ? '#EXT-X-PLAYLIST-TYPE:VOD' : x);
  if (!out.some(x => x === '#EXT-X-PLAYLIST-TYPE:VOD')) out.push('#EXT-X-PLAYLIST-TYPE:VOD');
  let total = 0, count = 0;
  for (const group of media) {
    out.push(...group.tags, group.inf.line, group.uri);
    total += group.inf.seconds;
    count += 1;
    if (total >= maxSeconds || count >= 3600) break;
  }
  out.push('#EXT-X-ENDLIST');
  return out.join('\n') + '\n';
}

async function setupDecoder() {
  fs.mkdirSync(vendor, { recursive: true });
  for (const name of ['wasm_exec.js', 'natsux.wasm']) {
    const dest = path.join(vendor, name);
    if (!fs.existsSync(dest)) {
      console.log(`Downloading original decoder: ${name}`);
      const { data } = await download(`${decoderOrigin}/wasm/${name}`, 16 * 1024 * 1024);
      if (name.endsWith('.wasm') && !data.subarray(0, 8).equals(Buffer.from([0,97,115,109,1,0,0,0]))) throw Error('Invalid WASM response');
      fs.writeFileSync(dest + '.tmp', data);
      fs.renameSync(dest + '.tmp', dest);
    }
  }
  require(path.join(vendor, 'wasm_exec.js'));
  const go = new globalThis.Go();
  const { instance } = await WebAssembly.instantiate(fs.readFileSync(path.join(vendor, 'natsux.wasm')), go.importObject);
  let runtimeError;
  void go.run(instance).catch(e => { runtimeError = e; });
  const deadline = Date.now() + 5000;
  while (Date.now() < deadline) {
    if (runtimeError) throw runtimeError;
    if (globalThis.natsuxReady === false) throw Error('Original decoder refused this environment');
    if (globalThis.natsuxReady === true && typeof globalThis.natsuxDecodeNTXP === 'function' && typeof globalThis.natsuxDecodeNTXS === 'function') return;
    await new Promise(resolve => setTimeout(resolve, 15));
  }
  throw Error('Decoder startup timed out');
}
function send(res, status, data, mime) {
  res.writeHead(status, { 'Content-Type': mime, 'Content-Length': data.length, 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff' });
  // HEAD should match GET's status and response headers, without a body.
  if (res.req?.method === 'HEAD') return res.end();
  res.end(data);
}
async function main() {
  await setupDecoder();
  const server = http.createServer(async (req, res) => {
    if (req.method !== 'GET' && req.method !== 'HEAD') return send(res, 405, Buffer.from('GET and HEAD only'), 'text/plain');
    try {
      const requested = new URL(req.url, 'http://localhost');
      const route = requested.pathname;
      if (route === '/health') return send(res, 200, Buffer.from(JSON.stringify({ ready: true })), 'application/json');
      if (!authorized(requested)) return send(res, 401, Buffer.from('Authentication required'), 'text/plain');
      if (route === '/' || route === '/watch.m3u') {
        const list = `#EXTM3U\n#EXTINF:-1,${channel}\n${localURL('/playlist.m3u8')}\n`;
        return send(res, 200, Buffer.from(list), 'audio/x-mpegurl; charset=utf-8');
      }
      let target;
      // Guarded bounded replay clip, currently only ABC's requested morning segment.
      const clipMatch = route.match(/^\/clip\/([a-z0-9_-]+)\/(\d{10})\/(\d{2,4})\.m3u8$/);
      if (clipMatch) {
        const selected = clipMatch[1], epoch = Number(clipMatch[2]), seconds = Number(clipMatch[3]);
        const age = Math.floor(Date.now() / 1000) - epoch;
        if (selected !== 'abc' || seconds < 30 || seconds > 3600 || age < 0 || age > 6 * 86400)
          return send(res, 404, Buffer.from('Unavailable replay clip'), 'text/plain');
        const src = sourceURL('/stream/jp/' + selected + '/replay.m3u8?mode=hls&start=' + epoch);
        const decoded = await resource(src);
        const hls = clippedReplayPlaylist(decoded.data.toString('utf8'), seconds);
        return send(res, 200, Buffer.from(hls, 'utf8'), 'application/vnd.apple.mpegurl; charset=utf-8');
      }
      if (route === '/playlist.m3u8') target = sourceURL(`/stream/jp/${encodeURIComponent(channel)}/stream-output.m3u8?mode=hls`);
      else if (/^\/channel\/[a-z0-9_]+\/playlist\.m3u8$/.test(route)) {
        const selected = route.split('/')[2];
        if (!trialChannels.has(selected)) return send(res, 404, Buffer.from('Unknown trial channel'), 'text/plain');
        target = sourceURL(`/stream/jp/${selected}/stream-output.m3u8?mode=hls`);
      }
      else if (route === '/master.m3u') target = sourceURL('/stream/master.m3u');
      else if (route.startsWith('/resource/')) {
        const token = route.slice('/resource/'.length);
        if (!/^[a-zA-Z0-9_-]+$/.test(token) || token.length > 8192) throw Error('Invalid resource token');
        target = sourceURL(Buffer.from(token, 'base64url').toString('utf8'));
      } else return send(res, 404, Buffer.from('Not found'), 'text/plain');
      const result = await resource(target);
      send(res, 200, result.data, result.mime);
    } catch (e) {
      console.error(new Date().toISOString(), e.message);
      send(res, 502, Buffer.from(e.message + '\n'), 'text/plain; charset=utf-8');
    }
  });
  server.on('error', e => { console.error(e.message); process.exitCode = 1; });
  server.listen(port, '0.0.0.0', () => {
    console.log('Ready. Use PUBLIC_BASE_URL + /playlist.m3u8?key=YOUR_ACCESS_TOKEN');
    console.log('Channel list: PUBLIC_BASE_URL + /master.m3u?key=YOUR_ACCESS_TOKEN');
    console.log('Access token is not printed in logs.');
  });
  process.on('SIGINT', () => { server.close(); process.exit(0); });
}
main().catch(e => { console.error('Startup failed:', e.message); process.exitCode = 1; });
