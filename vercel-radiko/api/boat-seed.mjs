const VENUES = {
  '01': '01kiryu', '02': '02toda', '03': '03edogawa', '04': '04heiwajima',
  '05': '05tamagawa', '06': '06hamanako', '07': '07gamagori', '08': '08tokoname',
  '09': '09tsu', '10': '10mikuni', '11': '11biwako', '12': '12suminoe',
  '13': '13amagasaki', '14': '14naruto', '15': '15marugame', '16': '16kojima',
  '17': '17miyajima', '18': '18tokuyama', '19': '19shimonoseki', '20': '20wakamatsu',
  '21': '21ashiya', '22': '22fukuoka', '23': '23karatsu', '24': '24omura',
};

const UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1';
const BASE_HEADERS = {
  'Origin': 'https://front.player.boatrace-cdn.jp',
  'Referer': 'https://front.player.boatrace-cdn.jp/',
  'User-Agent': UA,
  'Accept': 'application/json,*/*',
};

function jstYmd() {
  return new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Tokyo', year: 'numeric', month: '2-digit', day: '2-digit'
  }).format(new Date()).replaceAll('-', '');
}

function normalizeVenue(value) {
  const n = Number(String(value || '').match(/\d{1,2}/)?.[0] || 0);
  if (n < 1 || n > 24) return '';
  return String(n).padStart(2, '0');
}

async function timedFetch(url, options = {}, timeoutMs = 6500) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, cache: 'no-store', redirect: 'follow', signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Cache-Control', 'no-store, max-age=0');

  const jcd = normalizeVenue(req.query?.venue || req.query?.jcd);
  const streamMode = ['1', 'true', 'hls'].includes(
    String(req.query?.stream || req.query?.format || '').toLowerCase()
  );
  const code = VENUES[jcd];
  if (!code) {
    res.status(400).json({ ok: false, error: 'venue must be 01-24' });
    return;
  }

  const ymd = /^\d{8}$/.test(String(req.query?.date || '')) ? String(req.query.date) : jstYmd();
  const attempts = [];

  try {
    const setting = `https://front.player.boatrace-cdn.jp/setting/live/${code}/setting.json?t=${Date.now()}`;
    try {
      const r = await timedFetch(setting, { headers: BASE_HEADERS }, 2500);
      attempts.push({ stage: 'setting', status: r.status });
    } catch (error) {
      attempts.push({ stage: 'setting', error: `${error?.name || 'Error'}:${error?.message || error}` });
    }

    const playback = `https://playback.api.streaks.jp/v1/projects/cp-boatrace-prod/medias/ref:lm-br-${code}-tokyo-${ymd}?audio_only=false`;
    const r = await timedFetch(playback, { headers: BASE_HEADERS }, 6500);
    const text = await r.text();
    attempts.push({ stage: 'playback', status: r.status });

    if (!r.ok) {
      res.status(502).json({ ok: false, venue: jcd, date: ymd, region: process.env.VERCEL_REGION || null, attempts });
      return;
    }

    let data = {};
    try { data = JSON.parse(text); } catch (_) {}
    const hit = (Array.isArray(data?.sources) ? data.sources : [])
      .map(x => (x && typeof x === 'object' ? String(x.src || '') : ''))
      .find(x => x.startsWith('https://manifest.streaks.jp/') && x.includes('.m3u8')) || '';

    if (!hit) {
      res.status(404).json({ ok: false, venue: jcd, date: ymd, region: process.env.VERCEL_REGION || null, attempts, error: 'no Streaks HLS source' });
      return;
    }

    if (streamMode) {
      const playlistResponse = await timedFetch(hit, {
        headers: {
          ...BASE_HEADERS,
          'Accept': 'application/vnd.apple.mpegurl,application/x-mpegURL,*/*',
        },
      }, 6500);
      const playlist = await playlistResponse.text();
      attempts.push({ stage: 'manifest', status: playlistResponse.status });

      res.setHeader('Content-Type', 'application/vnd.apple.mpegurl; charset=utf-8');
      res.setHeader('X-BOAT-Venue', jcd);
      if (!playlistResponse.ok || !playlist.trimStart().startsWith('#EXTM3U')) {
        res.status(502).send('#EXTM3U\n# BOAT stream unavailable\n');
        return;
      }
      res.status(200).send(playlist);
      return;
    }

    res.status(200).json({ ok: true, venue: jcd, date: ymd, region: process.env.VERCEL_REGION || null, url: hit, attempts });
  } catch (error) {
    res.status(502).json({
      ok: false,
      venue: jcd,
      date: ymd,
      region: process.env.VERCEL_REGION || null,
      error: `${error?.name || 'Error'}:${error?.message || String(error)}`,
      attempts,
    });
  }
}
