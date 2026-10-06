const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/151 Safari/537.36";
const VERSION = "2026-10-07-tver-follow-v1";
const ORIGIN = "https://tver.jp";
const PLATFORM = "https://platform-api.tver.jp/service/api/v1";
const BROWSER_CREATE = "https://platform-api.tver.jp/v2/api/platform_users/browser/create";
const PLAYER_INFO = "https://player.tver.jp/player/streaks_info_v2.json";
const PLAYBACK = "https://playback.api.streaks.jp/v1/projects";
const SSAI = "https://ssai.api.streaks.jp/v1/projects";

function json(res, status, value) {
  res.statusCode = status;
  res.setHeader("Content-Type", "application/json; charset=utf-8");
  res.setHeader("Cache-Control", "no-store, max-age=0");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.end(JSON.stringify(value));
}

async function fetchJson(url, init = {}) {
  const r = await fetch(url, {
    redirect: "follow",
    cache: "no-store",
    ...init,
    headers: {
      "User-Agent": UA,
      Accept: "application/json,text/plain,*/*",
      ...(init.headers || {})
    }
  });
  const body = await r.text();
  let data = null;
  try { data = JSON.parse(body); } catch {}
  if (!r.ok || data == null) {
    throw new Error("HTTP " + r.status + " " + new URL(url).host + " " + body.slice(0, 120));
  }
  return data;
}

async function browserCredentials() {
  const r = await fetch(BROWSER_CREATE, {
    method: "POST",
    headers: {
      "User-Agent": UA,
      Accept: "application/json",
      "Content-Type": "application/x-www-form-urlencoded",
      Referer: "https://s.tver.jp/"
    },
    body: "device_type=pc",
    cache: "no-store"
  });
  const d = await r.json().catch(() => null);
  const uid = d && d.result && d.result.platform_uid;
  const token = d && d.result && d.result.platform_token;
  if (!r.ok || !uid || !token) throw new Error("browser credentials failed");
  return { uid, token };
}

async function platform(path, cred) {
  const u = new URL(PLATFORM + "/" + path);
  u.searchParams.set("platform_uid", cred.uid);
  u.searchParams.set("platform_token", cred.token);
  return fetchJson(u.toString(), {
    headers: {
      "x-tver-platform-type": "web",
      Origin: ORIGIN,
      Referer: ORIGIN + "/"
    }
  });
}

function keyOrder() {
  const d = new Date(Date.now() + 9 * 3600 * 1000);
  const month = d.getUTCMonth() + 1;
  const preferred = "key0" + (month % 6 || 6);
  const all = ["key01","key02","key03","key04","key05","key06"];
  return [preferred].concat(all.filter(x => x !== preferred));
}

async function apiKeys(project, fallback) {
  const info = await fetchJson(PLAYER_INFO, { headers: { Referer: ORIGIN + "/" } });
  const obj = (info && info[project] && info[project].api_key) || {};
  const out = [];
  for (const name of keyOrder()) {
    const value = obj[name];
    if (typeof value === "string" && value && !out.includes(value)) out.push(value);
  }
  for (const value of Object.values(obj)) {
    if (typeof value === "string" && value && !out.includes(value)) out.push(value);
  }
  if (fallback && !out.includes(fallback)) out.push(fallback);
  return out;
}

function mediaObject(playback) {
  return playback && playback.media && typeof playback.media === "object" ? playback.media : playback;
}

function sources(playback) {
  const media = mediaObject(playback);
  const value = media && media.sources;
  if (Array.isArray(value)) return value.filter(x => x && typeof x === "object");
  if (value && typeof value === "object") return [value];
  return [];
}

function trusted(url) {
  try {
    const u = new URL(url);
    const h = u.hostname.toLowerCase();
    return u.protocol === "https:" &&
      (h === "streaks.jp" || h.endsWith(".streaks.jp") || h === "tver.jp" || h.endsWith(".tver.jp"));
  } catch { return false; }
}

