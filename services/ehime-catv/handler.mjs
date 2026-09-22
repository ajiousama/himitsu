const CHANNELS = {
  town_news24: 'hc_town_news_24',
  machicam24: 'hc_machi_cam_24',
  event_selection: 'hc_eventsel_channel',
  ehime_channel: 'hc_ehime_channel',
  bousai: 'hc_bousai_channel',
  igo_shogi: 'hc_gosho_channel',
  ainan: 'hc_ainan_live_cam',
};

const UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1';
const NS = 'https://cdn.e-catv.ne.jp/mpeg-dash/';

function parseAttrs(text = '') {
  const out = {};
  for (const m of String(text).matchAll(/([A-Za-z_:][\w:.-]*)\s*=\s*"([^"]*)"/g)) out[m[1]] = m[2];
  return out;
}

function firstTag(xml, tag) {
  const m = String(xml).match(new RegExp(`<${tag}\\b([^>]*)>([\\s\\S]*?)<\\/${tag}>`, 'i'));
  if (m) return { attrs: parseAttrs(m[1]), body: m[2] };
  const s = String(xml).match(new RegExp(`<${tag}\\b([^>]*)\\/>`, 'i'));
  return s ? { attrs: parseAttrs(s[1]), body: '' } : null;
}

function adaptationSets(xml) {
  const out = [];
  const re = /<AdaptationSet\b([^>]*)>([\s\S]*?)<\/AdaptationSet>/gi;
  let m;
  while ((m = re.exec(xml))) out.push({ attrs: parseAttrs(m[1]), body: m[2] });
  return out;
}

function timelineSegments(segmentTemplate) {
  const scale = Math.max(1, Number(segmentTemplate.attrs.timescale || 1));
  const tl = firstTag(segmentTemplate.body, 'SegmentTimeline');
  if (!tl) return [];
  const out = [];
  const re = /<S\b([^>]*)\/?>(?:<\/S>)?/gi;
  let m, cur = null;
  while ((m = re.exec(tl.body))) {
    const a = parseAttrs(m[1]);
    if (a.t != null) cur = Number(a.t);
    const d = Number(a.d || 0);
    let r = Number(a.r || 0);
    if (!Number.isFinite(cur) || !Number.isFinite(d) || d <= 0) continue;
    if (!Number.isFinite(r) || r < 0) r = 0;
    r = Math.min(r, 1000);
    for (let i = 0; i <= r; i++) {
      out.push({ t: cur, d, scale });
      cur += d;
    }
  }
  return out;
}

function absoluteBase(xml, mpdUrl) {
  const b = String(xml).match(/<BaseURL>([^<]+)<\/BaseURL>/i);
  return b ? new URL(b[1].trim(), mpdUrl).href : mpdUrl.replace(/[^/]+$/, '');
}

function parseTrack(aset, base) {
  const rep = firstTag(aset.body, 'Representation');
  const st = firstTag(aset.body, 'SegmentTemplate');
  if (!rep || !st) return null;
  const repId = rep.attrs.id;
  const media = st.attrs.media;
  const init = st.attrs.initialization;
  if (!repId || !media || !init) return null;

  const all = timelineSegments(st);
  if (!all.length) return null;
  const keep = 18;
  const startIndex = Math.max(0, all.length - keep);
  const chosen = all.slice(startIndex);
  const startNumber = Number(st.attrs.startNumber || 1);
  const usesNumber = media.includes('$Number$');
  const usesTime = media.includes('$Time$');

  const segments = chosen.map((s, j) => {
    const absoluteIndex = startIndex + j;
    let name = media.replaceAll('$RepresentationID$', repId);
    if (usesTime) name = name.replaceAll('$Time$', String(Math.trunc(s.t)));
    if (usesNumber) name = name.replaceAll('$Number$', String(Math.trunc(startNumber + absoluteIndex)));
    return { url: new URL(name, base).href, duration: s.d / s.scale, t: s.t, d: s.d };
  });

  let sequence;
  if (usesNumber) sequence = Math.trunc(startNumber + startIndex);
  else {
    const first = chosen[0];
    sequence = Math.max(0, Math.trunc(first.t / first.d));
  }

  const initName = init.replaceAll('$RepresentationID$', repId);
  return {
    rep: rep.attrs,
    init: new URL(initName, base).href,
    segments,
    sequence,
  };
}

