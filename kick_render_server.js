const http = require("http");
const { URL } = require("url");
const channels = require("./kick_channels.json");
const PORT = Number(process.env.PORT || 10000);
const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36";
const VERSION = "2026-09-16-kick-render-v3-livestream";
async function getJson(url){try{const r=await fetch(url,{headers:{accept:"application/json, text/plain, */*","user-agent":UA,referer:"https://kick.com/","cache-control":"no-cache"},cache:"no-store"});if(r.ok)return await r.json()}catch{}return null}
function findM3u8(v){if(!v)return null;if(typeof v==="string")return /^https?:\/\//i.test(v)&&v.includes(".m3u8")?v:null;if(Array.isArray(v)){for(const x of v){const h=findM3u8(x);if(h)return h}}else if(typeof v==="object"){for(const x of Object.values(v)){const h=findM3u8(x);if(h)return h}}return null}
async function alive(url){if(!url)return false;try{const r=await fetch(url,{headers:{"user-agent":UA,referer:"https://kick.com/"},cache:"no-store"});if(!r.ok)return false;return (await r.text()).includes("#EXTM3U")}catch{return false}}
async function resolveSlug(slug){for(const ep of [`https://kick.com/api/v2/channels/${encodeURIComponent(slug)}/livestream`,`https://kick.com/api/v1/channels/${encodeURIComponent(slug)}/livestream`,`https://kick.com/api/v2/channels/${encodeURIComponent(slug)}/playback-url`,`https://kick.com/api/v2/channels/${encodeURIComponent(slug)}`]){const data=await getJson(ep),url=findM3u8(data);if(url&&await alive(url))return {slug,playback:url}}return null}
async function resolveLive(item){for(const slug of [...new Set([item.slug,...(item.slug_aliases||[])].filter(Boolean))]){const h=await resolveSlug(slug);if(h)return h}return null}
function headers(res){res.setHeader("Cache-Control","no-store");res.setHeader("Access-Control-Allow-Origin","*");res.setHeader("X-Kick-Resolver-Version",VERSION)}
function json(res,status,obj){headers(res);res.statusCode=status;res.setHeader("Content-Type","application/json; charset=utf-8");res.end(JSON.stringify(obj))}
function redirect(res,url){headers(res);res.statusCode=302;res.setHeader("Location",url);res.end()}
async function handler(req,res){const u=new URL(req.url,"http://localhost");if(u.pathname==="/health")return json(res,200,{ok:true,resolver:VERSION});if(u.pathname!=="/kick"&&u.pathname!=="/api/kick")return json(res,404,{error:"not found",resolver:VERSION});const aliases={gccx:"kick.gccx",gccx2:"kick.gccx2",nogizaka:"kick.nogizaka",nogi:"kick.nogizaka"};const key=String(u.searchParams.get("ch")||"").toLowerCase(),id=aliases[key]||key,item=channels.find(x=>String(x.tvg_id||"").toLowerCase()===id);if(!item)return json(res,404,{error:"unknown KICK channel",resolver:VERSION});const hit=await resolveLive(item);if(!hit)return json(res,503,{error:"KICK live playback unavailable",tvg_id:item.tvg_id,slug:item.slug,resolver:VERSION});return redirect(res,hit.playback)}
http.createServer((req,res)=>handler(req,res).catch(e=>json(res,500,{error:"internal error",detail:String(e?.message||e),resolver:VERSION}))).listen(PORT,"0.0.0.0",()=>console.log(`KICK resolver ${VERSION} listening on ${PORT}`));
