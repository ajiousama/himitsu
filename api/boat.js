const VENUES = {
  '01': { code: '01kiryu', slug: 'kiryu' },
  '02': { code: '02toda', slug: 'toda' },
  '03': { code: '03edogawa', slug: 'edogawa' },
  '04': { code: '04heiwajima', slug: 'heiwajima' },
  '05': { code: '05tamagawa', slug: 'tamagawa' },
  '06': { code: '06hamanako', slug: 'hamanako' },
  '07': { code: '07gamagori', slug: 'gamagori' },
  '08': { code: '08tokoname', slug: 'tokoname' },
  '09': { code: '09tsu', slug: 'tsu' },
  '10': { code: '10mikuni', slug: 'mikuni' },
  '11': { code: '11biwako', slug: 'biwako' },
  '12': { code: '12suminoe', slug: 'suminoe' },
  '13': { code: '13amagasaki', slug: 'amagasaki' },
  '14': { code: '14naruto', slug: 'naruto' },
  '15': { code: '15marugame', slug: 'marugame' },
  '16': { code: '16kojima', slug: 'kojima' },
  '17': { code: '17miyajima', slug: 'miyajima' },
  '18': { code: '18tokuyama', slug: 'tokuyama' },
  '19': { code: '19shimonoseki', slug: 'shimonoseki' },
  '20': { code: '20wakamatsu', slug: 'wakamatsu' },
  '21': { code: '21ashiya', slug: 'ashiya' },
  '22': { code: '22fukuoka', slug: 'fukuoka' },
  '23': { code: '23karatsu', slug: 'karatsu' },
  '24': { code: '24omura', slug: 'omura' },
};

const UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1';

function todayJst() {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Tokyo', year: 'numeric', month: '2-digit', day: '2-digit'
  }).formatToParts(new Date());
  const obj = Object.fromEntries(parts.map(p => [p.type, p.value]));
  return `${obj.year}${obj.month}${obj.day}`;
}

function normalizeVenue(v) {
  const m = String(v || '').match(/(?:^|\D)(\d{1,2})(?:\D|$)/);
  if (!m) return '';
  return String(Number(m[1])).padStart(2, '0');
}

