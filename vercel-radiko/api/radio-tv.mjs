const SEGMENT_SECONDS = 5;
const TIMESCALE = 12800;

const STATIONS = {
  nhk_r1_osaka: { nhk: 'https://simul2.drdi.st.nhk/live/12/joined/master.m3u8' },
  nhk_fm_osaka: { nhk: 'https://simul2.drdi.st.nhk/live/13/joined/master.m3u8' },
  nhk_r1_matsuyama: { nhk: 'https://simul2.drdi.st.nhk/live/16/joined/master.m3u8' },
  nhk_fm_matsuyama: { nhk: 'https://simul2.drdi.st.nhk/live/17/joined/master.m3u8' },
  'JOEU-FM': { radiko: 'JOEU-FM' },
  RNB: { radiko: 'RNB' },
  ABC: { radiko: 'ABC' },
  CCL: { radiko: 'CCL' },
  '802': { radiko: '802' },
  FMO: { radiko: 'FMO' },
  MBS: { radiko: 'MBS' },
  OBC: { radiko: 'OBC' },
  KBS: { radiko: 'KBS' },
  'ALPHA-STATION': { radiko: 'ALPHA-STATION' },
  'E-RADIO': { radiko: 'E-RADIO' },
  CRK: { radiko: 'CRK' },
};

function selfBase(req) {
  const proto = String(req.headers['x-forwarded-proto'] || 'https').split(',')[0].trim();
  return `${proto}://${req.headers.host}`;
}

function selfUrl(req, station, params = {}) {
  const q = new URLSearchParams({ station, ...params });
  return `${selfBase(req)}/api/radio-tv?${q.toString()}`;
}

function staticAssetUrl(req, station, kind) {
  const name = kind === 'init' ? 'init.mp4' : `${station}.m4s`;
  return `${selfBase(req)}/radio-video-assets/${encodeURIComponent(name)}`;
}

async function readAsset(req, station, kind) {
  const url = staticAssetUrl(req, station, kind);
  const r = await fetch(url, { cache: 'force-cache', redirect: 'follow' });
  if (!r.ok) throw new Error(`Required video asset is unavailable. ${url} (HTTP ${r.status})`);
  return Buffer.from(await r.arrayBuffer());
}

async function assetAvailable(req, station, kind) {
  try {
    const url = staticAssetUrl(req, station, kind);
    const r = await fetch(url, { method: 'HEAD', cache: 'no-store', redirect: 'follow' });
    return r.ok;
  } catch {
    return false;
  }
}

function send(res, status, body, contentType, extra = {}) {
  res.statusCode = status;
  res.setHeader('Content-Type', contentType);
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', extra.cache || 'no-store');
  for (const [k, v] of Object.entries(extra.headers || {})) res.setHeader(k, v);
  res.end(body);
}

function firstMediaUrl(text, source) {
  const lines = text.split(/\r?\n/);
  let sawVariant = false;
  for (const line of lines) {
    if (line.trim().startsWith('#EXT-X-STREAM-INF:')) {
      sawVariant = true;
      continue;
    }
    const s = line.trim();
    if (s && !s.startsWith('#') && sawVariant) return new URL(s, source).toString();
  }
  return null;
}

function latestProgramDateTime(text) {
  const marker = '#EXT-X-PROGRAM-DATE-TIME:';
  let nextStart = NaN;
  let durationMs = 0;
  let latest = NaN;
  for (const line of text.split(/\r?\n/)) {
    const s = line.trim();
    if (s.startsWith(marker)) {
      const t = Date.parse(s.slice(marker.length).trim());
      if (Number.isFinite(t)) nextStart = t;
      continue;
    }
    if (s.startsWith('#EXTINF:')) {
      const seconds = Number.parseFloat(s.slice('#EXTINF:'.length));
      durationMs = Number.isFinite(seconds) ? seconds * 1000 : 0;
      continue;
    }
    if (s && !s.startsWith('#') && Number.isFinite(nextStart)) {
      latest = nextStart;
      nextStart += durationMs;
      durationMs = 0;
    }
  }
  return latest;
}

function validateNhkUrl(raw) {
  const u = new URL(raw);
  if (u.protocol !== 'https:') throw new Error('NHK relay requires https');
  const h = u.hostname.toLowerCase();
  if (!(h === 'drdi.st.nhk' || h.endsWith('.drdi.st.nhk'))) {
    throw new Error(`NHK relay host blocked: ${h}`);
  }
  return u;
}

