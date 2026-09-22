const channels = require("../kick_channels.json");

const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36";
const RESOLVER_VERSION = "2026-09-21-kick-live-vod-v6-gccx2";

function norm(s) {
  return String(s || "").toLowerCase().replace(/[^a-z0-9\u3040-\u30ff\u3400-\u9fff]+/g, "");
}

function flattenObjects(value, out = []) {
  if (!value || typeof value !== "object") return out;
  if (Array.isArray(value)) {
    for (const v of value) flattenObjects(v, out);
    return out;
  }
  out.push(value);
  for (const v of Object.values(value)) flattenObjects(v, out);
  return out;
}

async function getJson(url) {
  for (let attempt = 0; attempt < 3; attempt++) {
    try {
      const r = await fetch(url, {
        headers: {
          "accept": "application/json, text/plain, */*",
          "user-agent": UA,
          "referer": "https://kick.com/",
          "cache-control": "no-cache",
          "pragma": "no-cache"
        },
        cache: "no-store"
      });
      if (r.ok) {
        try { return await r.json(); } catch {}
      }
    } catch {}
    if (attempt < 2) await new Promise(r => setTimeout(r, 250 * (attempt + 1)));
  }
  return null;
}

function playbackOf(obj) {
  return obj?.playback_url ||
         obj?.playbackUrl ||
         obj?.stream?.playback_url ||
         obj?.stream?.playbackUrl ||
         obj?.livestream?.playback_url ||
         obj?.livestream?.playbackUrl ||
         obj?.data?.playback_url ||
         obj?.data?.playbackUrl ||
         null;
}

function sameIvsChannel(url, expected) {
  return !!url && !!expected && url.includes(".channel." + expected + ".m3u8");
}

async function resolveSlug(slug, expectedId) {
  if (!slug) return null;
  const data = await getJson("https://kick.com/api/v2/channels/" + encodeURIComponent(slug));
  if (!data) return null;
  const playback = playbackOf(data);
  if (!playback) return null;
  if (expectedId && !sameIvsChannel(playback, expectedId)) return null;
  return { slug: data.slug || slug, playback };
}

async function searchCandidates(item) {
  const terms = [
    item.search,
    ...(Array.isArray(item.match_terms) ? item.match_terms : []),
    item.name
  ].filter(Boolean);

  const wanted = new Set(terms.map(norm).filter(Boolean));
  const found = [];

  for (const term of terms.slice(0, 5)) {
    const data = await getJson("https://kick.com/api/search?query=" + encodeURIComponent(term));
    if (!data) continue;
    for (const obj of flattenObjects(data)) {
      const slug = obj.slug || obj.channel_slug || obj.username || obj.name;
      if (!slug || typeof slug !== "string") continue;
      const hay = norm([obj.slug, obj.username, obj.name, obj.session_title, obj.title].filter(Boolean).join(" "));
      if (wanted.size && ![...wanted].some(x => x && hay.includes(x))) continue;
      found.push(slug);
    }
  }
  return [...new Set(found)];
}

async function resolve(item) {
  const expectedId = String(item.channel_id || "").trim();
  const slugs = [
    item.slug,
    ...(Array.isArray(item.slug_aliases) ? item.slug_aliases : [])
  ].filter(Boolean);

  for (const slug of [...new Set(slugs)]) {
    const hit = await resolveSlug(slug, expectedId);
    if (hit) return hit;
  }

  for (const slug of [...new Set(slugs)]) {
    const hit = await resolveSlug(slug, expectedId);
    if (hit) return hit;
  }

  const searched = await searchCandidates(item);
  for (const slug of searched) {
    const hit = await resolveSlug(slug, expectedId);
    if (hit) return hit;
  }
  return null;
}

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


function pickVariant(text, source) {
  const lines = String(text || "").replace(/\r/g, "").split("\n");
  const candidates = [];
  for (let i = 0; i < lines.length; i++) {
    if (!lines[i].trim().startsWith("#EXT-X-STREAM-INF:")) continue;
    const bandwidth = Number((lines[i].match(/BANDWIDTH=(\d+)/i) || [])[1] || 0);
    for (let j = i + 1; j < lines.length; j++) {
      const next = lines[j].trim();
      if (!next) continue;
      if (next.startsWith("#")) break;
      candidates.push({ bandwidth, url: absolute(source, next) });
      break;
    }
  }
  candidates.sort((a, b) => b.bandwidth - a.bandwidth);
  return candidates[0]?.url || null;
}

