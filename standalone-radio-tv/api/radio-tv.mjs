const ASSET_BASE = 'https://raw.githubusercontent.com/ajiousama/himitsu/main/vercel-radiko/radio-video-assets';
const RADIKO_BASE = 'https://himitsu-six.vercel.app/api/radiko';
const SEGMENT_SECONDS = 5;
const TIMESCALE = 12800;
const CACHE = new Map();

const STATIONS = {
  nhk_r1_osaka: { nhk: 'https://simul2.drdi.st.nhk/live/12/joined/master.m3u8' },
  nhk_fm_osaka: { nhk: 'https://simul2.drdi.st.nhk/live/13/joined/master.m3u8' },
  nhk_r1_matsuyama: { nhk: 'https://simul2.drdi.st.nhk/live/16/joined/master.m3u8' },
  nhk_fm_matsuyama: { nhk: 'https://simul2.drdi.st.nhk/live/17/joined/master.m3u8' },
  'JOEU-FM': { radiko: 'JOEU-FM' }, RNB: { radiko: 'RNB' }, ABC: { radiko: 'ABC' },
  CCL: { radiko: 'CCL' }, '802': { radiko: '802' }, FMO: { radiko: 'FMO' },
  MBS: { radiko: 'MBS' }, OBC: { radiko: 'OBC' }, KBS: { radiko: 'KBS' },
  'ALPHA-STATION': { radiko: 'ALPHA-STATION' }, 'E-RADIO': { radiko: 'E-RADIO' }, CRK: { radiko: 'CRK' },
};

function selfBase(req) {
  const proto = String(req.headers['x-forwarded-proto'] || 'https').split(',')[0].trim();
  return `${proto}://${req.headers.host}`;
}
function selfUrl(req, station, params = {}) {
  return `${selfBase(req)}/api/radio-tv?${new URLSearchParams({ station, ...params })}`;
}
function send(res, status, body, type, cache = 'no-store') {
  res.statusCode = status;
  res.setHeader('Content-Type', type);
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', cache);
  res.end(body);
}
async function asset(name) {
  if (CACHE.has(name)) return CACHE.get(name);
  const r = await fetch(`${ASSET_BASE}/${encodeURIComponent(name)}`, { redirect: 'follow' });
  if (!r.ok) throw new Error(`asset ${name} HTTP ${r.status}`);
  const b = Buffer.from(await r.arrayBuffer());
  CACHE.set(name, b);
  return b;
}
function patchSegment(source, sequence) {
  const out = Buffer.from(source);
  const seq = BigInt(sequence);
  let p = 0;
  while ((p = out.indexOf(Buffer.from('mfhd'), p)) >= 0) {
    if (p + 12 <= out.length) out.writeUInt32BE(Number(seq & 0xffffffffn), p + 8);
    p += 4;
  }
  p = 0;
  while ((p = out.indexOf(Buffer.from('tfdt'), p)) >= 0) {
    if (p + 16 <= out.length) {
      const ticks = seq * BigInt(SEGMENT_SECONDS * TIMESCALE);
      if (out[p + 4] === 1) out.writeBigUInt64BE(ticks, p + 8);
      else out.writeUInt32BE(Number(ticks & 0xffffffffn), p + 8);
    }
    p += 4;
  }
  return out;
}
function firstMediaUrl(text, source) {
  const lines = text.split(/\r?\n/); let variant = false;
  for (const line of lines) {
    if (line.trim().startsWith('#EXT-X-STREAM-INF:')) { variant = true; continue; }
    const s = line.trim();
    if (variant && s && !s.startsWith('#')) return new URL(s, source).toString();
  }
  return null;
}
function rewriteMedia(text, source) {
  const base = new URL(source);
  return text.split(/\r?\n/).map(line => {
    line = line.replace(/URI="([^"]+)"/g, (_, raw) => `URI="${new URL(raw, base)}"`);
    const s = line.trim();
    return s && !s.startsWith('#') ? new URL(s, base).toString() : line;
  }).join('\n');
}
async function nhkMedia(url) {
  let r = await fetch(url, { headers: { 'User-Agent': 'Mozilla/5.0' }, cache: 'no-store', redirect: 'follow' });
  let text = await r.text();
  if (!r.ok || !text.includes('#EXTM3U')) throw new Error(`NHK master HTTP ${r.status}`);
  const child = firstMediaUrl(text, r.url || url);
  if (child) {
    r = await fetch(child, { headers: { 'User-Agent': 'Mozilla/5.0' }, cache: 'no-store', redirect: 'follow' });
    text = await r.text();
    if (!r.ok || !text.includes('#EXTM3U')) throw new Error(`NHK media HTTP ${r.status}`);
  }
  return rewriteMedia(text, r.url || child || url);
}
async function audioMedia(cfg) {
  if (cfg.radiko) {
    const r = await fetch(`${RADIKO_BASE}?station=${encodeURIComponent(cfg.radiko)}&stage=media`, { cache: 'no-store', redirect: 'follow' });
    const text = await r.text();
    if (!r.ok || !text.includes('#EXTM3U')) throw new Error(`Radiko HTTP ${r.status}: ${text.slice(0,100)}`);
    return text;
  }
  return nhkMedia(cfg.nhk);
}
function videoPlaylist(req, station) {
  const now = Math.floor(Date.now() / (SEGMENT_SECONDS * 1000));
  const first = now - 7;
  const lines = ['#EXTM3U','#EXT-X-VERSION:7',`#EXT-X-TARGETDURATION:${SEGMENT_SECONDS}`,`#EXT-X-MEDIA-SEQUENCE:${first}`,'#EXT-X-INDEPENDENT-SEGMENTS',`#EXT-X-MAP:URI="${selfUrl(req,station,{asset:'init'})}"`];
  for (let n=first; n<=now; n++) {
    lines.push(`#EXT-X-PROGRAM-DATE-TIME:${new Date(n*SEGMENT_SECONDS*1000).toISOString()}`);
    lines.push(`#EXTINF:${SEGMENT_SECONDS.toFixed(3)},`);
    lines.push(selfUrl(req,station,{asset:'seg',n:String(n)}));
  }
  lines.push(''); return lines.join('\n');
}
function master(req, station) {
  return ['#EXTM3U','#EXT-X-VERSION:7',`#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="radio",NAME="Radio",DEFAULT=YES,AUTOSELECT=YES,URI="${selfUrl(req,station,{stage:'audio'})}"`,'#EXT-X-STREAM-INF:BANDWIDTH=320000,AVERAGE-BANDWIDTH=210000,RESOLUTION=640x360,FRAME-RATE=25.000,AUDIO="radio"',selfUrl(req,station,{stage:'video'}),''].join('\n');
}

