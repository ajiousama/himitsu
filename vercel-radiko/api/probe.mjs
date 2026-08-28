const AUTH_KEY = 'bcd151073c03b352e1ef2fd66c32209da9ca0afa';

const BASE_HEADERS = {
  'X-Radiko-App': 'pc_html5',
  'X-Radiko-App-Version': '0.0.1',
  'X-Radiko-Device': 'pc',
  'X-Radiko-User': 'dummy_user',
  'User-Agent': 'Mozilla/5.0',
};

export default async function handler(req, res) {
  try {
    const auth1 = await fetch('https://api.radiko.jp/v2/api/auth1', {
      headers: BASE_HEADERS,
      cache: 'no-store',
    });

    const token = auth1.headers.get('x-radiko-authtoken');
    const off = Number(auth1.headers.get('x-radiko-keyoffset'));
    const len = Number(auth1.headers.get('x-radiko-keylength'));

    if (!auth1.ok || !token || !Number.isFinite(off) || !Number.isFinite(len)) {
      res.status(502).json({
        ok: false,
        region: process.env.VERCEL_REGION || null,
        stage: 'auth1',
        status: auth1.status,
      });
      return;
    }

    const partial = Buffer.from(AUTH_KEY.slice(off, off + len), 'utf8').toString('base64');
    const auth2Headers = {
      ...BASE_HEADERS,
      'X-Radiko-AuthToken': token,
      'X-Radiko-PartialKey': partial,
    };

    const auth2 = await fetch('https://api.radiko.jp/v2/api/auth2', {
      headers: auth2Headers,
      cache: 'no-store',
    });
    const body = (await auth2.text()).trim();

    res.status(auth2.ok ? 200 : 502).json({
      ok: auth2.ok && /^JP\d{1,2}(,|$)/.test(body),
      region: process.env.VERCEL_REGION || null,
      auth2Status: auth2.status,
      detected: body.slice(0, 80),
    });
  } catch (error) {
    res.status(502).json({
      ok: false,
      region: process.env.VERCEL_REGION || null,
      error: `${error?.name || 'Error'}: ${error?.message || String(error)}`,
    });
  }
}
