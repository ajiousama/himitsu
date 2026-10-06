const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36";
const VERSION = "2026-10-07-tver-live-news-v2";

async function fetchText(url, headers = {}) {
  const r = await fetch(url, {
    headers: {
      accept: "text/html,application/xhtml+xml,application/json,text/plain,*/*",
      "user-agent": UA,
      referer: "https://tver.jp/",
      "cache-control": "no-cache",
      pragma: "no-cache",
      ...headers
    },
    cache: "no-store",
    redirect: "follow"
  });
  if (!r.ok) throw new Error(`HTTP ${r.status} ${url}`);
  return r.text();
}

const NEWS_SPECIAL = {
  news24: {
    label: "日テレNEWS24",
    title: /日テレNEWS24/i,
    fallback: ["le7gtytdy0"]
  },
  tbs: {
    label: "TBS NEWS DIG",
    title: /TBS\s*NEWS\s*DIG/i,
    fallback: ["le5t0u6hpv"]
  }
};

async function specialLiveMeta(id) {
  return j(`https://statics.tver.jp/content/live/${encodeURIComponent(id)}.json?v=3`, {
    headers: {
      origin: "https://tver.jp",
      referer: "https://tver.jp/"
    }
  });
}

async function discoverSpecialLiveId(kind) {
  const cfg = NEWS_SPECIAL[kind];
  if (!cfg) throw new Error("unknown news channel");

  const ids = [];
  try {
    const html = await fetchText("https://tver.jp/corner/f0048951");
    for (const m of html.matchAll(/\/live\/special\/(le[a-z0-9]+)/gi)) {
      if (!ids.includes(m[1])) ids.push(m[1]);
    }
  } catch {}

  for (const id of [...ids, ...cfg.fallback]) {
    try {
      const meta = await specialLiveMeta(id);
      const title = String(meta?.title || meta?.seriesTitle || "");
      if (cfg.title.test(title)) return { id, meta, title };
    } catch {}
  }

  throw new Error(`${cfg.label} current Special Live not found`);
}

async function resolveSpecialNews(kind) {
  const { id, title } = await discoverSpecialLiveId(kind);
  const playback = await j(
    `https://playback.api.streaks.jp/v1/projects/tver-splive/medias/ref:${encodeURIComponent(id)}`,
    {
      headers: {
        origin: "https://tver.jp",
        referer: "https://tver.jp/",
        "x-streaks-api-key": id
      }
    }
  );
  const media = playableSource(playback?.sources);
  if (!media) throw new Error("Special Live HLS source missing");
  return { id, title, media };
}

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

export default async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store, max-age=0");
  res.setHeader("Pragma", "no-cache");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("X-TVer-Resolver-Version", VERSION);
  res.setHeader("X-Vercel-Region", process.env.VERCEL_REGION || "unknown");

  const news = String(req.query?.news || "").trim().toLowerCase();
  if (news) {
    if (!NEWS_SPECIAL[news]) {
      return res.status(400).json({ error: "invalid TVer news channel", resolver: VERSION });
    }
    try {
      const live = await resolveSpecialNews(news);
      res.setHeader("X-TVer-Live-Id", live.id);
      res.setHeader("X-TVer-Live-Title", encodeURIComponent(live.title || NEWS_SPECIAL[news].label));
      res.setHeader("Location", live.media);
      return res.status(302).end();
    } catch (e) {
      return res.status(502).json({
        error: "TVer Special Live unavailable",
        news,
        detail: String(e?.message || e),
        resolver: VERSION
      });
    }
  }

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