export default async function handler(req,res) {
  try {
    if (req.method !== 'GET') return send(res,405,'method not allowed\n','text/plain; charset=utf-8');
    const station = String(req.query?.station || 'ABC').trim();
    const cfg = STATIONS[station];
    if (!cfg) return send(res,404,'unknown radio station\n','text/plain; charset=utf-8');
    const kind = String(req.query?.asset || '');
    if (kind === 'init') return send(res,200,await asset('init.mp4'),'video/mp4','public, max-age=31536000, immutable');
    if (kind === 'seg') {
      const n = String(req.query?.n || '0');
      if (!/^\d{1,15}$/.test(n)) return send(res,400,'bad sequence\n','text/plain; charset=utf-8');
      return send(res,200,patchSegment(await asset(`${station}.m4s`),BigInt(n)),'video/iso.segment','public, max-age=86400');
    }
    const stage = String(req.query?.stage || '');
    if (stage === 'audio') return send(res,200,await audioMedia(cfg),'application/vnd.apple.mpegurl; charset=utf-8');
    if (stage === 'video') return send(res,200,videoPlaylist(req,station),'application/vnd.apple.mpegurl; charset=utf-8');
    if (stage === 'status') {
      const [i,s] = await Promise.all([asset('init.mp4'),asset(`${station}.m4s`)]);
      return send(res,200,JSON.stringify({ok:!!i.length&&!!s.length,station,initBytes:i.length,segmentBytes:s.length},null,2),'application/json; charset=utf-8');
    }
    return send(res,200,master(req,station),'application/vnd.apple.mpegurl; charset=utf-8');
  } catch(e) {
    return send(res,502,JSON.stringify({ok:false,error:`${e?.name||'Error'}: ${e?.message||String(e)}`},null,2),'application/json; charset=utf-8');
  }
}