async function fetchNhk(raw) {
  let current = validateNhkUrl(raw);
  for (let i = 0; i < 4; i++) {
    const r = await fetch(current, {
      headers: { 'User-Agent': 'Mozilla/5.0' },
      cache: 'no-store',
      redirect: 'manual',
    });
    if ([301, 302, 303, 307, 308].includes(r.status)) {
      const loc = r.headers.get('location');
      if (!loc) throw new Error(`NHK redirect ${r.status} without location`);
      current = validateNhkUrl(new URL(loc, current).toString());
      continue;
    }
    return { response: r, url: current.toString() };
  }
  throw new Error('NHK redirect limit exceeded');
}

function relayUrl(req, station, absoluteUrl) {
  const relay = Buffer.from(absoluteUrl, 'utf8').toString('base64url');
  return selfUrl(req, station, { relay });
}

function rewriteNhkMedia(req, station, text, source) {
  const base = new URL(source);
  const out = [];
  for (let line of text.split(/\r?\n/)) {
    line = line.replace(/URI="([^"]+)"/g, (_, raw) => {
      const absolute = validateNhkUrl(new URL(raw, base).toString()).toString();
      return `URI="${relayUrl(req, station, absolute)}"`;
    });
    const s = line.trim();
    if (s && !s.startsWith('#')) {
      const absolute = validateNhkUrl(new URL(s, base).toString()).toString();
      line = relayUrl(req, station, absolute);
    }
    out.push(line);
  }
  return out.join('\n');
}

async function nhkMedia(req, station, url) {
  let got = await fetchNhk(url);
  let r = got.response;
  let source = got.url;
  let text = await r.text();
  if (!r.ok || !text.includes('#EXTM3U')) throw new Error(`NHK playlist HTTP ${r.status}`);

  const child = firstMediaUrl(text, source);
  if (child) {
    got = await fetchNhk(child);
    r = got.response;
    source = got.url;
    text = await r.text();
    if (!r.ok || !text.includes('#EXTM3U')) throw new Error(`NHK media HTTP ${r.status}`);
  }
  return rewriteNhkMedia(req, station, text, source);
}

async function audioMedia(req, station, cfg) {
  if (cfg.radiko) {
    const url = `${selfBase(req)}/api/radiko?station=${encodeURIComponent(cfg.radiko)}&stage=media`;
    const r = await fetch(url, { cache: 'no-store', redirect: 'follow' });
    const text = await r.text();
    if (!r.ok || !text.includes('#EXTM3U')) throw new Error(`Radiko audio HTTP ${r.status}: ${text.slice(0, 120)}`);
    return text;
  }
  return nhkMedia(req, station, cfg.nhk);
}

async function relayNhk(req, res, station, token) {
  let decoded;
  try {
    decoded = Buffer.from(token, 'base64url').toString('utf8');
  } catch {
    return send(res, 400, 'bad relay token\n', 'text/plain; charset=utf-8');
  }
  const got = await fetchNhk(decoded);
  const r = got.response;
  if (!r.ok) {
    const text = await r.text();
    return send(res, r.status, text.slice(0, 1000), 'text/plain; charset=utf-8');
  }
  const data = Buffer.from(await r.arrayBuffer());
  const type = r.headers.get('content-type') || 'application/octet-stream';
  return send(res, 200, data, type, { cache: 'no-store' });
}

function patchSegment(source, sequence) {
  const out = Buffer.from(source);
  const seq = BigInt(sequence);
  const seq32 = Number(seq & 0xffffffffn);
  const ticks = seq * BigInt(SEGMENT_SECONDS * TIMESCALE);
  let pos = 0;

  while ((pos = out.indexOf(Buffer.from('mfhd'), pos)) >= 0) {
    if (pos + 12 <= out.length) out.writeUInt32BE(seq32, pos + 8);
    pos += 4;
  }

  pos = 0;
  while ((pos = out.indexOf(Buffer.from('sidx'), pos)) >= 0) {
    if (pos + 24 <= out.length) {
      const version = out[pos + 4];
      const scale = out.readUInt32BE(pos + 12) || TIMESCALE;
      const sidxTicks = seq * BigInt(SEGMENT_SECONDS) * BigInt(scale);
      if (version === 1) out.writeBigUInt64BE(sidxTicks, pos + 16);
      else if (version === 0 && pos + 20 <= out.length) out.writeUInt32BE(Number(sidxTicks & 0xffffffffn), pos + 16);
    }
    pos += 4;
  }

  pos = 0;
  while ((pos = out.indexOf(Buffer.from('tfdt'), pos)) >= 0) {
    if (pos + 16 <= out.length) {
      const version = out[pos + 4];
      if (version === 1) out.writeBigUInt64BE(ticks, pos + 8);
      else if (version === 0 && pos + 12 <= out.length) out.writeUInt32BE(Number(ticks & 0xffffffffn), pos + 8);
    }
    pos += 4;
  }
  return out;
}

