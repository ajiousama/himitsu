// Variables used by Scriptable.
// These must be at the very top of the file. Do not edit.
// icon-color: blue; icon-glyph: ship;

// BOAT SEED AUTO
// iPhone / Scriptable専用。
// 日本回線から当日Streaks URLを自動取得し、ajiousama/himitsu の
// boat_stream_seed.m3u を「当日分だけ」安全に追記・更新する。
// 既存の当日URLは一時取得失敗でも残し、前日以前のURLは残さない。
// 成功時は無通知。失敗時だけ通知するのでShortcutsの時刻オートメーション向け。

const HIM_OWNER = "ajiousama";
const HIM_REPO = "himitsu";
const HIM_BRANCH = "main";
const HIM_TOKEN_KEY = "himitsu_github_pat";
const TOKEN_STORE_FILE = "kouei_freewifi_tokens_v17.json";
const SEED_PATH = "boat_stream_seed.m3u";
const UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_6 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1";
const API_REPO = `/repos/${HIM_OWNER}/${HIM_REPO}`;
const LOGO_BASE = "https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main/public_sports_logos_github_43/boatrace";

const BOAT = [
  ["01kiryu","boat.kiryu","BOATRACE桐生","桐生","01_kiryu.png"],
  ["02toda","boat.toda","BOATRACE戸田","戸田","02_toda.png"],
  ["03edogawa","boat.edogawa","BOATRACE江戸川","江戸川","03_edogawa.png"],
  ["04heiwajima","boat.heiwajima","BOATRACE平和島","平和島","04_heiwajima.png"],
  ["05tamagawa","boat.tamagawa","BOATRACE多摩川","多摩川","05_tamagawa.png"],
  ["06hamanako","boat.hamanako","BOATRACE浜名湖","浜名湖","06_hamanako.png"],
  ["07gamagori","boat.gamagori","BOATRACE蒲郡","蒲郡","07_gamagori.png"],
  ["08tokoname","boat.tokoname","BOATRACE常滑","常滑","08_tokoname.png"],
  ["09tsu","boat.tsu","BOATRACE津","津","09_tsu.png"],
  ["10mikuni","boat.mikuni","BOATRACE三国","三国","10_mikuni.png"],
  ["11biwako","boat.biwako","BOATRACEびわこ","びわこ","11_biwako.png"],
  ["12suminoe","boat.suminoe","BOATRACE住之江","住之江","12_suminoe.png"],
  ["13amagasaki","boat.amagasaki","BOATRACE尼崎","尼崎","13_amagasaki.png"],
  ["14naruto","boat.naruto","BOATRACE鳴門","鳴門","14_naruto.png"],
  ["15marugame","boat.marugame","BOATRACE丸亀","丸亀","15_marugame.png"],
  ["16kojima","boat.kojima","BOATRACE児島","児島","16_kojima.png"],
  ["17miyajima","boat.miyajima","BOATRACE宮島","宮島","17_miyajima.png"],
  ["18tokuyama","boat.tokuyama","BOATRACE徳山","徳山","18_tokuyama.png"],
  ["19shimonoseki","boat.shimonoseki","BOATRACE下関","下関","19_shimonoseki.png"],
  ["20wakamatsu","boat.wakamatsu","BOATRACE若松","若松","20_wakamatsu.png"],
  ["21ashiya","boat.ashiya","BOATRACE芦屋","芦屋","21_ashiya.png"],
  ["22fukuoka","boat.fukuoka","BOATRACE福岡","福岡","22_fukuoka.png"],
  ["23karatsu","boat.karatsu","BOATRACE唐津","唐津","23_karatsu.png"],
  ["24omura","boat.omura","BOATRACE大村","大村","24_omura.png"],
];

function japanYmd(date = new Date()) {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Tokyo", year: "numeric", month: "2-digit", day: "2-digit"
  }).formatToParts(date);
  const get = t => parts.find(x => x.type === t)?.value || "";
  return `${get("year")}${get("month")}${get("day")}`;
}

function savedToken() {
  try {
    if (Keychain.contains(HIM_TOKEN_KEY)) {
      const t = String(Keychain.get(HIM_TOKEN_KEY) || "").trim();
      if (t) return t;
    }
  } catch (_) {}
  try {
    const fm = FileManager.local();
    const path = fm.joinPath(fm.documentsDirectory(), TOKEN_STORE_FILE);
    if (fm.fileExists(path)) {
      const d = JSON.parse(fm.readString(path) || "{}");
      const t = String(d[HIM_TOKEN_KEY] || "").trim();
      if (t) {
        try { Keychain.set(HIM_TOKEN_KEY, t); } catch (_) {}
        return t;
      }
    }
  } catch (_) {}
  return "";
}

async function gh(path, token, method = "GET", body = null) {
  const r = new Request(`https://api.github.com${path}`);
  r.method = method;
  r.timeoutInterval = 30;
  r.headers = {
    Authorization: `Bearer ${token}`,
    Accept: "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
    "User-Agent": "Scriptable-BOAT-SEED-AUTO",
    "Cache-Control": "no-cache, no-store",
  };
  if (body !== null) {
    r.headers["Content-Type"] = "application/json";
    r.body = JSON.stringify(body);
  }
  const data = await r.load();
  const status = r.response?.statusCode ?? 0;
  const text = data.toRawString();
  if (status < 200 || status >= 300) throw new Error(`GitHub API ${status}: ${text.slice(0,300)}`);
  return text ? JSON.parse(text) : {};
}

function githubDecode(content) {
  return Data.fromBase64String(String(content || "").replace(/\s/g, "")).toRawString();
}

function githubEncode(text) {
  return Data.fromString(text).toBase64String();
}

