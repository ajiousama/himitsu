const CHANNELS = {
  gccx: 'mirumo-ch',
  nogizaka: 'nogi20110821',
};

const UA =
  'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151 Safari/537.36';

function normalize(value) {
  return String(value || '')
    .replaceAll('\\/', '/')
    .replaceAll('\\u0026', '&')
    .replaceAll('\\u002F', '/');
}

function collectM3u8(value, out = []) {
  if (Array.isArray(value)) {
    for (const v of value) collectM3u8(v, out);
    return out;
  }
  if (value && typeof value === 'object') {
    for (const v of Object.values(value)) collectM3u8(v, out);
    return out;
  }
  if (typeof value === 'string') {
    const v = normalize(value);
    if (v.startsWith('https://') && v.includes('.m3u8')) out.push(v);
  }
  return out;
}

function jwtRemainingSeconds(url) {
  try {
    const token = new URL(url).searchParams.get('token');
    if (!token) return null;
    const parts = token.split('.');
    if (parts.length < 2) return null;
    const b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const padded = b64 + '='.repeat((4 - (b64.length % 4)) % 4);
    const payload = JSON.parse(Buffer.from(padded, 'base64').toString('utf8'));
    if (!payload.exp) return null;
    return Number(payload.exp) - Math.floor(Date.now() / 1000);
  } catch {
    return null;
  }
}

async function getJson(url, slug) {
  const r = await fetch(url, {
    headers: {
      'User-Agent': UA,
      Accept: 'application/json,text/plain,*/*',
      Referer: `https://kick.com/${slug}`,
      Origin: 'https://kick.com',
      'Cache-Control': 'no-cache, no-store, max-age=0',
      Pragma: 'no-cache',
    },
    cache: 'no-store',
    redirect: 'follow',
  });
  if (!r.ok) return { status: r.status, data: null };
  try {
    return { status: r.status, data: await r.json() };
  } catch {
    return { status: r.status, data: null };
  }
}

export default async function handler(req, res) {
  const key = String(req.query?.ch || '').toLowerCase();
  const slug = CHANNELS[key];
  if (!slug) {
    res.status(400).json({ ok: false, error: 'unknown channel' });
    return;
  }

  const nonce = `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  const endpoints = [
    `https://kick.com/api/v2/channels/${slug}/playback-url?refresh=${nonce}`,
    `https://kick.com/api/v2/channels/${slug}?refresh=${nonce}-1`,
    `https://kick.com/api/v2/channels/${slug}/livestream?refresh=${nonce}-2`,
    `https://kick.com/api/v1/channels/${slug}?refresh=${nonce}-3`,
  ];

  const errors = [];
  const candidates = [];

  for (const endpoint of endpoints) {
    try {
      const { status, data } = await getJson(endpoint, slug);
      if (!data) {
        errors.push(`${new URL(endpoint).pathname}: HTTP ${status}`);
        continue;
      }
      for (const url of collectM3u8(data)) candidates.push(url);
    } catch (error) {
      errors.push(`${new URL(endpoint).pathname}: ${error?.message || error}`);
    }
  }

  const unique = [...new Set(candidates)];
  unique.sort((a, b) => (jwtRemainingSeconds(b) ?? -1) - (jwtRemainingSeconds(a) ?? -1));

  const fresh = unique.find((url) => {
    const remain = jwtRemainingSeconds(url);
    return remain == null || remain > 60;
  });

  if (!fresh) {
    res.setHeader('Cache-Control', 'no-store, max-age=0');
    res.status(503).json({
      ok: false,
      channel: key,
      slug,
      error: 'fresh KICK playback URL unavailable',
      candidates: unique.length,
      details: errors.slice(-6),
    });
    return;
  }

  res.setHeader('Cache-Control', 'no-store, max-age=0');
  res.setHeader('Location', fresh);
  res.status(302).end();
}
