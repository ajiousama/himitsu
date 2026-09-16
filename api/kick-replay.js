const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36";
const RESOLVER_VERSION = "2026-09-16-kick-replay-v1";

function findM3u8(value) {
  if (!value) return null;
  if (typeof value === "string") {
    return /^https?:\/\//i.test(value) && value.includes(".m3u8") ? value : null;
  }
  if (Array.isArray(value)) {
    for (const item of value) {
      const hit = findM3u8(item);
      if (hit) return hit;
    }
    return null;
  }
  if (typeof value === "object") {
    for (const key of ["source", "playback_url", "playbackUrl", "hls_url", "hlsUrl", "stream_url", "streamUrl"]) {
      const hit = findM3u8(value[key]);
      if (hit) return hit;
    }
    for (const item of Object.values(value)) {
      const hit = findM3u8(item);
      if (hit) return hit;
    }
  }
  return null;
}

async function getJson(url) {
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const r = await fetch(url, {
        headers: {
          accept: "application/json, text/plain, */*",
          "user-agent": UA,
          referer: "https://kick.com/",
          "cache-control": "no-cache",
          pragma: "no-cache"
        },
        cache: "no-store"
      });
      if (r.ok) {
        try { return await r.json(); } catch {}
      }
    } catch {}
    if (attempt < 2) await new Promise(r => setTimeout(r, 300 * (attempt + 1)));
  }
  return null;
}

module.exports = async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store, max-age=0");
  res.setHeader("Pragma", "no-cache");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("X-Kick-Replay-Resolver-Version", RESOLVER_VERSION);

  const vod = String(req.query?.vod || "").trim();
  if (!/^[A-Za-z0-9_-]{6,120}$/.test(vod)) {
    return res.status(400).json({ error: "invalid KICK VOD id", resolver: RESOLVER_VERSION });
  }

  const data = await getJson("https://kick.com/api/v1/video/" + encodeURIComponent(vod));
  if (!data) {
    return res.status(404).json({ error: "KICK VOD metadata unavailable", vod, resolver: RESOLVER_VERSION });
  }

  const source = findM3u8(data);
  if (!source) {
    return res.status(410).json({ error: "KICK VOD media unavailable", vod, resolver: RESOLVER_VERSION });
  }

  res.setHeader("X-Kick-VOD-Id", vod);
  return res.redirect(302, source);
};
