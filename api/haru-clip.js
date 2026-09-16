const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36";
const VERSION = "2026-09-16-haru-clip-v2";

function isAllowedSource(raw) {
  try {
    const u = new URL(raw);
    return u.protocol === "https:" && u.hostname === "haru.charandom.blog" && /\/stream\/jp\/[^/]+\/replay\.m3u8$/i.test(u.pathname);
  } catch {
    return false;
  }
}

function absolute(base, value) {
  try { return new URL(value, base).toString(); } catch { return value; }
}

async function fetchText(url) {
  const r = await fetch(url, {
    headers: {
      accept: "application/vnd.apple.mpegurl,application/x-mpegURL,text/plain,*/*",
      "user-agent": UA,
      referer: "https://haru.charandom.blog/",
      "cache-control": "no-cache",
      pragma: "no-cache"
    },
    cache: "no-store"
  });
  if (!r.ok) throw new Error(`HLS fetch failed ${r.status}`);
  return await r.text();
}

function pickVariant(text, source) {
  const lines = String(text || "").replace(/\r/g, "").split("\n");
  const candidates = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line.startsWith("#EXT-X-STREAM-INF:")) continue;
    const bw = Number((line.match(/BANDWIDTH=(\d+)/i) || [])[1] || 0);
    for (let j = i + 1; j < lines.length; j++) {
      const next = lines[j].trim();
      if (!next) continue;
      if (next.startsWith("#")) break;
      candidates.push({ bandwidth: bw, url: absolute(source, next) });
      break;
    }
  }
  candidates.sort((a, b) => b.bandwidth - a.bandwidth);
  return candidates[0]?.url || null;
}

function rewriteMedia(text, source, duration) {
  const lines = String(text || "").replace(/\r/g, "").split("\n");
  const header = [];
  const body = [];
  let cumulative = 0;
  let pendingInf = null;
  let pendingTags = [];
  let segmentCount = 0;

  for (const raw of lines) {
    let line = raw;
    if (!line) continue;

    if (line.startsWith("#EXTINF:")) {
      const m = line.match(/^#EXTINF:([0-9.]+)/);
      pendingInf = { line, seconds: m ? Number(m[1]) : 0 };
      continue;
    }

    if (line.startsWith("#")) {
      line = line.replace(/URI="([^"]+)"/g, (_, uri) => `URI="${absolute(source, uri)}"`);
      if (pendingInf) pendingTags.push(line);
      else if (line !== "#EXT-X-ENDLIST") header.push(line);
      continue;
    }

    if (!pendingInf) {
      body.push(absolute(source, line.trim()));
      continue;
    }

    const segSeconds = Math.max(0, Number(pendingInf.seconds) || 0);
    if (segmentCount > 0 && cumulative + segSeconds > duration + 0.25) break;

    body.push(...pendingTags);
    body.push(pendingInf.line);
    body.push(absolute(source, line.trim()));
    cumulative += segSeconds;
    segmentCount += 1;
    pendingInf = null;
    pendingTags = [];
    if (cumulative >= duration - 0.25) break;
  }

  if (!segmentCount) throw new Error("no media segments found");
  const out = [...header, ...body];
  if (!out.some(x => x.startsWith("#EXTM3U"))) out.unshift("#EXTM3U");
  out.push("#EXT-X-ENDLIST");
  return out.join("\n") + "\n";
}

module.exports = async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store, max-age=0");
  res.setHeader("Pragma", "no-cache");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("X-HARU-Clip-Version", VERSION);

  const src = String(req.query?.src || "").trim();
  let duration = Number(req.query?.duration || 600);
  if (!Number.isFinite(duration)) duration = 600;
  duration = Math.max(30, Math.min(Math.floor(duration), 3600));

  if (!isAllowedSource(src)) {
    return res.status(400).json({ error: "invalid HARU replay source", resolver: VERSION });
  }

  try {
    let mediaUrl = src;
    let text = await fetchText(mediaUrl);
    for (let depth = 0; depth < 2 && /#EXT-X-STREAM-INF:/i.test(text); depth++) {
      const variant = pickVariant(text, mediaUrl);
      if (!variant) throw new Error("master playlist has no variant");
      mediaUrl = variant;
      text = await fetchText(mediaUrl);
    }
    if (/#EXT-X-STREAM-INF:/i.test(text)) throw new Error("nested master playlist too deep");

    const rewritten = rewriteMedia(text, mediaUrl, duration);
    res.setHeader("Content-Type", "application/vnd.apple.mpegurl; charset=utf-8");
    res.setHeader("X-HARU-Clip-Duration", String(duration));
    res.setHeader("X-HARU-Clip-Media", mediaUrl);
    return res.status(200).send(rewritten);
  } catch (e) {
    return res.status(502).json({
      error: "HARU clip playlist failed",
      detail: String(e?.message || e),
      resolver: VERSION
    });
  }
};