function clearHls(source) {
  const src = String((source && source.src) || "");
  const typ = String((source && source.type) || "").toLowerCase();
  const ks = source && (source.key_systems || source.keySystems);
  const drm = ks && typeof ks === "object" && Object.keys(ks).length > 0;
  return !drm && trusted(src) && (src.includes(".m3u8") || typ.includes("mpegurl") || typ.includes("m3u8"));
}

function ssai(value) {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0;
  if (typeof value === "string") return !["","0","false","disabled","none"].includes(value.toLowerCase());
  if (value && typeof value === "object") return "enabled" in value ? ssai(value.enabled) : true;
  return false;
}

function sessionized(url) {
  try { return Boolean(new URL(url).searchParams.get("session")); } catch { return false; }
}

function appendQuery(raw, query) {
  const u = new URL(raw);
  for (const pair of new URLSearchParams(String(query || ""))) u.searchParams.set(pair[0], pair[1]);
  return u.toString();
}

function ads(playback, currentId) {
  const p = {
    delivery_type: "simul",
    is_dvr: "0",
    video_id: currentId || "",
    device: "pc",
    device_code: "0001",
    tag_type: "browser",
    car: "0",
    personalIsLat: "0",
    c: "simul",
    vr_uuid: "",
    platformAdUid: "",
    platformUid: "",
    accountId: "",
    memberId: "",
    memberIdHash: "",
    luid: "",
    platformVrUid: ""
  };
  const media = mediaObject(playback);
  const extra = (media && (media.ad_fields || media.adFields)) || (playback && (playback.ad_fields || playback.adFields));
  if (extra && typeof extra === "object" && !Array.isArray(extra)) Object.assign(p, extra);
  return p;
}

async function ssaiUrl(playback, projectFallback, clearSources, currentId) {
  const media = mediaObject(playback) || {};
  const project = String(media.project || media.projectId || media.project_id ||
    playback.project || playback.projectId || playback.project_id || projectFallback || "");
  const mediaId = String(media.mediaId || media.mediaID || media.media_id || media.id ||
    playback.mediaId || playback.mediaID || playback.media_id || playback.id || "");
  if (!project || !mediaId) throw new Error("SSAI identity missing");
  const usable = clearSources.filter(x => x.id);
  if (!usable.length) throw new Error("SSAI source ids missing");

  const payload = {
    id: usable.map(x => String(x.id)).join(","),
    ads_params: ads(playback, currentId)
  };
  const reply = await fetchJson(
    SSAI + "/" + encodeURIComponent(project) + "/medias/" + encodeURIComponent(mediaId) + "/ssai/session",
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "*/*",
        Origin: ORIGIN,
        Referer: ORIGIN + "/"
      },
      body: JSON.stringify(payload)
    }
  );
  const rows = Array.isArray(reply) ? reply : [reply];
  const byId = new Map(rows.map(x => [String((x && x.id) || ""), String((x && x.query) || "")]));
  for (const source of usable) {
    const query = byId.get(String(source.id || ""));
    if (query && /(^|&)session=[^&]+/i.test(query)) return appendQuery(String(source.src), query);
  }
  throw new Error("SSAI session token missing");
}

async function playbackUrl(project, mediaId, keys, currentId) {
  const ref = String(mediaId).startsWith("ref:") ? String(mediaId) : "ref:" + String(mediaId);
  const endpoint = PLAYBACK + "/" + encodeURIComponent(project) + "/medias/" + encodeURIComponent(ref);
  let playback = null;
  let last = null;

  for (const key of keys) {
    try {
      playback = await fetchJson(endpoint, {
        headers: {
          Accept: "*/*",
          Origin: ORIGIN,
          Referer: ORIGIN + "/",
          "X-Streaks-Api-Key": key
        }
      });
      break;
    } catch (e) { last = e; }
  }
  if (!playback) throw new Error("playback failed: " + String(last && last.message || last || "no key"));

  const clear = sources(playback).filter(clearHls);
  if (!clear.length) throw new Error("clear HLS missing");
  const ready = clear.find(x => sessionized(String(x.src || "")));
  if (ready) return String(ready.src);

  const media = mediaObject(playback) || {};
  const needs = ssai(media.ssai) || ssai(playback.ssai) || clear.some(x => ssai(x.ssai));
  if (!needs) return String(clear[0].src);
  return ssaiUrl(playback, project, clear, currentId);
}

