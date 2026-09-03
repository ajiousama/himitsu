const channels = require("../kick_channels.json");

const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36";

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
  const r = await fetch(url, {
    headers: {
      "accept": "application/json, text/plain, */*",
      "user-agent": UA,
      "referer": "https://kick.com/"
    },
    cache: "no-store"
  });
  if (!r.ok) return null;
  try { return await r.json(); } catch { return null; }
}

function playbackOf(obj) {
  return obj?.playback_url ||
         obj?.stream?.playback_url ||
         obj?.livestream?.playback_url ||
         obj?.data?.playback_url ||
         null;
}

function isLive(obj) {
  const live = obj?.livestream;
  if (live && typeof live === "object") {
    if (live.is_live === false) return false;
    return true;
  }
  if (obj?.is_live === true) return true;
  if (obj?.stream?.is_live === true) return true;
  return false;
}

function sameIvsChannel(url, expected) {
  return !!url && !!expected && url.includes(".channel." + expected + ".m3u8");
}

async function resolveSlug(slug, expectedId) {
  if (!slug) return null;
  const data = await getJson("https://kick.com/api/v2/channels/" + encodeURIComponent(slug));
  if (!data) return null;
  const playback = playbackOf(data);
  if (!sameIvsChannel(playback, expectedId)) return null;
  if (!isLive(data)) return null;
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

  const searched = await searchCandidates(item);
  for (const slug of searched) {
    const hit = await resolveSlug(slug, expectedId);
    if (hit) return hit;
  }
  return null;
}

module.exports = async function handler(req, res) {
  res.setHeader("Cache-Control", "no-store, max-age=0");
  res.setHeader("Pragma", "no-cache");

  const key = String(req.query?.ch || "").toLowerCase();
  const aliases = {
    gccx: "kick.gccx",
    nogizaka: "kick.nogizaka",
    nogi: "kick.nogizaka"
  };
  const tvgId = aliases[key] || key;
  const item = channels.find(x => String(x.tvg_id || "").toLowerCase() === tvgId);
  if (!item) return res.status(404).json({ error: "unknown KICK channel" });

  try {
    const hit = await resolve(item);
    if (!hit) return res.status(503).json({
      error: "KICK live playback unavailable",
      tvg_id: item.tvg_id,
      expected_channel_id: item.channel_id
    });
    res.setHeader("X-Kick-Resolved-Slug", hit.slug);
    res.setHeader("X-Kick-Channel-Id", String(item.channel_id || ""));
    return res.redirect(302, hit.playback);
  } catch (e) {
    return res.status(502).json({ error: "KICK resolver failed", detail: String(e?.message || e) });
  }
};
