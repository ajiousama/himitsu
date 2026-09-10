const channels = require("../kick_channels.json");

const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36";
const RESOLVER_VERSION = "2026-09-10-gccx2-v2";

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
          "referer": "https://kick.com/"
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

  // Playback URL is the strongest signal. KICK has changed live-state fields
  // across API revisions, so do not reject a usable live HLS just because
  // is_live/livestream metadata is missing or shaped differently.
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

  // One extra pass helps when KICK briefly returns a transient 4xx/5xx.
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
  res.setHeader("X-Kick-Resolver-Version", RESOLVER_VERSION);

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
