const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36";
const RESOLVER_VERSION = "2026-09-17-kick-replay-v3-clip";

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

function pickVariant(text, source) {
  const lines = String(text || "").replace(/\r/g, "").split("\n");
  const choices = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line.startsWith("#EXT-X-STREAM-INF:")) continue;
    const bw = Number((line.match(/BANDWIDTH=(\d+)/i) || [])[1] || 0);
    for (let j = i + 1; j < lines.length; j++) {
      const next = lines[j].trim();
      if (!next) continue;
      if (next.startsWith("#")) break;
      choices.push({ bw, url: absolute(source, next) });
      break;
    }
  }
  choices.sort((a, b) => b.bw - a.bw);
  return choices[0]?.url || null;
}

function rewriteStartOnly(text, source, startSeconds) {
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

function rewriteClip(text, source, offset, duration) {
  const lines = String(text || "").replace(/\r/g, "").split("\n");
  const header = [];
  const groups = [];
  let tags = [];
  let inf = null;
  const isHeader = line => line === "#EXTM3U" || /^#EXT-X-(VERSION|TARGETDURATION|MEDIA-SEQUENCE|DISCONTINUITY-SEQUENCE|PLAYLIST-TYPE|INDEPENDENT-SEGMENTS|ALLOW-CACHE)/.test(line);

  for (const raw of lines) {
    let line = raw.trim();
    if (!line || line === "#EXT-X-ENDLIST") continue;
    if (line.startsWith("#EXTINF:")) {
      inf = { line, seconds: Number((line.match(/^#EXTINF:([0-9.]+)/) || [])[1] || 0) };
      continue;
    }
    if (line.startsWith("#")) {
      line = line.replace(/URI="([^"]+)"/g, (_, uri) => `URI="${absolute(source, uri)}"`);
      if (!inf && !groups.length && !tags.length && isHeader(line)) header.push(line);
      else tags.push(line);
      continue;
    }
    if (inf) {
      groups.push({ tags, inf: inf.line, seconds: Math.max(0, inf.seconds || 0), uri: absolute(source, line) });
      tags = [];
      inf = null;
    }
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
    const segmentStart = cumulative;
    const segmentEnd = cumulative + group.seconds;
    cumulative = segmentEnd;

    if (segmentEnd <= offset + 0.001) {
      skipped++;
      continue;
    }
    if (segmentStart >= offset + duration - 0.001) break;

    const segmentTags = [...group.tags];
    if (!selected.length) {
      if (activeKey && !segmentTags.some(x => x.startsWith("#EXT-X-KEY:"))) segmentTags.unshift(activeKey);
      if (activeMap && !segmentTags.some(x => x.startsWith("#EXT-X-MAP:"))) segmentTags.unshift(activeMap);
      segmentTags.unshift(`# KICK clip requested start=${offset}s duration=${duration}s actual_segment_start=${segmentStart.toFixed(3)}s`);
    }
    selected.push({ ...group, tags: segmentTags });
    selectedDuration += group.seconds;
  }

  if (!selected.length) throw new Error(`offset ${offset}s is outside available VOD`);

  const out = header.map(line => {
    const m = line.match(/^#EXT-X-MEDIA-SEQUENCE:(\d+)/);
    return m ? `#EXT-X-MEDIA-SEQUENCE:${Number(m[1]) + skipped}` : line;
  });
  if (!out.includes("#EXTM3U")) out.unshift("#EXTM3U");
  for (const group of selected) out.push(...group.tags, group.inf, group.uri);
  out.push("#EXT-X-ENDLIST");
  return { text: out.join("\n") + "\n", selectedDuration };
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

  let duration = Number(req.query?.duration || 0);
  if (!Number.isFinite(duration) || duration < 0) duration = 0;
  duration = duration ? Math.max(30, Math.min(Math.floor(duration), 12 * 60 * 60)) : 0;

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
  res.setHeader("X-Kick-Replay-Duration", String(duration));

  if (!start && !duration) return res.redirect(302, source);

  try {
    let media = source;
    let playlist = await getText(media);
    for (let depth = 0; depth < 3 && /#EXT-X-STREAM-INF:/i.test(playlist); depth++) {
      const variant = pickVariant(playlist, media);
      if (!variant) throw new Error("master playlist has no variant");
      media = variant;
      playlist = await getText(media);
    }
    if (/#EXT-X-STREAM-INF:/i.test(playlist)) throw new Error("nested master playlist too deep");

    res.setHeader("Content-Type", "application/vnd.apple.mpegurl; charset=utf-8");
    if (duration) {
      const clipped = rewriteClip(playlist, media, start, duration);
      res.setHeader("X-Kick-Replay-Selected-Duration", String(clipped.selectedDuration));
      return res.status(200).send(clipped.text);
    }
    return res.status(200).send(rewriteStartOnly(playlist, media, start));
  } catch (e) {
    return res.status(502).json({
      error: "KICK VOD clip playlist failed",
      vod,
      start,
      duration,
      detail: String(e?.message || e),
      resolver: RESOLVER_VERSION
    });
  }
};