async function loadChannel(sourceName) {
  const mpdUrl = `${NS}${sourceName}/dash.mpd`;
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), 7000);
  try {
    const r = await fetch(mpdUrl, {
      headers: { 'User-Agent': UA, Accept: 'application/dash+xml,application/xml,text/xml,*/*' },
      cache: 'no-store', redirect: 'follow', signal: ctrl.signal,
    });
    if (!r.ok) throw new Error(`MPD HTTP ${r.status}`);
    const xml = await r.text();
    const base = absoluteBase(xml, mpdUrl);
    let video = null, audio = null;
    for (const aset of adaptationSets(xml)) {
      const rep = firstTag(aset.body, 'Representation');
      const type = String(aset.attrs.contentType || '').toLowerCase();
      const mime = String((rep && rep.attrs.mimeType) || aset.attrs.mimeType || '').toLowerCase();
      const track = parseTrack(aset, base);
      if (!track) continue;
      if (!video && (type === 'video' || mime.startsWith('video/'))) video = track;
      if (!audio && (type === 'audio' || mime.startsWith('audio/'))) audio = track;
    }
    if (!video) throw new Error('video track not found');
    return { video, audio, mpdUrl };
  } finally {
    clearTimeout(timer);
  }
}

function mediaPlaylist(track) {
  const maxDuration = Math.max(...track.segments.map(s => s.duration));
  const target = Math.max(3, Math.ceil(maxDuration));
  const lines = [
    '#EXTM3U',
    '#EXT-X-VERSION:7',
    `#EXT-X-TARGETDURATION:${target}`,
    `#EXT-X-MEDIA-SEQUENCE:${track.sequence}`,
    `#EXT-X-MAP:URI="${track.init}"`,
  ];
  for (const s of track.segments) {
    lines.push(`#EXTINF:${s.duration.toFixed(6)},`);
    lines.push(s.url);
  }
  return `${lines.join('\n')}\n`;
}

function masterPlaylist(video, audio, ch) {
  const vbw = Number(video.rep.bandwidth || 4000000);
  const abw = Number((audio && audio.rep.bandwidth) || 0);
  const w = video.rep.width || '1920';
  const h = video.rep.height || '1080';
  const vc = video.rep.codecs || 'avc1.640028';
  const ac = (audio && audio.rep.codecs) || 'mp4a.40.2';
  const q = encodeURIComponent(ch);
  const lines = ['#EXTM3U', '#EXT-X-VERSION:7', '#EXT-X-INDEPENDENT-SEGMENTS'];
  if (audio) {
    lines.push(`#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aud",NAME="stereo",DEFAULT=YES,AUTOSELECT=YES,URI="?ch=${q}&kind=audio"`);
    lines.push(`#EXT-X-STREAM-INF:BANDWIDTH=${vbw + abw},RESOLUTION=${w}x${h},CODECS="${vc},${ac}",AUDIO="aud"`);
  } else {
    lines.push(`#EXT-X-STREAM-INF:BANDWIDTH=${vbw},RESOLUTION=${w}x${h},CODECS="${vc}"`);
  }
  lines.push(`?ch=${q}&kind=video`);
  return `${lines.join('\n')}\n`;
}

function resolveChannel(raw) {
  const key = String(raw || '').trim();
  if (CHANNELS[key]) return { key, source: CHANNELS[key] };
  if (/^hc_[a-z0-9_]+$/i.test(key) && Object.values(CHANNELS).includes(key)) {
    const alias = Object.entries(CHANNELS).find(([, v]) => v === key)?.[0] || key;
    return { key: alias, source: key };
  }
  return null;
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0');
  res.setHeader('Pragma', 'no-cache');

  const selected = resolveChannel(req.query.ch || req.query.channel);
  if (!selected) {
    res.status(400).json({ ok: false, error: 'unknown channel', channels: Object.keys(CHANNELS) });
    return;
  }

  try {
    const data = await loadChannel(selected.source);
    const kind = String(req.query.kind || 'master').toLowerCase();
    if (String(req.query.debug || '') === '1') {
      res.status(200).json({
        ok: true, channel: selected.key, source: selected.source, mpd: data.mpdUrl,
        video: { rep: data.video.rep, segments: data.video.segments.length, sequence: data.video.sequence },
        audio: data.audio ? { rep: data.audio.rep, segments: data.audio.segments.length, sequence: data.audio.sequence } : null,
      });
      return;
    }

    res.setHeader('Content-Type', 'application/vnd.apple.mpegurl; charset=utf-8');
    if (kind === 'video') res.status(200).send(mediaPlaylist(data.video));
    else if (kind === 'audio') {
      if (!data.audio) res.status(404).send('#EXTM3U\n# audio track not found\n');
      else res.status(200).send(mediaPlaylist(data.audio));
    } else res.status(200).send(masterPlaylist(data.video, data.audio, selected.key));
  } catch (e) {
    res.status(502).setHeader('Content-Type', 'application/vnd.apple.mpegurl; charset=utf-8');
    res.end(`#EXTM3U\n# Ehime CATV gateway error: ${String(e && e.message || e).replace(/[\r\n]+/g, ' ')}\n`);
  }
}