function channels(payload) {
  const list = payload && payload.result && payload.result.contents;
  if (!Array.isArray(list)) return [];
  return list.map(item => {
    const c = (item && item.content) || {};
    const v = (item && item.video) || c.video || {};
    const id = String(c.id || "").toLowerCase();
    const project = String(v.projectID || v.projectId || "");
    const mediaId = String(v.mediaID || v.mediaId || "");
    if (!id || !project || !mediaId) return null;
    return {
      id,
      name: String(c.name || id),
      project,
      mediaId,
      keyName: String(v.apiKey || id)
    };
  }).filter(Boolean);
}

async function currentProgram(id, cred) {
  const data = await platform("callLiveTimeline/" + encodeURIComponent(id), cred);
  const list = data && data.result && data.result.contents;
  const now = Math.floor(Date.now() / 1000);
  if (!Array.isArray(list)) return null;
  for (const item of list) {
    const c = (item && item.content) || {};
    const start = Number(c.startAt || 0);
    const end = Number(c.endAt || 0);
    if (!(start <= now && now < end)) continue;
    const label = String(c.title || "") + " " + String(c.seriesTitle || "");
    if (item.type === "pause" || /配信休止|配信準備中/.test(label)) return null;
    return {
      id: String(c.id || ""),
      title: String(c.title || c.seriesTitle || ""),
      startAt: start,
      endAt: end
    };
  }
  return null;
}

async function resolveSimul(id) {
  const cred = await browserCredentials();
  const list = channels(await platform("callLiveChannel", cred));
  const ch = list.find(x => x.id === String(id).toLowerCase());
  if (!ch) throw new Error("channel not found");
  const current = await currentProgram(ch.id, cred);
  if (!current) throw new Error("channel off air");
  const keys = await apiKeys(ch.project, "");
  const hls = await playbackUrl(ch.project, ch.mediaId, keys, current.id);
  return { id: ch.id, title: current.title || ch.name, hls };
}

async function resolveSpecial(id) {
  if (!/^le[a-z0-9]+$/i.test(String(id))) throw new Error("invalid Special Live id");

  try {
    const hls = await playbackUrl("tver-splive", "ref:" + id, [id], id);
    let title = id;
    try {
      const meta = await fetchJson("https://statics.tver.jp/content/live/" + encodeURIComponent(id) + ".json?v=3", { headers: { Origin: ORIGIN, Referer: ORIGIN + "/" } });
      title = String(meta.title || meta.seriesTitle || id);
    } catch {}
    return { id, title, hls };
  } catch (first) {
    let meta = null;
    for (const version of [3,2,1]) {
      try {
        meta = await fetchJson(
          "https://statics.tver.jp/content/live/" + encodeURIComponent(id) + ".json?v=" + version,
          { headers: { Origin: ORIGIN, Referer: ORIGIN + "/" } }
        );
        break;
      } catch {}
    }
    if (!meta) throw first;
    const v = meta.liveVideo || meta.video || {};
    const project = String(v.projectID || v.projectId || "");
    const mediaId = String(v.mediaID || v.mediaId || "");
    const direct = String(v.apiKey || v.api_key || "");
    if (!project || !mediaId) throw first;
    const keys = await apiKeys(project, direct);
    if (!keys.length) throw first;
    const hls = await playbackUrl(project, mediaId, keys, String(meta.id || id));
    return { id, title: String(meta.title || meta.seriesTitle || id), hls };
  }
}


async function fetchText(url) {
  const r = await fetch(url, {
    headers: {
      "User-Agent": UA,
      Accept: "text/html,application/xhtml+xml,text/plain,*/*",
      Referer: ORIGIN + "/",
      "Cache-Control": "no-cache"
    },
    cache: "no-store",
    redirect: "follow"
  });
  if (!r.ok) throw new Error("HTTP " + r.status + " " + new URL(url).host);
  return r.text();
}