function decodeEscapes(s) {
  return String(s || '')
    .replace(/\\u0026/gi, '&')
    .replace(/\\x26/gi, '&')
    .replace(/\\\//g, '/')
    .replace(/&amp;/g, '&');
}

function m3u8Candidates(text, base) {
  const decoded = decodeEscapes(text);
  const out = [];
  const push = raw => {
    if (!raw) return;
    try {
      const u = new URL(raw, base).href;
      if (/\.m3u8(?:$|[?#])/i.test(u) && !out.includes(u)) out.push(u);
    } catch (_) {}
  };
  for (const m of decoded.matchAll(/https?:\/\/[^\s"'<>]+?\.m3u8(?:\?[^\s"'<>]*)?/ig)) push(m[0]);
  for (const m of decoded.matchAll(/["']([^"']+?\.m3u8(?:\?[^"']*)?)["']/ig)) push(m[1]);
  return out;
}

async function fetchText(url, headers = {}, timeoutMs = 6000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const r = await fetch(url, { headers, cache: 'no-store', redirect: 'follow', signal: ctrl.signal });
    return { ok: r.ok, status: r.status, url: r.url, text: await r.text() };
  } finally {
    clearTimeout(timer);
  }
}

async function tryPlayback(code, ymd, attempts) {
  const url = `https://playback.api.streaks.jp/v1/projects/cp-boatrace-prod/medias/ref:lm-br-${code}-tokyo-${ymd}?audio_only=false`;
  const variants = [
    { Origin: 'https://players.streaks.jp', Referer: 'https://front.player.boatrace-cdn.jp/' },
    { Origin: 'https://front.player.boatrace-cdn.jp', Referer: 'https://front.player.boatrace-cdn.jp/' },
    { Referer: 'https://front.player.boatrace-cdn.jp/' },
  ];
  for (let i = 0; i < variants.length; i++) {
    const headers = { 'User-Agent': UA, Accept: 'application/json', ...variants[i] };
    if (process.env.BOATRACE_STREAKS_API_KEY) headers['X-Streaks-Api-Key'] = process.env.BOATRACE_STREAKS_API_KEY;
    try {
      const r = await fetch(url, { headers, cache: 'no-store', redirect: 'follow' });
      const body = await r.text();
      attempts.push({ source: `streaks-${i + 1}`, status: r.status });
      if (!r.ok) continue;
      let data;
      try { data = JSON.parse(body); } catch (_) { data = null; }
      const sources = data && Array.isArray(data.sources) ? data.sources : [];
      for (const item of sources) {
        const src = item && typeof item === 'object' ? String(item.src || '') : '';
        if (/^https?:\/\//i.test(src)) return { url: src, source: 'streaks-playback' };
      }
      const embedded = m3u8Candidates(body, url);
      if (embedded[0]) return { url: embedded[0], source: 'streaks-body' };
    } catch (e) {
      attempts.push({ source: `streaks-${i + 1}`, error: String(e && e.name || e) });
    }
  }
  return null;
}

async function tryJlc(jcd, attempts) {
  const root = `https://livebb.jlc.ne.jp/bb_top/sp_bb/live_${jcd}.php`;
  const headers = { 'User-Agent': UA, Referer: 'https://boatrace.sakura.tv/' };
  try {
    const page = await fetchText(root, headers);
    attempts.push({ source: 'jlc-mobile', status: page.status });
    if (!page.ok) return null;
    const direct = m3u8Candidates(page.text, page.url);
    if (direct[0]) return { url: direct[0], source: 'jlc-mobile' };
    const resources = [];
    for (const m of decodeEscapes(page.text).matchAll(/(?:src|href)=["']([^"']+)["']/ig)) {
      try {
        const u = new URL(m[1], page.url);
        if ((u.hostname === 'livebb.jlc.ne.jp' || /uliza/i.test(u.hostname)) && /\.(?:js|php)(?:$|\?)/i.test(u.href)) {
          if (!resources.includes(u.href)) resources.push(u.href);
        }
      } catch (_) {}
    }
    for (const u of resources.slice(0, 10)) {
      try {
        const r = await fetchText(u, headers, 4000);
        attempts.push({ source: 'jlc-resource', status: r.status, host: new URL(u).hostname });
        if (!r.ok) continue;
        const c = m3u8Candidates(r.text, r.url);
        if (c[0]) return { url: c[0], source: 'jlc-resource' };
      } catch (e) {
        attempts.push({ source: 'jlc-resource', error: String(e && e.name || e) });
      }
    }
  } catch (e) {
    attempts.push({ source: 'jlc-mobile', error: String(e && e.name || e) });
  }
  return null;
}

async function trySakura(slug, attempts) {
  const root = `https://boatrace.sakura.tv/${slug}/`;
  try {
    const page = await fetchText(root, { 'User-Agent': UA });
    attempts.push({ source: 'sakura', status: page.status });
    if (!page.ok) return null;
    const c = m3u8Candidates(page.text, page.url);
    if (c[0]) return { url: c[0], source: 'sakura' };
  } catch (e) {
    attempts.push({ source: 'sakura', error: String(e && e.name || e) });
  }
  return null;
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', 'no-store, max-age=0');
  const jcd = normalizeVenue(req.query.venue || req.query.jcd);
  const venue = VENUES[jcd];
  if (!venue) {
    res.status(400).json({ ok: false, error: 'venue must be 01-24' });
    return;
  }
  const ymd = /^\d{8}$/.test(String(req.query.date || '')) ? String(req.query.date) : todayJst();
  const attempts = [];
  let hit = await tryPlayback(venue.code, ymd, attempts);
  if (!hit) hit = await tryJlc(jcd, attempts);
  if (!hit) hit = await trySakura(venue.slug, attempts);
  if (String(req.query.debug || '') === '1') {
    res.status(hit ? 200 : 503).json({ ok: !!hit, venue: jcd, date: ymd, hit, attempts });
    return;
  }
  if (!hit) {
    res.status(503).setHeader('Content-Type', 'application/vnd.apple.mpegurl; charset=utf-8');
    res.end('#EXTM3U\n# BOAT resolver: stream is not available yet\n');
    return;
  }
  res.statusCode = 302;
  res.setHeader('Location', hit.url);
  res.setHeader('X-Boat-Resolver-Source', hit.source);
  res.end();
}