function clipPlaylist(text, source, offset, duration) {
  const lines = String(text || "").replace(/\r/g, "").split("\n");
  const header = [];
  const groups = [];
  let tags = [];
  let inf = null;
  const isHeader = line =>
    line === "#EXTM3U" ||
    /^#EXT-X-(VERSION|TARGETDURATION|MEDIA-SEQUENCE|DISCONTINUITY-SEQUENCE|PLAYLIST-TYPE|INDEPENDENT-SEGMENTS|ALLOW-CACHE)/.test(line);

  for (const raw of lines) {
    let line = raw.trim();
    if (!line || line === "#EXT-X-ENDLIST") continue;
    if (line.startsWith("#EXTINF:")) {
      inf = {
        line,
        seconds: Number((line.match(/^#EXTINF:([0-9.]+)/) || [])[1] || 0)
      };
      continue;
    }
    if (line.startsWith("#")) {
      line = line.replace(/URI="([^"]+)"/g, (_, uri) => `URI="${absolute(source, uri)}"`);
      if (!inf && !groups.length && !tags.length && isHeader(line)) header.push(line);
      else tags.push(line);
      continue;
    }
    if (inf) {
      groups.push({
        tags,
        inf: inf.line,
        seconds: Math.max(0, inf.seconds || 0),
        uri: absolute(source, line)
      });
      tags = [];
      inf = null;
    }
  }

  if (!groups.length) throw new Error("no media segments found");

  let cumulative = 0;
  let skipped = 0;
  let key = null;
  let map = null;
  const selected = [];

  for (const group of groups) {
    for (const tag of group.tags) {
      if (tag.startsWith("#EXT-X-KEY:")) key = tag;
      if (tag.startsWith("#EXT-X-MAP:")) map = tag;
    }
    const start = cumulative;
    const end = cumulative + group.seconds;
    cumulative = end;

    if (end <= offset + 0.001) {
      skipped++;
      continue;
    }
    if (start >= offset + duration - 0.001) break;

    const outTags = [...group.tags];
    if (!selected.length) {
      if (key && !outTags.some(x => x.startsWith("#EXT-X-KEY:"))) outTags.unshift(key);
      if (map && !outTags.some(x => x.startsWith("#EXT-X-MAP:"))) outTags.unshift(map);
      outTags.unshift(
        "#EXT-X-START:TIME-OFFSET=0,PRECISE=YES",
        `# KICK clip requested offset=${offset}s actual_segment_start=${start.toFixed(3)}s`
      );
    }
    selected.push({ ...group, tags: outTags });
  }

  if (!selected.length) throw new Error(`offset ${offset}s is outside available replay`);

  const out = header.map(line => {
    const match = line.match(/^#EXT-X-MEDIA-SEQUENCE:(\d+)/);
    return match ? `#EXT-X-MEDIA-SEQUENCE:${Number(match[1]) + skipped}` : line;
  });
  if (!out.includes("#EXTM3U")) out.unshift("#EXTM3U");
  for (const group of selected) out.push(...group.tags, group.inf, group.uri);
  out.push("#EXT-X-ENDLIST");
  return out.join("\n") + "\n";
}

async function handleVod(req, res) {
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

    const rewritten = duration
      ? clipPlaylist(playlist, media, start, duration)
      : rewritePlaylist(playlist, media, start);

    res.setHeader("Content-Type", "application/vnd.apple.mpegurl; charset=utf-8");
    return res.status(200).send(rewritten);
  } catch (e) {
    return res.status(502).json({
      error: "KICK VOD seek playlist failed",
      vod,
      start,
      duration,
      detail: String(e?.message || e),
      resolver: RESOLVER_VERSION
    });
  }
}

module.exports = async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store, max-age=0");
  res.setHeader("Pragma", "no-cache");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("X-Kick-Resolver-Version", RESOLVER_VERSION);

  if (req.query?.vod) return handleVod(req, res);

  const key = String(req.query?.ch || "").toLowerCase();
  const aliases = {
    gccx: "kick.gccx",
    gccx2: "kick.gccx2",
    nogizaka: "kick.nogizaka",
    nogi: "kick.nogizaka"
  };
  const tvgId = aliases[key] || key;
  const item = channels.find(x => String(x.tvg_id || "").toLowerCase() === tvgId);
  if (!item) return res.status(404).json({ error: "unknown KICK channel", resolver: RESOLVER_VERSION });

  try {
    const hit = await resolve(item);
    if (!hit) return res.status(503).json({
      error: "KICK live playback unavailable",
      tvg_id: item.tvg_id,
      slug: item.slug,
      expected_channel_id: item.channel_id,
      resolver: RESOLVER_VERSION
    });
    res.setHeader("X-Kick-Resolved-Slug", hit.slug);
    res.setHeader("X-Kick-Channel-Id", String(item.channel_id || ""));
    return res.redirect(302, hit.playback);
  } catch (e) {
    return res.status(502).json({ error: "KICK resolver failed", detail: String(e?.message || e), resolver: RESOLVER_VERSION });
  }
};