function decodeJwtPayload(url) {
  try {
    const m = String(url).match(/[?&]token=([^&]+)/);
    if (!m) return null;
    const token = decodeURIComponent(m[1]);
    const p = token.split(".")[1];
    if (!p) return null;
    let b64 = p.replace(/-/g, "+").replace(/_/g, "/");
    while (b64.length % 4) b64 += "=";
    return JSON.parse(Data.fromBase64String(b64).toRawString());
  } catch (_) {
    return null;
  }
}

function currentDayDirect(url, ymd) {
  if (!String(url).startsWith("https://manifest.streaks.jp/") || !String(url).includes(".m3u8")) return false;
  const p = decodeJwtPayload(url);
  const start = Number(p?.start || 0);
  if (!Number.isFinite(start) || start <= 0) return false;
  return japanYmd(new Date(start * 1000)) === ymd;
}

function parseSeed(text) {
  const lines = String(text || "").replace(/\r/g, "").split("\n");
  const out = new Map();
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (!line.startsWith("#EXTINF:")) continue;
    const id = line.match(/tvg-id="([^"]+)"/)?.[1];
    if (!id) continue;
    for (let j = i + 1; j < Math.min(lines.length, i + 6); j++) {
      const s = lines[j].trim();
      if (!s) continue;
      if (s.startsWith("#EXTINF:")) break;
      if (s.startsWith("#")) continue;
      if (s.startsWith("http://") || s.startsWith("https://")) out.set(id, s);
      break;
    }
  }
  return out;
}

function findStreamUrl(x) {
  if (!x) return null;
  if (Array.isArray(x)) {
    for (const v of x) { const hit = findStreamUrl(v); if (hit) return hit; }
    return null;
  }
  if (typeof x === "object") {
    if (Array.isArray(x.sources)) {
      for (const s of x.sources) {
        const u = typeof s?.src === "string" ? s.src : (typeof s?.url === "string" ? s.url : "");
        if (u.includes(".m3u8")) return u;
      }
    }
    for (const v of Object.values(x)) {
      if (typeof v === "string" && v.includes(".m3u8")) return v;
      if (v && typeof v === "object") { const hit = findStreamUrl(v); if (hit) return hit; }
    }
  }
  return null;
}

async function fetchBoat(apiId, ymd) {
  const api = `https://playback.api.streaks.jp/v1/projects/cp-boatrace-prod/medias/ref:lm-br-${apiId}-tokyo-${ymd}?audio_only=false`;
  try {
    const r = new Request(api);
    r.timeoutInterval = 15;
    r.headers = {
      "User-Agent": UA,
      Origin: "https://front.player.boatrace-cdn.jp",
      Referer: "https://front.player.boatrace-cdn.jp/",
      Accept: "application/json,*/*",
      "Cache-Control": "no-cache, no-store",
      Pragma: "no-cache",
    };
    const d = await r.loadJSON();
    const u = findStreamUrl(d);
    return currentDayDirect(u, ymd) ? u : null;
  } catch (_) {
    return null;
  }
}

async function fetchInChunks(ymd) {
  const result = new Map();
  for (let i = 0; i < BOAT.length; i += 6) {
    const chunk = BOAT.slice(i, i + 6);
    const rows = await Promise.all(chunk.map(async row => [row[1], await fetchBoat(row[0], ymd)]));
    for (const [id, url] of rows) if (url) result.set(id, url);
  }
  return result;
}

function buildSeed(urls) {
  const lines = ["#EXTM3U", ""];
  for (const [_apiId, id, display, _venue, logoFile] of BOAT) {
    const url = urls.get(id);
    if (!url) continue;
    lines.push(
      `#EXTINF:-1 tvg-id="${id}" tvg-name="${display}" tvg-logo="${LOGO_BASE}/${logoFile}" group-title="ボートレース",${display}`,
      url,
      ""
    );
  }
  return lines.join("\n").trimEnd() + "\n";
}

async function notifyError(message) {
  try {
    const n = new Notification();
    n.title = "BOAT SEED 自動更新エラー";
    n.body = String(message).slice(0, 500);
    await n.schedule();
  } catch (_) {}
}

try {
  const token = savedToken();
  if (!token) throw new Error("Free Wi-Fi GitHub Tokenが未保存。先に『公営これ一発 v17』を一度実行してください。");

  const ymd = japanYmd();
  const current = await gh(`${API_REPO}/contents/${SEED_PATH}?ref=${HIM_BRANCH}`, token);
  const oldText = githubDecode(current.content || "");
  const oldEntries = parseSeed(oldText);

  // 当日JWTだけを引き継ぐ。前日以前のURLはここで自動的に捨てる。
  const merged = new Map();
  for (const [id, url] of oldEntries) if (currentDayDirect(url, ymd)) merged.set(id, url);

  // iPhoneの日本回線から24場を再取得。取得できた場だけ上書きする。
  const fresh = await fetchInChunks(ymd);
  for (const [id, url] of fresh) merged.set(id, url);

  if (merged.size === 0) throw new Error("当日Streaks SEEDを1場も取得できなかったため、GitHubのSEEDは変更していません。");

  const newText = buildSeed(merged);
  if (newText !== oldText) {
    await gh(`${API_REPO}/contents/${SEED_PATH}`, token, "PUT", {
      message: `Auto refresh iPhone BOAT seed ${ymd}`,
      content: githubEncode(newText),
      branch: HIM_BRANCH,
      sha: current.sha,
    });
  }

  console.log(`BOAT SEED AUTO ${ymd}: fresh=${fresh.size}, current-day-total=${merged.size}, changed=${newText !== oldText}`);
} catch (e) {
  console.error(e);
  await notifyError(e?.message || String(e));
}

Script.complete();
