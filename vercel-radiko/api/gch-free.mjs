const GCH_PAGE = 'https://sp.gch.jp/jra';
const PLAYER_ORIGIN = 'https://players.streaks.jp';
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36';

function sendJson(res, status, obj) {
  res.statusCode = status;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');
  res.end(JSON.stringify(obj));
}

function parsePlayer(html) {
  const re = /<iframe[^>]+src=["'](https:\/\/players\.streaks\.jp\/([\w-]+)\/([0-9a-f]+)\/index\.html\?[^"']*\bm=([^&"']+)[^"']*)["']/i;
  const m = html.match(re);
  if (!m) return null;
  return {
    playerUrl: m[1].replaceAll('&amp;', '&'),
    projectId: m[2],
    apiKey: m[3],
    mediaId: decodeURIComponent(m[4].replaceAll('&amp;', '&')),
  };
}

async function fetchJson(url, init = {}) {
  const r = await fetch(url, { redirect: 'follow', cache: 'no-store', ...init });
  const text = await r.text();
  let data = null;
  try { data = JSON.parse(text); } catch {}
  return { r, text, data };
}

function chooseHlsSource(playback) {
  const sources = Array.isArray(playback?.sources) ? playback.sources : [];
  return sources.find((s) => {
    const src = typeof s?.src === 'string' ? s.src : '';
    const drm = s?.key_systems && Object.keys(s.key_systems).length > 0;
    return src.includes('.m3u8') && !drm;
  }) || null;
}

function hasSsai(playback) {
  const sources = Array.isArray(playback?.sources) ? playback.sources : [];
  return sources.some((s) => s && typeof s.ssai === 'object' && s.ssai !== null);
}

function appendQuery(url, query) {
  const u = new URL(url);
  if (typeof query === 'string') {
    const qs = new URLSearchParams(query);
    for (const [k, v] of qs) u.searchParams.set(k, v);
  } else if (query && typeof query === 'object') {
    for (const [k, v] of Object.entries(query)) {
      if (Array.isArray(v)) {
        for (const item of v) u.searchParams.append(k, String(item));
      } else if (v != null) {
        u.searchParams.set(k, String(v));
      }
    }
  }
  return u.toString();
}

async function resolveFreeHls() {
  const pageRes = await fetch(GCH_PAGE, {
    headers: {
      'User-Agent': UA,
      'Accept-Language': 'ja,en-US;q=0.9,en;q=0.8',
      Referer: GCH_PAGE,
    },
    cache: 'no-store',
  });
  const html = await pageRes.text();
  if (!pageRes.ok) return { ok: false, stage: 'page', status: pageRes.status };

  const player = parsePlayer(html);
  if (!player) return { ok: false, stage: 'player', status: 404 };

  const playbackUrl = `https://playback.api.streaks.jp/v1/projects/${encodeURIComponent(player.projectId)}/medias/${encodeURIComponent(player.mediaId)}`;
  const playbackResult = await fetchJson(playbackUrl, {
    headers: {
      'User-Agent': UA,
      Accept: 'application/json',
      Origin: PLAYER_ORIGIN,
      Referer: player.playerUrl,
      'X-Streaks-Api-Key': player.apiKey,
    },
  });

  if (!playbackResult.r.ok || !playbackResult.data) {
    return {
      ok: false,
      stage: 'playback',
      status: playbackResult.r.status,
      streaksCode: playbackResult.data?.code ?? null,
      streaksId: playbackResult.data?.id ?? null,
      message: playbackResult.data?.message ?? null,
      projectId: player.projectId,
      mediaId: player.mediaId,
    };
  }

  const playback = playbackResult.data;
  const source = chooseHlsSource(playback);
  if (!source) {
    return {
      ok: false,
      stage: 'source',
      status: 404,
      projectId: player.projectId,
      mediaId: player.mediaId,
      playbackType: playback?.type ?? null,
      sourceCount: Array.isArray(playback?.sources) ? playback.sources.length : 0,
    };
  }

  let hls = source.src;
  let ssai = false;
  if ((playback?.type === 'linear' || playback?.type === 'live') && hasSsai(playback)) {
    const streaksId = playback.id;
    const ssaiUrl = `https://ssai.api.streaks.jp/v1/projects/${encodeURIComponent(player.projectId)}/medias/${encodeURIComponent(streaksId)}/ssai/session`;
    const sessionResult = await fetchJson(ssaiUrl, {
      method: 'POST',
      headers: {
        'User-Agent': UA,
        'Content-Type': 'application/json',
        Accept: 'application/json',
        Origin: PLAYER_ORIGIN,
        Referer: player.playerUrl,
        'X-Streaks-Api-Key': player.apiKey,
      },
      body: JSON.stringify({ id: source.id }),
    });
    if (!sessionResult.r.ok || !sessionResult.data) {
      return { ok: false, stage: 'ssai', status: sessionResult.r.status, message: sessionResult.data?.message ?? null };
    }
    const session = Array.isArray(sessionResult.data) ? sessionResult.data[0] : sessionResult.data;
    hls = appendQuery(hls, session?.query ?? null);
    ssai = true;
  }

  return {
    ok: true,
    hls,
    page: GCH_PAGE,
    projectId: player.projectId,
    mediaId: player.mediaId,
    playbackId: playback?.id ?? null,
    playbackType: playback?.type ?? null,
    ssai,
  };
}

export default async function handler(req, res) {
  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.statusCode = 405;
    res.setHeader('Allow', 'GET, HEAD');
    return res.end('Method Not Allowed');
  }

  try {
    const result = await resolveFreeHls();
    const probe = req.query?.probe === '1' || req.query?.probe === 'true';
    const raw = req.query?.raw === '1' || req.query?.raw === 'true';

    if (raw) {
      if (!result.ok) return sendJson(res, result.status || 502, result);
      return sendJson(res, 200, result);
    }

    if (probe) {
      const safe = { ...result };
      if (safe.hls) safe.hls = 'resolved';
      return sendJson(res, result.ok ? 200 : (result.status || 502), safe);
    }

    if (!result.ok) {
      return sendJson(res, result.status || 502, {
        ok: false,
        stage: result.stage,
        status: result.status ?? null,
        streaksCode: result.streaksCode ?? null,
        streaksId: result.streaksId ?? null,
        message: result.message ?? null,
      });
    }

    res.statusCode = 302;
    res.setHeader('Location', result.hls);
    res.setHeader('Cache-Control', 'no-store, max-age=0');
    res.setHeader('X-GCH-Source', 'official-free-1ch');
    return res.end();
  } catch (e) {
    return sendJson(res, 500, { ok: false, stage: 'exception', message: String(e?.message || e) });
  }
}
