const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36";
const VERSION = "2026-09-16-haru-clip-v3-offset";

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

function isPlaylistHeader(line) {
  return line === "#EXTM3U" ||
    line.startsWith("#EXT-X-VERSION:") ||
    line.startsWith("#EXT-X-TARGETDURATION:") ||
    line.startsWith("#EXT-X-MEDIA-SEQUENCE:") ||
    line.startsWith("#EXT-X-DISCONTINUITY-SEQUENCE:") ||
    line.startsWith("#EXT-X-PLAYLIST-TYPE:") ||
    line.startsWith("#EXT-X-INDEPENDENT-SEGMENTS") ||
    line.startsWith("#EXT-X-I-FRAMES-ONLY") ||
    line.startsWith("#EXT-X-ALLOW-CACHE:");
}

function rewriteTagUris(line, source) {
  return line.replace(/URI="([^"]+)"/g, (_, uri) => `URI="${absolute(source, uri)}"`);
}

function rewriteMedia(text, source, offset, duration) {
  const lines = String(text || "").replace(/\r/g, "").split("\n");
  const header = [];
  const groups = [];
  let pendingTags = [];
  let pendingInf = null;

  for (const raw of lines) {
    let line = raw.trim();
    if (!line || line === "#EXT-X-ENDLIST") continue;

    if (line.startsWith("#EXTINF:")) {
      const m = line.match(/^#EXTINF:([0-9.]+)/);
      pendingInf = { line, seconds: m ? Number(m[1]) : 0 };
      continue;
    }

    if (line.startsWith("#")) {
      line = rewriteTagUris(line, source);
      if (!pendingInf && groups.length === 0 && pendingTags.length === 0 && isPlaylistHeader(line)) {
        header.push(line);
      } else {
        pendingTags.push(line);
      }
      continue;
    }

    if (!pendingInf) continue;
    groups.push({
      tags: pendingTags,
      inf: pendingInf.line,
      seconds: Math.max(0, Number(pendingInf.seconds) || 0),
      uri: absolute(source, line)
    });
    pendingTags = [];
    pendingInf = null;
  }

  if (!groups.length) throw new Error("no media segments found");

  let cumulative = 0;
  let selectedDuration = 0;
  let skipped = 0;
  let activeKey = null;
  let activeMap = null;
  const selected = [];

  for (const group of groups) {
    for (const tag of group.tags) {
      if (tag.startsWith("#EXT-X-KEY:")) activeKey = tag;
      if (tag.startsWith("#EXT-X-MAP:")) activeMap = tag;
    }

    const segStart = cumulative;
    const segEnd = cumulative + group.seconds;
    cumulative = segEnd;

    if (segEnd <= offset + 0.001) {
      skipped += 1;
      continue;
    }
    if (selectedDuration >= duration - 0.25) break;
    if (selected.length > 0 && selectedDuration + group.seconds > duration + 0.25) break;

    const tags = [...group.tags];
    if (selected.length === 0) {
      if (activeKey && !tags.some(t => t.startsWith("#EXT-X-KEY:"))) tags.unshift(activeKey);
      if (activeMap && !tags.some(t => t.startsWith("#EXT-X-MAP:"))) tags.unshift(activeMap);
      tags.unshift(`#EXT-X-START:TIME-OFFSET=0,PRECISE=YES`);
      tags.unshift(`# HARU clip requested offset=${offset}s actual_segment_start=${segStart.toFixed(3)}s`);
    }

    selected.push({ ...group, tags });
    selectedDuration += group.seconds;
  }

  if (!selected.length) throw new Error(`offset ${offset}s is outside available replay`);

  const adjustedHeader = header.map(line => {
    const m = line.match(/^#EXT-X-MEDIA-SEQUENCE:(\d+)/);
    if (!m) return line;
    return `#EXT-X-MEDIA-SEQUENCE:${Number(m[1]) + skipped}`;
  });

  const out = [...adjustedHeader];
  if (!out.some(x => x === "#EXTM3U")) out.unshift("#EXTM3U");
  for (const group of selected) {
    out.push(...group.tags);
    out.push(group.inf);
    out.push(group.uri);
  }
  out.push("#EXT-X-ENDLIST");
  return { text: out.join("\n") + "\n", actualDuration: selectedDuration, skipped };
}

module.exports = async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store, max-age=0");
  res.setHeader("Pragma", "no-cache");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("X-HARU-Clip-Version", VERSION);

  const src = String(req.query?.src || "").trim();
  let offset = Number(req.query?.offset || 0);
  let duration = Number(req.query?.duration || 600);
  if (!Number.isFinite(offset)) offset = 0;
  if (!Number.isFinite(duration)) duration = 600;
  offset = Math.max(0, Math.min(Math.floor(offset), 8 * 3600));
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

    const clipped = rewriteMedia(text, mediaUrl, offset, duration);
    res.setHeader("Content-Type", "application/vnd.apple.mpegurl; charset=utf-8");
    res.setHeader("X-HARU-Clip-Offset", String(offset));
    res.setHeader("X-HARU-Clip-Duration", String(duration));
    res.setHeader("X-HARU-Clip-Actual-Duration", String(clipped.actualDuration));
    res.setHeader("X-HARU-Clip-Skipped-Segments", String(clipped.skipped));
    res.setHeader("X-HARU-Clip-Media", mediaUrl);
    return res.status(200).send(clipped.text);
  } catch (e) {
    return res.status(502).json({
      error: "HARU clip playlist failed",
      offset,
      duration,
      detail: String(e?.message || e),
      resolver: VERSION
    });
  }
};
