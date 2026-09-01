import fs from 'node:fs';
import path from 'node:path';

const ASSET_DIR = path.join(process.cwd(), 'radio-video-assets');
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

function rewriteMedia(text, source) {
  const base = new URL(source);
  const out = [];
  for (let line of text.split(/\r?\n/)) {
    line = line.replace(/URI="([^"]+)"/g, (_, raw) => `URI="${new URL(raw, base).toString()}"`);
    const s = line.trim();
    if (s && !s.startsWith('#')) line = new URL(s, base).toString();
    out.push(line);
  }
  return out.join('\n');
}

async function nhkMedia(url) {
  let r = await fetch(url, { headers: { 'User-Agent': 'Mozilla/5.0' }, cache: 'no-store', redirect: 'follow' });
  let text = await r.text();
  if (!r.ok || !text.includes('#EXTM3U')) throw new Error(`NHK playlist HTTP ${r.status}`);
  const child = firstMediaUrl(text, r.url || url);
  if (child) {
    r = await fetch(child, { headers: { 'User-Agent': 'Mozilla/5.0' }, cache: 'no-store', redirect: 'follow' });
    text = await r.text();
    if (!r.ok || !text.includes('#EXTM3U')) throw new Error(`NHK media HTTP ${r.status}`);
  }
  return rewriteMedia(text, r.url || child || url);
}

async function audioMedia(req, station, cfg) {
  if (cfg.radiko) {
    const url = `${selfBase(req)}/api/radiko?station=${encodeURIComponent(cfg.radiko)}&stage=media`;
    const r = await fetch(url, { cache: 'no-store', redirect: 'follow' });
    const text = await r.text();
    if (!r.ok || !text.includes('#EXTM3U')) throw new Error(`Radiko audio HTTP ${r.status}: ${text.slice(0, 120)}`);
    return text;
  }
  return nhkMedia(cfg.nhk);
}

function patchSegment(source, sequence) {
  const out = Buffer.from(source);
  const seq = BigInt(sequence);
  const seq32 = Number(seq & 0xffffffffn);
  let pos = 0;
  while ((pos = out.indexOf(Buffer.from('mfhd'), pos)) >= 0) {
    if (pos + 12 <= out.length) out.writeUInt32BE(seq32, pos + 8);
    pos += 4;
  }
  pos = 0;
  while ((pos = out.indexOf(Buffer.from('tfdt'), pos)) >= 0) {
    if (pos + 16 <= out.length) {
      const version = out[pos + 4];
      const ticks = seq * BigInt(SEGMENT_SECONDS * TIMESCALE);
      if (version === 1 && pos + 16 <= out.length) out.writeBigUInt64BE(ticks, pos + 8);
      else if (version === 0 && pos + 12 <= out.length) out.writeUInt32BE(Number(ticks & 0xffffffffn), pos + 8);
    }
    pos += 4;
  }
  return out;
}

function assetPath(station, kind) {
  const name = kind === 'init' ? 'init.mp4' : `${station}.m4s`;
  return path.join(ASSET_DIR, name);
}

function videoPlaylist(req, station) {
  const nowSeq = Math.floor(Date.now() / (SEGMENT_SECONDS * 1000));
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

    const asset = String(req.query?.asset || '');
    if (asset === 'init') {
      const data = fs.readFileSync(assetPath(station, 'init'));
      return send(res, 200, data, 'video/mp4', { cache: 'public, max-age=31536000, immutable' });
    }
    if (asset === 'seg') {
      const nRaw = String(req.query?.n || '0');
      if (!/^\d{1,15}$/.test(nRaw)) return send(res, 400, 'bad sequence\n', 'text/plain; charset=utf-8');
      const template = fs.readFileSync(assetPath(station, 'seg'));
      const data = patchSegment(template, BigInt(nRaw));
      return send(res, 200, data, 'video/iso.segment', { cache: 'public, max-age=86400' });
    }

    const stage = String(req.query?.stage || '');
    if (stage === 'audio') {
      const text = await audioMedia(req, station, cfg);
      return send(res, 200, text, 'application/vnd.apple.mpegurl; charset=utf-8');
    }
    if (stage === 'video') {
      return send(res, 200, videoPlaylist(req, station), 'application/vnd.apple.mpegurl; charset=utf-8');
    }
    if (stage === 'status') {
      const initOk = fs.existsSync(assetPath(station, 'init'));
      const segOk = fs.existsSync(assetPath(station, 'seg'));
      return send(res, 200, JSON.stringify({ ok: initOk && segOk, station, initOk, segOk }, null, 2), 'application/json; charset=utf-8');
    }
    return send(res, 200, master(req, station), 'application/vnd.apple.mpegurl; charset=utf-8');
  } catch (e) {
    return send(res, 502, JSON.stringify({ ok: false, error: `${e?.name || 'Error'}: ${e?.message || String(e)}` }, null, 2), 'application/json; charset=utf-8');
  }
}