function videoPlaylist(req, station, anchorMs = Date.now()) {
  const nowSeq = Math.floor(anchorMs / (SEGMENT_SECONDS * 1000));
  const first = nowSeq - 7;
  const lines = [
    '#EXTM3U',
    '#EXT-X-VERSION:7',
    `#EXT-X-TARGETDURATION:${SEGMENT_SECONDS}`,
    `#EXT-X-MEDIA-SEQUENCE:${first}`,
    '#EXT-X-INDEPENDENT-SEGMENTS',
    `#EXT-X-MAP:URI="${selfUrl(req, station, { asset: 'init' })}"`,
  ];
  for (let n = first; n <= nowSeq; n++) {
    lines.push(`#EXT-X-PROGRAM-DATE-TIME:${new Date(n * SEGMENT_SECONDS * 1000).toISOString()}`);
    lines.push(`#EXTINF:${SEGMENT_SECONDS.toFixed(3)},`);
    lines.push(selfUrl(req, station, { asset: 'seg', n: String(n) }));
  }
  lines.push('');
  return lines.join('\n');
}

function master(req, station) {
  const audio = selfUrl(req, station, { stage: 'audio' });
  const video = selfUrl(req, station, { stage: 'video' });
  return [
    '#EXTM3U',
    '#EXT-X-VERSION:7',
    `#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="radio",NAME="Radio",DEFAULT=YES,AUTOSELECT=YES,URI="${audio}"`,
    '#EXT-X-STREAM-INF:BANDWIDTH=320000,AVERAGE-BANDWIDTH=210000,RESOLUTION=640x360,FRAME-RATE=25.000,AUDIO="radio"',
    video,
    '',
  ].join('\n');
}

export default async function handler(req, res) {
  try {
    if (req.method !== 'GET') return send(res, 405, 'method not allowed\n', 'text/plain; charset=utf-8');
    const station = String(req.query?.station || 'ABC').trim();
    const cfg = STATIONS[station];
    if (!cfg) return send(res, 404, 'unknown radio station\n', 'text/plain; charset=utf-8');

    const relay = String(req.query?.relay || '');
    if (relay) {
      if (!cfg.nhk) return send(res, 403, 'relay is NHK-only\n', 'text/plain; charset=utf-8');
      return relayNhk(req, res, station, relay);
    }

    const asset = String(req.query?.asset || '');
    if (asset === 'init') {
      const data = await readAsset(req, station, 'init');
      return send(res, 200, data, 'video/mp4', { cache: 'public, max-age=31536000, immutable' });
    }
    if (asset === 'seg') {
      const nRaw = String(req.query?.n || '0');
      if (!/^\d{1,15}$/.test(nRaw)) return send(res, 400, 'bad sequence\n', 'text/plain; charset=utf-8');
      const template = await readAsset(req, station, 'seg');
      const data = patchSegment(template, BigInt(nRaw));
      return send(res, 200, data, 'video/iso.segment', { cache: 'public, max-age=86400' });
    }

    const stage = String(req.query?.stage || '');
    if (stage === 'audio') {
      const text = await audioMedia(req, station, cfg);
      return send(res, 200, text, 'application/vnd.apple.mpegurl; charset=utf-8');
    }
    if (stage === 'video') {
      const audioText = await audioMedia(req, station, cfg);
      const audioEdge = latestProgramDateTime(audioText);
      const anchorMs = Number.isFinite(audioEdge) ? audioEdge : Date.now();
      return send(res, 200, videoPlaylist(req, station, anchorMs), 'application/vnd.apple.mpegurl; charset=utf-8');
    }
    if (stage === 'status') {
      const [initOk, segOk] = await Promise.all([
        assetAvailable(req, station, 'init'),
        assetAvailable(req, station, 'seg'),
      ]);
      return send(res, 200, JSON.stringify({ ok: initOk && segOk, station, initOk, segOk }, null, 2), 'application/json; charset=utf-8');
    }
    return send(res, 200, master(req, station), 'application/vnd.apple.mpegurl; charset=utf-8');
  } catch (e) {
    return send(res, 502, JSON.stringify({ ok: false, error: `${e?.name || 'Error'}: ${e?.message || String(e)}` }, null, 2), 'application/json; charset=utf-8');
  }
}
