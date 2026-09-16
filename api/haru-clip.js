const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36";
const VERSION = "2026-09-16-haru-clip-v1";

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

function proxyUrl(req, src, duration) {
  const proto = req.headers["x-forwarded-proto"] || "https";
  const host = req.headers.host || "himitsu-six.vercel.app";
  return `${proto}://${host}/api/haru-clip?src=${encodeURIComponent(src)}&duration=${duration}`;
}

function rewriteMaster(text, source, req, duration) {
  const lines = String(text || "").replace(/\r/g, "").split("\n");
  const out = [];
  for (let line of lines) {
    if (!line.trim()) { out.push(line); continue; }
    if (line.startsWith("#")) {
      line = line.replace(/URI="([^"]+)"/g, (_, uri) => {
        const abs = absolute(source, uri);
        return `URI="${proxyUrl(req, abs, duration)}"`;
      });
      out.push(line);
      continue;
    }
    const abs = absolute(source, line.trim());
    out.push(proxyUrl(req, abs, duration));
  }
  return out.join("\n");
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
    const text = await fetchText(src);
    const isMaster = /#EXT-X-STREAM-INF:/i.test(text);
    const rewritten = isMaster
      ? rewriteMaster(text, src, req, duration)
      : rewriteMedia(text, src, duration);
    res.setHeader("Content-Type", "application/vnd.apple.mpegurl; charset=utf-8");
    res.setHeader("X-HARU-Clip-Duration", String(duration));
    return res.status(200).send(rewritten);
  } catch (e) {
    return res.status(502).json({
      error: "HARU clip playlist failed",
      detail: String(e?.message || e),
      resolver: VERSION
    });
  }
};
