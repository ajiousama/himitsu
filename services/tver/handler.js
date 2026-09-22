const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36";
const VERSION = "2026-09-19-tver-v1";

async function j(url, opts = {}) {
  const r = await fetch(url, {
    ...opts,
    headers: {
      accept: "application/json, text/plain, */*",
      "user-agent": UA,
      ...(opts.headers || {})
    },
    cache: "no-store"
  });
  if (!r.ok) throw new Error(`JSON ${r.status} ${url}`);
  return r.json();
}

async function t(url) {
  const r = await fetch(url, {
    headers: {
      accept: "application/vnd.apple.mpegurl, application/x-mpegURL, text/plain, */*",
      "user-agent": UA,
      origin: "https://tver.jp",
      referer: "https://tver.jp/",
      "cache-control": "no-cache"
    },
    cache: "no-store"
  });
  if (!r.ok) throw new Error(`HLS ${r.status}`);
  return r.text();
}

function abs(base, value) {
  try { return new URL(value, base).toString(); } catch { return value; }
}

function pickVariant(text, source) {
  const lines = String(text || "").replace(/\r/g, "").split("\n");
  const variants = [];
  for (let i = 0; i < lines.length; i++) {
    if (!lines[i].startsWith("#EXT-X-STREAM-INF:")) continue;
    const bw = Number((lines[i].match(/BANDWIDTH=(\d+)/i) || [])[1] || 0);
    for (let k = i + 1; k < lines.length; k++) {
      const x = lines[k].trim();
      if (!x) continue;
      if (x.startsWith("#")) break;
      variants.push({ bw, url: abs(source, x) });
      break;
    }
  }
  variants.sort((a, b) => b.bw - a.bw);
  return variants[0]?.url || null;
}

function rewrite(text, source) {
  return String(text || "").replace(/\r/g, "").split("\n").map(line => {
    if (line.startsWith("#")) {
      return line.replace(/URI="([^"]+)"/g, (_, x) => `URI="${abs(source, x)}"`);
    }
    return line.trim() ? abs(source, line.trim()) : line;
  }).join("\n");
}

function playableSource(sources) {
  if (!sources) return null;
  const arr = Array.isArray(sources) ? sources : [sources];
  for (const s of arr) {
    if (!s || typeof s !== "object") continue;
    if (s.key_systems) continue;
    if (typeof s.src === "string" && (
      s.src.includes(".m3u8") ||
      String(s.type || "").includes("mpegurl") ||
      String(s.type || "").includes("m3u8")
    )) return s.src;
  }
  for (const s of arr) {
    if (Array.isArray(s)) {
      const hit = playableSource(s);
      if (hit) return hit;
    } else if (s && typeof s === "object") {
      const hit = playableSource(Object.values(s));
      if (hit) return hit;
    }
  }
  return null;
}

function currentKeyName() {
  const d = new Date(Date.now() + 9 * 3600 * 1000);
  const month = d.getUTCMonth() + 1;
  const n = month % 6 || 6;
  return `key0${n}`;
}

module.exports = async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store, max-age=0");
  res.setHeader("Pragma", "no-cache");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("X-TVer-Resolver-Version", VERSION);
  res.setHeader("X-Vercel-Region", process.env.VERCEL_REGION || "unknown");

  const ep = String(req.query?.ep || "").trim();
  if (!/^[A-Za-z0-9]{6,40}$/.test(ep)) {
    return res.status(400).json({ error: "invalid TVer episode id", resolver: VERSION });
  }

  try {
    const meta = await j(
      `https://statics.tver.jp/content/episode/${encodeURIComponent(ep)}.json?v=1`,
      { headers: { referer: "https://tver.jp/" } }
    );

    const project = meta?.streaks?.projectID;
    const ref = meta?.streaks?.videoRefID;
    if (!project || !ref) throw new Error("STREAKS metadata missing");

    const info = await j("https://player.tver.jp/player/streaks_info_v2.json", {
      headers: { referer: "https://tver.jp/" }
    });
    const apiKey = info?.[project]?.api_key?.[currentKeyName()];
    if (!apiKey) throw new Error("STREAKS API key missing");

    const mediaId = String(ref).startsWith("ref:") ? String(ref) : `ref:${ref}`;
    const playback = await j(
      `https://playback.api.streaks.jp/v1/projects/${encodeURIComponent(project)}/medias/${encodeURIComponent(mediaId)}`,
      {
        headers: {
          origin: "https://tver.jp",
          referer: "https://tver.jp/",
          "x-streaks-api-key": apiKey
        }
      }
    );

    let media = playableSource(playback?.sources);
    if (!media) throw new Error("HLS source missing");

    let playlist = await t(media);
    for (let depth = 0; depth < 3 && /#EXT-X-STREAM-INF:/i.test(playlist); depth++) {
      const next = pickVariant(playlist, media);
      if (!next) throw new Error("master playlist has no variant");
      media = next;
      playlist = await t(media);
    }
    if (/#EXT-X-STREAM-INF:/i.test(playlist)) throw new Error("nested master too deep");

    res.setHeader("Content-Type", "application/vnd.apple.mpegurl; charset=utf-8");
    res.setHeader("X-TVer-Project", project);
    res.setHeader("X-TVer-Media", mediaId);
    return res.status(200).send(rewrite(playlist, media));
  } catch (e) {
    return res.status(502).json({
      error: "TVer playback unavailable",
      ep,
      region: process.env.VERCEL_REGION || "unknown",
      detail: String(e?.message || e),
      resolver: VERSION
    });
  }
};
