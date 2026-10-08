import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const out = process.argv[2] || "rakuten/browser_live_urls.json";
const targets = [
  { apiId: 125, slot: 5, title: "セクシーエンタメチャンネル" },
  { apiId: 124, slot: 4, title: "おとなの歓楽街 by MEN’S NECO" },
  { apiId: 121, slot: 2, title: "アイドル・グラビア" },
  { apiId: 123, slot: 1, title: "刺激ストロング" },
  { apiId: 122, slot: 3, title: "映画（年齢制限あり）" }
];

const names = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"];
let chrome = null;
for (const name of names) {
  const p = spawnSync("which", [name], { encoding: "utf8" });
  if (p.status === 0 && p.stdout.trim()) { chrome = p.stdout.trim(); break; }
}
if (!chrome) throw new Error("Chrome/Chromium not found");

const profile = mkdtempSync(join(tmpdir(), "rch-live-"));
const port = 9231;
const child = spawn(chrome, [
  "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
  "--autoplay-policy=no-user-gesture-required",
  "--remote-debugging-port=" + port,
  "--user-data-dir=" + profile,
  "--lang=ja-JP", "about:blank"
], { stdio: "ignore" });

const sleep = ms => new Promise(r => setTimeout(r, ms));
async function getJson(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(String(r.status) + " " + url);
  return r.json();
}

let ws;
try {
  let pages = [];
  for (let i = 0; i < 50; i++) {
    try {
      pages = await getJson("http://127.0.0.1:" + port + "/json/list");
      if (pages.length) break;
    } catch {}
    await sleep(200);
  }
  const page = pages.find(x => x.type === "page") || pages[0];
  if (!page || !page.webSocketDebuggerUrl) throw new Error("DevTools page target not found");

  ws = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    ws.addEventListener("open", resolve, { once: true });
    ws.addEventListener("error", reject, { once: true });
  });

  let seq = 0;
  const pending = new Map();
  ws.addEventListener("message", ev => {
    const m = JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) {
      const p = pending.get(m.id);
      pending.delete(m.id);
      if (m.error) p.reject(new Error(m.error.message)); else p.resolve(m.result);
    }
  });
  function cmd(method, params = {}) {
    return new Promise((resolve, reject) => {
      const id = ++seq;
      pending.set(id, { resolve, reject });
      ws.send(JSON.stringify({ id, method, params }));
    });
  }
  async function evalValue(expression) {
    const r = await cmd("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.text || "Runtime.evaluate failed");
    return r.result ? r.result.value : undefined;
  }

  const captured = {};
  const seen = [];
  ws.addEventListener("message", ev => {
    try {
      const m = JSON.parse(ev.data);
      if (m.method !== "Network.requestWillBeSent") return;
      const u = (m.params && m.params.request && m.params.request.url) || "";
      if (!/fast\.rakuten\.tv/i.test(u) || !/rchannels-\d+-playout\/master\.m3u8/i.test(u)) return;
      seen.push(u);
      const mm = /rchannels-(\d+)-playout\/master\.m3u8/i.exec(u);
      if (!mm) return;
      const slot = Number(mm[1]);
      const t = targets.find(x => x.slot === slot);
      if (t) captured[String(t.apiId)] = u;
    } catch {}
  });

  await cmd("Runtime.enable");
  await cmd("Page.enable");
  await cmd("Network.enable");
  await cmd("Page.navigate", { url: "https://channel.rakuten.co.jp/" });
  await sleep(9000);

  const body = await evalValue("document.body ? document.body.innerText : ''");
  console.error("BODY_HAS_RESTRICTED", /年齢制限|セクシーエンタメ|刺激ストロング/.test(String(body || "")));
  const matchLinks = await evalValue("(()=>[...document.querySelectorAll('a')].map(a=>({text:String(a.textContent||'').replace(/\\s+/g,' ').trim(),href:a.href||''})).filter(x=>/セクシー|歓楽街|グラビア|刺激ストロング|年齢制限|CH\\s*(239|240|241|242|243)|channel/i.test(x.text+' '+x.href)).slice(0,120))()");
  console.error("MATCH_LINKS", JSON.stringify(matchLinks));
  for (const key of ["セクシーエンタメ","おとなの歓楽街","アイドル・グラビア","刺激ストロング","映画（年齢制限あり）","CH 239","CH 240","CH 241","CH 242","CH 243"]) {
    const i = String(body || "").indexOf(key);
    if (i >= 0) console.error("BODY_SNIP", key, JSON.stringify(String(body || "").slice(Math.max(0,i-200), i+900)));
  }

  const ageExpr = "(async()=>{const n=v=>String(v||'').replace(/\\s+/g,' ').trim();const vis=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0};const xs=[...document.querySelectorAll('button,[role=button],[role=tab],[role=option],li,div,span')].filter(vis);const x=xs.find(e=>{const t=n(e.textContent);return t&&t.length<100&&t.includes('年齢制限')});if(!x)return false;let c=x;for(let i=0;i<6&&c;i++,c=c.parentElement){if(c.matches&&c.matches('button,a,[role=button],[role=tab],[role=option]')){c.click();return true}try{if(getComputedStyle(c).cursor==='pointer'){c.click();return true}}catch{}}x.click();return true})()";
  console.error("AGE_FILTER_CLICK", await evalValue(ageExpr));
  await sleep(3000);

  for (const t of targets) {
    if (captured[String(t.apiId)]) continue;
    const expr = "(()=>{const needle=" + JSON.stringify(t.title) + ";const n=v=>String(v||'').replace(/\\s+/g,' ').trim();const vis=e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0};let xs=[...document.querySelectorAll('a,button,[role=button],div,span')].filter(vis).filter(e=>n(e.textContent).includes(needle));xs.sort((a,b)=>n(a.textContent).length-n(b.textContent).length);let x=xs[0];if(!x)return false;for(let i=0;i<8&&x;i++,x=x.parentElement){if(x.matches&&x.matches('a,button,[role=button]')){x.click();return true}try{if(getComputedStyle(x).cursor==='pointer'){x.click();return true}}catch{}}xs[0].click();return true})()";
    const clicked = await evalValue(expr);
    console.error("CHANNEL_CLICK", t.apiId, clicked);
    await sleep(5500);
  }

  const payload = {
    captured_at_utc: new Date().toISOString(),
    channels: captured,
    captured_count: Object.keys(captured).length,
    seen_urls: [...new Set(seen)]
  };
  writeFileSync(out, JSON.stringify(payload, null, 2) + "\n", "utf8");
  console.log(JSON.stringify({
    captured_count: payload.captured_count,
    channel_ids: Object.keys(captured),
    seen_count: payload.seen_urls.length
  }));
} finally {
  try { if (ws) ws.close(); } catch {}
  try { child.kill("SIGTERM"); } catch {}
  try { rmSync(profile, { recursive: true, force: true }); } catch {}
}
