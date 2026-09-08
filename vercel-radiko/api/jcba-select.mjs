const UA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1';

const STATIONS = {
  FM845: 'kyotoribingufm',
  BARIBARI: 'fmradiobaribari',
};

export default async function handler(req, res) {
  res.setHeader('Cache-Control', 'no-store, max-age=0');
  res.setHeader('Access-Control-Allow-Origin', '*');

  if (req.method !== 'GET') {
    res.status(405).json({ ok: false, error: 'method_not_allowed' });
    return;
  }

  const station = String(req.query?.station || '').toUpperCase();
  const slug = STATIONS[station];
  if (!slug) {
    res.status(400).json({ ok: false, error: 'unsupported_station' });
    return;
  }

  const params = new URLSearchParams({
    station: slug,
    channel: '0',
    quality: 'high',
    burst: '5',
  });

  try {
    const upstream = await fetch(`https://www.jcbasimul.com/api/select_stream?${params.toString()}`, {
      headers: {
        'User-Agent': UA,
        'Accept': 'application/json,*/*',
        'Referer': `https://www.jcbasimul.com/${slug}/rawplayer`,
      },
      cache: 'no-store',
    });

    const text = await upstream.text();
    let payload;
    try {
      payload = JSON.parse(text);
    } catch {
      throw new Error(`invalid_json_http_${upstream.status}`);
    }

    const location = String(payload?.location || '').trim();
    const token = String(payload?.token || '').trim();
    if (!upstream.ok || Number(payload?.code || 0) !== 200 || !location.startsWith('wss://') || !token) {
      throw new Error(`select_stream_failed_http_${upstream.status}_code_${payload?.code ?? 'none'}`);
    }

    res.status(200).json({
      ok: true,
      station,
      location,
      token,
      via: 'vercel-kix1',
    });
  } catch (error) {
    console.error('[jcba-select]', station, error?.message || error);
    res.status(502).json({
      ok: false,
      station,
      error: String(error?.message || error),
      via: 'vercel-kix1',
    });
  }
}
