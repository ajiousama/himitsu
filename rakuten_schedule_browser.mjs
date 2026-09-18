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
  await cmd("Network.enable");
  const networkUrls = [];
  const interestingRequests = [];
  ws.addEventListener("message", ev => {
    try {
      const m=JSON.parse(ev.data);
      if (m.method === "Network.requestWillBeSent") {
        const req=m.params?.request || {};
        const u = req.url || "";
        if (/rakuten|channel|schedule|program|epg|content|rmc-cx\.api/i.test(u)) {
          networkUrls.push(u);
          if (/rmc-cx\.api\.rakuten\.co\.jp\/v\d+\/web\/(events|blocks)/i.test(u)) {
            interestingRequests.push({
              requestId:m.params?.requestId || "",
              url:u,
              method:req.method || "",
              postData:req.postData || "",
              headers:req.headers || {}
            });
          }
        }
      }
      if (m.method === "Network.responseReceived") {
        const u=m.params?.response?.url || "";
        if (/rmc-cx\.api\.rakuten\.co\.jp\/v\d+\/web\/(events|blocks)/i.test(u)) {
          const hit=interestingRequests.findLast?.(x=>x.url===u) || [...interestingRequests].reverse().find(x=>x.url===u);
          if (hit) {
            hit.status=m.params?.response?.status;
            hit.mimeType=m.params?.response?.mimeType || "";
            hit.responseRequestId=m.params?.requestId || "";
          }
        }
      }
    } catch {}
  });
  const pages={};
  for (const date of dates) {
    const url=`https://channel.rakuten.co.jp/schedule/${date}`;
    await cmd("Page.navigate",{url});
    await sleep(6500);
    const selected = await evalValue(`(async () => {
      const norm = v => String(v || '').replace(/\\s+/g,' ').trim();

      // Native select path.
      const selects=[...document.querySelectorAll('select')];
      const nativeSelect=selects.find(x => [...x.options].some(o => norm(o.textContent).includes('年齢制限')));
      if (nativeSelect) {
        const o=[...nativeSelect.options].find(o => norm(o.textContent).includes('年齢制限'));
        const setter=Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype,'value')?.set;
        if (setter) setter.call(nativeSelect,o.value); else nativeSelect.value=o.value;
        nativeSelect.dispatchEvent(new Event('input',{bubbles:true}));
        nativeSelect.dispatchEvent(new Event('change',{bubbles:true}));
        return 'native-select';
      }

      // Current R Channel UI may render the category selector as a custom
      // button/div instead of a <select>. Open the control and click the
      // visible age-restricted option.
      const all=[...document.querySelectorAll('button,[role=button],[role=combobox],div,span')];
      const opener=all.find(el => {
        const t=norm(el.textContent);
        return t && t.length < 80 && (t === 'すべて' || t.includes('チャンネル')) &&
          (el.matches('button,[role=button],[role=combobox]') || getComputedStyle(el).cursor === 'pointer');
      });
      if (opener) opener.click();
      await new Promise(r => setTimeout(r, 500));

      const options=[...document.querySelectorAll('[role=option],button,li,div,span')];
      const option=options.find(el => {
        const t=norm(el.textContent);
        if (!t || t.length > 80 || !t.includes('年齢制限')) return false;
        const r=el.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
      });
      if (option) {
        option.click();
        return 'custom-option';
      }
      return false;
    })()`);
    await sleep(5000);
    const text = await evalValue("document.body ? document.body.innerText : ''");

    // If the selector interaction did not work but the restricted channels are
    // already present in the DOM, accept the page as selected. This happens in
    // some responsive layouts where all category panes stay mounted.
    const bodyText=String(text||"");
    const hasRestricted = /CH\\s*(239|240|241|242|243)\\b/i.test(bodyText);
    const m241=/CH\\s*241\\b/i.exec(bodyText);
    const snippet241=m241 ? bodyText.slice(Math.max(0,m241.index-120), Math.min(bodyText.length,m241.index+1800)) : '';
    const filteredNetwork=[...new Set(networkUrls)].filter(u => /rakuten|channel|schedule|program|epg|content/i.test(u));
    const api=[];
    for (const x of interestingRequests.slice(-20)) {
      let body="";
      const rid=x.responseRequestId || x.requestId;
      if (rid) {
        try { body=(await cmd("Network.getResponseBody",{requestId:rid}))?.body || ""; } catch {}
      }
      api.push({...x,body:String(body).slice(0,12000)});
    }
    pages[date]={selected:Boolean(selected || hasRestricted),method:selected || (hasRestricted?'already-visible':false),snippet241,text:bodyText,network:filteredNetwork.slice(-120),api};
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