function idsFromHtml(html) {
  const normalized = String(html || "")
    .replace(/\\u002F/gi, "/")
    .replace(/\\\//g, "/");
  const out = [];
  for (const m of normalized.matchAll(/\/live\/special\/(le[a-z0-9]+)/gi)) {
    if (!out.includes(m[1])) out.push(m[1]);
  }
  return out;
}

async function discoverPlayableSpecials() {
  const candidates = [];
  const pages = [
    "https://tver.jp/live",
    "https://tver.jp/corner/f0048951"
  ];

  for (const page of pages) {
    try {
      const ids = idsFromHtml(await fetchText(page));
      for (const id of ids) if (!candidates.includes(id)) candidates.push(id);
    } catch {}
  }

  const out = [];
  for (const id of candidates.slice(0, 40)) {
    try {
      const live = await resolveSpecial(id);
      out.push({
        kind: "special",
        id,
        title: String(live.title || id),
        resolver: "/api/tver?special=" + encodeURIComponent(id)
      });
    } catch {}
  }
  return out;
}

async function resolveNewsAlias(alias) {
  const live = await discoverPlayableSpecials();
  const re = alias === "news24" ? /日テレ\s*NEWS24/i : /TBS\s*NEWS\s*DIG/i;
  const hit = live.find(x => re.test(String(x.title || "")));
  if (!hit) throw new Error("news live not found");
  return resolveSpecial(hit.id);
}

function walk(value, out) {
  if (!value || typeof value !== "object") return out;
  if (Array.isArray(value)) {
    for (const v of value) walk(v, out);
    return out;
  }
  out.push(value);
  for (const v of Object.values(value)) walk(v, out);
  return out;
}

async function catalog(req) {
  const cred = await browserCredentials();
  const raw = channels(await platform("callLiveChannel", cred));
  const simul = [];
  await Promise.all(raw.map(async ch => {
    try {
      const cur = await currentProgram(ch.id, cred);
      if (cur) simul.push({ kind: "simul", id: ch.id, name: ch.name, title: cur.title, startAt: cur.startAt, endAt: cur.endAt });
    } catch {}
  }));

  const specialMap = new Map();

  try {
    const home = await platform("callHome", cred);
    const now = Math.floor(Date.now() / 1000);
    for (const obj of walk(home, [])) {
      if (obj.type !== "live") continue;
      const c = obj.content;
      if (!c || typeof c !== "object") continue;
      const id = String(c.id || "");
      if (!/^le[a-z0-9]+$/i.test(id)) continue;
      const start = Number(c.startAt || 0);
      const end = Number(c.endAt || 0);
      if (start && now < start) continue;
      if (end && now >= end) continue;
      specialMap.set(id, {
        kind: "special",
        id,
        title: String(c.title || c.seriesTitle || id),
        startAt: start || null,
        endAt: end || null
      });
    }
  } catch {}

  for (const item of await discoverPlayableSpecials()) {
    if (!specialMap.has(item.id)) specialMap.set(item.id, item);
  }

  const proto = String(req.headers["x-forwarded-proto"] || "https").split(",")[0].trim();
  const base = proto + "://" + req.headers.host + "/api/tver";
  const special = Array.from(specialMap.values());
  for (const x of simul) x.resolver = base + "?live=" + encodeURIComponent(x.id);
  for (const x of special) x.resolver = base + "?special=" + encodeURIComponent(x.id);
  simul.sort((a,b) => a.id.localeCompare(b.id));
  special.sort((a,b) => a.title.localeCompare(b.title, "ja"));
  return { simul, special };
}

function redirect(res, result, kind) {
  if (!trusted(result.hls)) return json(res, 502, { ok: false, error: "untrusted stream" });
  res.statusCode = 302;
  res.setHeader("Location", result.hls);
  res.setHeader("Cache-Control", "no-store, max-age=0");
  res.setHeader("Pragma", "no-cache");
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("X-TVer-Live-Kind", kind);
  res.setHeader("X-TVer-Live-Id", result.id);
  res.end();
}

export default async function handler(req, res) {
  res.setHeader("X-TVer-Resolver-Version", VERSION);
  res.setHeader("X-Vercel-Region", process.env.VERCEL_REGION || "unknown");
  res.setHeader("Access-Control-Allow-Origin", "*");

  if (req.method === "HEAD") {
    res.statusCode = 200;
    res.setHeader("Cache-Control", "no-store");
    return res.end();
  }
  if (req.method !== "GET") {
    res.statusCode = 405;
    res.setHeader("Allow", "GET, HEAD");
    return res.end("Method Not Allowed");
  }

  if (String(req.query && req.query.health || "") === "1") {
    return json(res, 200, {
      ok: true,
      resolver: VERSION,
      region: process.env.VERCEL_REGION || "unknown",
      strategy: "resolve-on-playback+ssai"
    });
  }

  if (String(req.query && req.query.debug || "") === "home") {
    try {
      const cred = await browserCredentials();
      const home = await platform("callHome", cred);
      const nodes = [];
      for (const obj of walk(home, [])) {
        const typ = String(obj.type || obj.Type || "");
        const c = obj.content || obj.Content;
        if (typ.toLowerCase().includes("live") || (c && /^le[a-z0-9]+$/i.test(String(c.id || c.Id || "")))) {
          nodes.push({
            type: typ,
            id: c && String(c.id || c.Id || ""),
            title: c && String(c.title || c.Title || c.seriesTitle || c.SeriesTitle || ""),
            startAt: c && (c.startAt || c.StartAt || null),
            endAt: c && (c.endAt || c.EndAt || null),
            keys: Object.keys(obj).slice(0,20),
            contentKeys: c && typeof c === "object" ? Object.keys(c).slice(0,30) : []
          });
        }
      }
      return json(res, 200, {
        ok: true,
        topKeys: Object.keys(home || {}),
        resultKeys: home && home.result ? Object.keys(home.result) : [],
        liveNodes: nodes.slice(0,100),
        resolver: VERSION
      });
    } catch (e) {
      return json(res, 502, { ok: false, detail: String(e && e.message || e), resolver: VERSION });
    }
  }

  if (String(req.query && req.query.catalog || "") === "1") {
    try {
      const c = await catalog(req);
      return json(res, 200, {
        ok: true,
        resolver: VERSION,
        region: process.env.VERCEL_REGION || "unknown",
        generatedAt: new Date().toISOString(),
        simul: c.simul,
        special: c.special
      });
    } catch (e) {
      return json(res, 502, { ok: false, error: "catalog failed", detail: String(e && e.message || e), resolver: VERSION });
    }
  }

  const live = String(req.query && req.query.live || "").trim().toLowerCase();
  const special = String(req.query && req.query.special || "").trim();
  const news = String(req.query && req.query.news || "").trim().toLowerCase();
  const probe = String(req.query && req.query.probe || "") === "1";

  try {
    let result;
    let kind;
    if (live) {
      result = await resolveSimul(live);
      kind = "simul";
    } else if (special) {
      result = await resolveSpecial(special);
      kind = "special";
    } else if (news === "news24" || news === "tbs") {
      result = await resolveNewsAlias(news);
      kind = "special";
    } else {
      return json(res, 400, {
        ok: false,
        error: "missing selector",
        usage: ["?live=ntv", "?special=le...", "?news=news24", "?news=tbs", "?catalog=1", "?health=1"],
        resolver: VERSION
      });
    }

    if (probe) {
      return json(res, 200, {
        ok: true,
        kind,
        id: result.id,
        title: result.title,
        hls: "resolved",
        resolver: VERSION,
        region: process.env.VERCEL_REGION || "unknown"
      });
    }
    return redirect(res, result, kind);
  } catch (e) {
    return json(res, 502, {
      ok: false,
      error: "TVer playback unavailable",
      selector: live || special || news,
      detail: String(e && e.message || e),
      resolver: VERSION,
      region: process.env.VERCEL_REGION || "unknown"
    });
  }
}
