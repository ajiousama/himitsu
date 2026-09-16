const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36";
const RESOLVER_VERSION = "2026-09-16-kick-replay-v2-start";

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

async function getText(url) {
  const r = await fetch(url, {
    headers: {
      accept: "application/vnd.apple.mpegurl, application/x-mpegURL, text/plain, */*",
      "user-agent": UA,
      referer: "https://kick.com/"
    },
    cache: "no-store"
  });
  if (!r.ok) throw new Error(`HLS fetch failed ${r.status}`);
  return await r.text();
}

function absolute(base, value) {
  try { return new URL(value, base).toString(); } catch { return value; }
}

function rewritePlaylist(text, source, startSeconds) {
  const out = [];
  const lines = String(text || "").replace(/\r/g, "").split("\n");
  let inserted = false;

  for (let line of lines) {
    if (!inserted && line.startsWith("#EXTM3U")) {
      out.push(line);
      out.push(`#EXT-X-START:TIME-OFFSET=${startSeconds},PRECISE=YES`);
      inserted = true;
      continue;
    }

    if (line.startsWith("#")) {
      line = line.replace(/URI="([^"]+)"/g, (_, uri) => `URI="${absolute(source, uri)}"`);
      out.push(line);
      continue;
    }

    if (line.trim()) out.push(absolute(source, line.trim()));
    else out.push(line);
  }

  if (!inserted) out.unshift(`#EXT-X-START:TIME-OFFSET=${startSeconds},PRECISE=YES`);
  return out.join("\n");
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

  let start = Number(req.query?.start || 0);
  if (!Number.isFinite(start) || start < 0) start = 0;
  start = Math.floor(Math.min(start, 7 * 24 * 60 * 60));

  const data = await getJson("https://kick.com/api/v1/video/" + encodeURIComponent(vod));
  if (!data) {
    return res.status(404).json({ error: "KICK VOD metadata unavailable", vod, resolver: RESOLVER_VERSION });
  }

  const source = findM3u8(data);
  if (!source) {
    return res.status(410).json({ error: "KICK VOD media unavailable", vod, resolver: RESOLVER_VERSION });
  }

  res.setHeader("X-Kick-VOD-Id", vod);
  res.setHeader("X-Kick-Replay-Start", String(start));

  if (!start) return res.redirect(302, source);

  try {
    const playlist = await getText(source);
    const rewritten = rewritePlaylist(playlist, source, start);
    res.setHeader("Content-Type", "application/vnd.apple.mpegurl; charset=utf-8");
    return res.status(200).send(rewritten);
  } catch (e) {
    return res.status(502).json({
      error: "KICK VOD seek playlist failed",
      vod,
      start,
      detail: String(e?.message || e),
      resolver: RESOLVER_VERSION
    });
  }
};
