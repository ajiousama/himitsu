import { spawn, spawnSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const dates = process.argv.slice(2);
if (!dates.length) {
  console.error("usage: node rakuten_schedule_browser.mjs YYYY-MM-DD [...]");
  process.exit(2);
}
const candidates = ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"];
let chrome = null;
for (const name of candidates) {
  const p = spawnSync("which", [name], { encoding: "utf8" });
  if (p.status === 0 && p.stdout.trim()) { chrome = p.stdout.trim(); break; }
}
if (!chrome) {
  console.error("Chrome/Chromium not found");
  process.exit(3);
}
const profile = mkdtempSync(join(tmpdir(), "rch-chrome-"));
const port = 9229;
const child = spawn(chrome, [
  "--headless=new", "--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage",
  `--remote-debugging-port=${port}`, `--user-data-dir=${profile}`,
  "--lang=ja-JP", "about:blank"
], { stdio: "ignore" });

const sleep = ms => new Promise(r => setTimeout(r, ms));
async function json(url, init={}) {
  const r = await fetch(url, init);
  if (!r.ok) throw new Error(`${r.status} ${url}`);
  return r.json();
}
let ws;
try {
  let targets = [];
  for (let i=0; i<40; i++) {
    try { targets = await json(`http://127.0.0.1:${port}/json/list`); if (targets.length) break; } catch {}
    await sleep(250);
  }
  const target = targets.find(t => t.type === "page") || targets[0];
  if (!target?.webSocketDebuggerUrl) throw new Error("DevTools target not found");
  ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve,reject) => {
    ws.addEventListener("open", resolve, {once:true});
    ws.addEventListener("error", reject, {once:true});
  });
  let seq=0;
  const pending=new Map();
  ws.addEventListener("message", ev => {
    const m=JSON.parse(ev.data);
    if (m.id && pending.has(m.id)) {
      const {resolve,reject}=pending.get(m.id); pending.delete(m.id);
      if (m.error) reject(new Error(m.error.message)); else resolve(m.result);
    }
  });
  function cmd(method, params={}) {
    return new Promise((resolve,reject) => {
      const id=++seq; pending.set(id,{resolve,reject});
      ws.send(JSON.stringify({id,method,params}));
    });
  }
  async function evalValue(expression) {
    const r=await cmd("Runtime.evaluate",{expression,returnByValue:true,awaitPromise:true});
    if (r.exceptionDetails) throw new Error(r.exceptionDetails.text || "Runtime.evaluate failed");
    return r.result?.value;
  }
  await cmd("Runtime.enable");
  await cmd("Page.enable");
  const pages={};
  for (const date of dates) {
    const url=`https://channel.rakuten.co.jp/schedule/${date}`;
    await cmd("Page.navigate",{url});
    await sleep(6500);
    const selected = await evalValue(`(() => {
      const selects=[...document.querySelectorAll('select')];
      const s=selects.find(x => [...x.options].some(o => (o.textContent||'').includes('年齢制限')));
      if (!s) return false;
      const o=[...s.options].find(o => (o.textContent||'').includes('年齢制限'));
      const setter=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value')?.set;
      if (setter) setter.call(s,o.value); else s.value=o.value;
      s.dispatchEvent(new Event('input',{bubbles:true}));
      s.dispatchEvent(new Event('change',{bubbles:true}));
      return true;
    })()`);
    await sleep(4000);
    const text = await evalValue("document.body ? document.body.innerText : ''");
    pages[date]={selected:Boolean(selected),text:String(text||"")};
  }
  console.log(JSON.stringify({pages}));
} catch (e) {
  console.error(e?.stack || String(e));
  process.exitCode=1;
} finally {
  try { ws?.close(); } catch {}
  try { child.kill("SIGTERM"); } catch {}
  try { rmSync(profile,{recursive:true,force:true}); } catch {}
}
