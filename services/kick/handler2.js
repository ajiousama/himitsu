const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36";
const SLUG = "joshua-hkd";
const VERSION = "2026-09-10-gccx2-dedicated-v1";

async function getJson(url) {
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const r = await fetch(url, {
        headers: {
          accept: "application/json, text/plain, */*",
          "user-agent": UA,
          referer: "https://kick.com/"
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

function findPlayback(value) {
  if (!value) return null;
  if (typeof value === "string") {
    if (/^https?:\/\/.+\.m3u8(?:\?|$)/i.test(value)) return value;
    return null;
  }
  if (Array.isArray(value)) {
    for (const v of value) {
      const hit = findPlayback(v);
      if (hit) return hit;
    }
    return null;
  }
  if (typeof value === "object") {
    const direct = value.playback_url || value.playbackUrl || value.hls_url || value.hlsUrl || value.stream_url || value.streamUrl;
    if (typeof direct === "string" && direct.includes(".m3u8")) return direct;
    for (const v of Object.values(value)) {
      const hit = findPlayback(v);
      if (hit) return hit;
    }
  }
  return null;
}

module.exports = async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store, max-age=0");
  res.setHeader("Pragma", "no-cache");
  res.setHeader("X-Kick2-Resolver-Version", VERSION);

  try {
    const data = await getJson("https://kick.com/api/v2/channels/" + encodeURIComponent(SLUG));
    if (!data) return res.status(503).json({ error: "KICK channel lookup failed", slug: SLUG, resolver: VERSION });

    const playback = findPlayback(data);
    if (!playback) return res.status(503).json({ error: "KICK live playback unavailable", slug: SLUG, resolver: VERSION });

    res.setHeader("X-Kick-Resolved-Slug", data.slug || SLUG);
    return res.redirect(302, playback);
  } catch (e) {
    return res.status(502).json({ error: "KICK resolver failed", detail: String(e?.message || e), resolver: VERSION });
  }
};
