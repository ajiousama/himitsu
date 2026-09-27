const UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/140 Safari/537.36";
const VERSION = "2026-09-27-cloudflare-v1";
const ALLOWED = [
  "streaks.jp","googlevideo.com","youtube.com","youtu.be","youtube-nocookie.com","ytimg.com",
  "charandom.blog","jp-primehome.com","boatrace.jp","jlc.ne.jp","githubusercontent.com","github.com","greenchannel.jp"
];
const EXACT = new Set(["118.68.167.114","118.21.101.221"]);

const KICK_CHANNELS = [
  {tvg_id:"kick.gccx2",slug:"joshua-hkd",channel_id:null,search:"ゲームセンターCX",match_terms:["ゲームセンター","CX","gccx","GameCenter CX","joshua-hkd"],slug_aliases:["joshua-hkd"]},
  {tvg_id:"kick.nogizaka",slug:"nogi20110821",channel_id:"9gFdFdQKcdgr",search:"乃木坂",match_terms:["乃木坂","nogi"],slug_aliases:["nogi20110821"]},
  {tvg_id:"kick.kodoku",slug:null,channel_id:null,search:"孤独のグルメ",match_terms:["孤独のグルメ","kodoku"],slug_aliases:[]},
  {tvg_id:"kick.kujotaizai",slug:"wekiukk7",channel_id:"92858985",search:"九条の大罪",match_terms:["九条の大罪","wekiukk7"],slug_aliases:["wekiukk7"]}
];

function cors(extra={}) { return {"access-control-allow-origin":"*","access-control-allow-methods":"GET,HEAD,OPTIONS","access-control-allow-headers":"Range,Content-Type,Accept","access-control-expose-headers":"Content-Length,Content-Range,Accept-Ranges,Content-Type",...extra}; }
function json(data,status=200,extra={}) { return new Response(JSON.stringify(data),{status,headers:cors({"content-type":"application/json; charset=utf-8","cache-control":"no-store",...extra})}); }
function text(body,status=200,ctype="text/plain; charset=utf-8",extra={}) { return new Response(body,{status,headers:cors({"content-type":ctype,"cache-control":"no-store",...extra})}); }
function redirect(url,status=302,extra={}) { return new Response(null,{status,headers:cors({location:url,"cache-control":"no-store",...extra})}); }
function abs(base,v){ try{return new URL(v,base).toString()}catch{return v} }
function allowedHost(h){ h=String(h||"").toLowerCase().replace(/\.$/,""); return EXACT.has(h)||ALLOWED.some(s=>h===s||h.endsWith("."+s)); }
function validateTarget(raw){ let u; try{u=new URL(raw)}catch{throw new Error("invalid url")}; if(!["http:","https:"].includes(u.protocol)||u.username||u.password)throw new Error("unsupported url"); if(!allowedHost(u.hostname))throw new Error("target host not allowed"); return u; }

function upstreamHeaders(u,req){
  const h=new Headers({"user-agent":UA,"accept":req.headers.get("accept")||"*/*","accept-language":req.headers.get("accept-language")||"ja-JP,ja;q=.9,en;q=.7","cache-control":"no-cache","pragma":"no-cache"});
  const range=req.headers.get("range"); if(range)h.set("range",range);
  const host=u.hostname.toLowerCase(),full=u.href.toLowerCase();
  if(host.endsWith("streaks.jp")){
    if(full.includes("boatrace")||full.includes("cp-boatrace-prod")){h.set("origin","https://front.player.boatrace-cdn.jp");h.set("referer","https://front.player.boatrace-cdn.jp/")}
    else{h.set("origin","https://tver.jp");h.set("referer","https://tver.jp/")}
  } else if(host.endsWith("googlevideo.com")){h.set("origin","https://www.youtube.com");h.set("referer","https://www.youtube.com/")}
  else if(host.endsWith("charandom.blog"))h.set("referer","https://haru.charandom.blog/");
  else if(host==="118.21.101.221"){const port=u.port||"80",cam=port==="81"?"cam02":port==="90"?"cam03":"cam01";h.set("referer",`https://www.kankoko.com/cam/web-cam/${cam}/index.html`);h.set("accept","multipart/x-mixed-replace,image/jpeg,image/*,*/*;q=.8")}
  return h;
}
async function fetchValidated(raw,req){
  let u=validateTarget(raw);
  for(let i=0;i<6;i++){
    const ac=new AbortController(),timer=setTimeout(()=>ac.abort(),20000); let r;
    try{r=await fetch(u,{method:req.method==="HEAD"?"HEAD":"GET",headers:upstreamHeaders(u,req),redirect:"manual",signal:ac.signal})} finally{clearTimeout(timer)}
    if(r.status>=300&&r.status<400&&r.headers.get("location")){u=validateTarget(new URL(r.headers.get("location"),u).href);continue}
    return r;
  }
  throw new Error("too many redirects");
}
function proxyUrl(origin,target){return `${origin}/proxy?url=${encodeURIComponent(target)}`}
function rewriteManifest(body,base,origin){return String(body).split(/\r?\n/).map(line=>{if(!line)return line;if(line.startsWith("#"))return line.replace(/URI="([^"]+)"/g,(_,x)=>`URI="${proxyUrl(origin,new URL(x,base).href)}"`).replace(/URI='([^']+)'/g,(_,x)=>`URI='${proxyUrl(origin,new URL(x,base).href)}'`);try{return proxyUrl(origin,new URL(line.trim(),base).href)}catch{return line}}).join("\n")}

async function handleProxy(req,url){
  const target=url.searchParams.get("url"); if(!target)return text("missing url",400);
  try{
    const r=await fetchValidated(target,req),final=r.url||target,ct=(r.headers.get("content-type")||"").toLowerCase();
    const path=(()=>{try{return new URL(final).pathname.toLowerCase()}catch{return ""}})();
    const headers=cors({"cache-control":r.headers.get("cache-control")||"public,max-age=5"});
    for(const n of ["content-type","content-range","accept-ranges","etag","last-modified"]){const v=r.headers.get(n);if(v)headers[n]=v}
    if(req.method==="HEAD"){const len=r.headers.get("content-length");if(len)headers["content-length"]=len;return new Response(null,{status:r.status,headers})}
    if(ct.includes("mpegurl")||path.endsWith(".m3u8"))return text(rewriteManifest(await r.text(),final,url.origin),r.status,"application/vnd.apple.mpegurl; charset=utf-8");
    return new Response(r.body,{status:r.status,headers});
  }catch(e){return text("proxy error: "+(e?.message||e),502)}
}

async function getJson(url){for(let i=0;i<3;i++){try{const r=await fetch(url,{headers:{accept:"application/json, text/plain, */*","user-agent":UA,referer:"https://kick.com/","cache-control":"no-cache",pragma:"no-cache"},cache:"no-store"});if(r.ok){try{return await r.json()}catch{}}}catch{}if(i<2)await new Promise(r=>setTimeout(r,250*(i+1)))}return null}
async function getHls(url,referer="https://kick.com/"){const r=await fetch(url,{headers:{accept:"application/vnd.apple.mpegurl, application/x-mpegURL, text/plain, */*","user-agent":UA,referer,"cache-control":"no-cache",pragma:"no-cache"},cache:"no-store"});if(!r.ok)throw new Error(`HLS fetch failed ${r.status}`);return await r.text()}
function findM3u8(v){if(!v)return null;if(typeof v==="string")return /^https?:\/\//i.test(v)&&v.includes(".m3u8")?v:null;if(Array.isArray(v)){for(const x of v){const h=findM3u8(x);if(h)return h}}else if(typeof v==="object"){for(const k of ["source","playback_url","playbackUrl","hls_url","hlsUrl","stream_url","streamUrl"]){const h=findM3u8(v[k]);if(h)return h}for(const x of Object.values(v)){const h=findM3u8(x);if(h)return h}}return null}
function playbackOf(o){return o?.playback_url||o?.playbackUrl||o?.stream?.playback_url||o?.stream?.playbackUrl||o?.livestream?.playback_url||o?.livestream?.playbackUrl||o?.data?.playback_url||o?.data?.playbackUrl||null}
function sameIvs(url,id){return !!url&&!!id&&url.includes(".channel."+id+".m3u8")}
async function resolveSlug(slug,expected){if(!slug)return null;const d=await getJson("https://kick.com/api/v2/channels/"+encodeURIComponent(slug));if(!d)return null;const p=playbackOf(d);if(!p)return null;if(expected){if(/^\d+$/.test(expected)){const id=String(d.id||d.channel_id||d.channel?.id||"").trim();if(id!==expected)return null}else if(!sameIvs(p,expected))return null}return {slug:d.slug||slug,playback:p}}
async function resolveKick(item){const expected=String(item.channel_id||"").trim();for(const slug of [...new Set([item.slug,...(item.slug_aliases||[])].filter(Boolean))]){const h=await resolveSlug(slug,expected);if(h)return h}return null}
function pickVariant(body,source){const ls=String(body).replace(/\r/g,"").split("\n"),c=[];for(let i=0;i<ls.length;i++){if(!ls[i].trim().startsWith("#EXT-X-STREAM-INF:"))continue;const bw=Number((ls[i].match(/BANDWIDTH=(\d+)/i)||[])[1]||0);for(let j=i+1;j<ls.length;j++){const n=ls[j].trim();if(!n)continue;if(n.startsWith("#"))break;c.push({bw,url:abs(source,n)});break}}c.sort((a,b)=>b.bw-a.bw);return c[0]?.url||null}
function clipPlaylist(body,source,offset,duration,label="KICK"){
  const ls=String(body).replace(/\r/g,"").split("\n"),header=[],groups=[];let tags=[],inf=null;
  const hdr=l=>l==="#EXTM3U"||/^#EXT-X-(VERSION|TARGETDURATION|MEDIA-SEQUENCE|DISCONTINUITY-SEQUENCE|PLAYLIST-TYPE|INDEPENDENT-SEGMENTS|ALLOW-CACHE)/.test(l);
  for(const raw of ls){let l=raw.trim();if(!l||l==="#EXT-X-ENDLIST")continue;if(l.startsWith("#EXTINF:")){inf={line:l,seconds:Number((l.match(/^#EXTINF:([0-9.]+)/)||[])[1]||0)};continue}if(l.startsWith("#")){l=l.replace(/URI="([^"]+)"/g,(_,x)=>`URI="${abs(source,x)}"`);if(!inf&&!groups.length&&!tags.length&&hdr(l))header.push(l);else tags.push(l);continue}if(inf){groups.push({tags,inf:inf.line,seconds:Math.max(0,inf.seconds||0),uri:abs(source,l)});tags=[];inf=null}}
  if(!groups.length)throw new Error("no media segments found");let cum=0,skipped=0,key=null,map=null;const sel=[];
  for(const g of groups){for(const t of g.tags){if(t.startsWith("#EXT-X-KEY:"))key=t;if(t.startsWith("#EXT-X-MAP:"))map=t}const s=cum,e=cum+g.seconds;cum=e;if(e<=offset+.001){skipped++;continue}if(s>=offset+duration-.001)break;const tt=[...g.tags];if(!sel.length){if(key&&!tt.some(x=>x.startsWith("#EXT-X-KEY:")))tt.unshift(key);if(map&&!tt.some(x=>x.startsWith("#EXT-X-MAP:")))tt.unshift(map);tt.unshift("#EXT-X-START:TIME-OFFSET=0,PRECISE=YES",`# ${label} clip requested offset=${offset}s actual_segment_start=${s.toFixed(3)}s`)}sel.push({...g,tags:tt})}
  if(!sel.length)throw new Error(`offset ${offset}s is outside available replay`);const out=header.map(l=>{const m=l.match(/^#EXT-X-MEDIA-SEQUENCE:(\d+)/);return m?`#EXT-X-MEDIA-SEQUENCE:${Number(m[1])+skipped}`:l});if(!out.includes("#EXTM3U"))out.unshift("#EXTM3U");for(const g of sel)out.push(...g.tags,g.inf,g.uri);out.push("#EXT-X-ENDLIST");return out.join("\n")+"\n";
}
async function handleKick(url){
  const vod=String(url.searchParams.get("vod")||"").trim();
  if(vod){if(!/^[A-Za-z0-9_-]{6,120}$/.test(vod))return json({error:"invalid KICK VOD id",resolver:VERSION},400);let start=Number(url.searchParams.get("start")||0),duration=Number(url.searchParams.get("duration")||0);if(!Number.isFinite(start)||start<0)start=0;if(!Number.isFinite(duration)||duration<0)duration=0;start=Math.floor(Math.min(start,604800));duration=duration?Math.max(30,Math.min(Math.floor(duration),43200)):0;const d=await getJson("https://kick.com/api/v1/video/"+encodeURIComponent(vod));if(!d)return json({error:"KICK VOD metadata unavailable",vod,resolver:VERSION},404);const src=findM3u8(d);if(!src)return json({error:"KICK VOD media unavailable",vod,resolver:VERSION},410);if(!start&&!duration)return redirect(src);try{let media=src,p=await getHls(media);for(let depth=0;depth<3&&/#EXT-X-STREAM-INF:/i.test(p);depth++){const v=pickVariant(p,media);if(!v)throw new Error("master playlist has no variant");media=v;p=await getHls(media)}const out=duration?clipPlaylist(p,media,start,duration,"KICK"):p.split(/\r?\n/).map(l=>l.startsWith("#")?l.replace(/URI="([^"]+)"/g,(_,x)=>`URI="${abs(media,x)}"`):(l.trim()?abs(media,l.trim()):l)).join("\n");return text(out,200,"application/vnd.apple.mpegurl; charset=utf-8")}catch(e){return json({error:"KICK VOD seek playlist failed",detail:String(e?.message||e),resolver:VERSION},502)}}
  const key=String(url.searchParams.get("ch")||"").toLowerCase(),aliases={gccx:"kick.gccx",gccx2:"kick.gccx2",nogizaka:"kick.nogizaka",nogi:"kick.nogizaka",kodoku:"kick.kodoku",kujotaizai:"kick.kujotaizai"},id=aliases[key]||key,item=KICK_CHANNELS.find(x=>x.tvg_id===id);if(!item)return json({error:"unknown KICK channel",resolver:VERSION},404);try{const hit=await resolveKick(item);if(!hit)return json({error:"KICK live playback unavailable",tvg_id:item.tvg_id,slug:item.slug,resolver:VERSION},503);return redirect(hit.playback,302,{"x-kick-resolved-slug":hit.slug})}catch(e){return json({error:"KICK resolver failed",detail:String(e?.message||e),resolver:VERSION},502)}
}

function allowedHaru(raw){try{const u=new URL(raw);return u.protocol==="https:"&&u.hostname==="haru.charandom.blog"&&/\/stream\/jp\/[^/]+\/replay\.m3u8$/i.test(u.pathname)}catch{return false}}
async function handleHaru(url){const src=String(url.searchParams.get("src")||"").trim();let offset=Number(url.searchParams.get("offset")||0),duration=Number(url.searchParams.get("duration")||600);if(!Number.isFinite(offset))offset=0;if(!Number.isFinite(duration))duration=600;offset=Math.max(0,Math.min(Math.floor(offset),28800));duration=Math.max(30,Math.min(Math.floor(duration),3600));if(!allowedHaru(src))return json({error:"invalid HARU replay source",resolver:VERSION},400);try{let media=src,p=await getHls(media,"https://haru.charandom.blog/");for(let depth=0;depth<2&&/#EXT-X-STREAM-INF:/i.test(p);depth++){const v=pickVariant(p,media);if(!v)throw new Error("master playlist has no variant");media=v;p=await getHls(media,"https://haru.charandom.blog/")}return text(clipPlaylist(p,media,offset,duration,"HARU"),200,"application/vnd.apple.mpegurl; charset=utf-8")}catch(e){return json({error:"HARU clip playlist failed",detail:String(e?.message||e),resolver:VERSION},502)}}

export default {
  async fetch(req){
    const url=new URL(req.url);
    if(req.method==="OPTIONS")return new Response(null,{status:204,headers:cors()});
    if(!["GET","HEAD"].includes(req.method))return text("method not allowed",405);
    if(url.pathname==="/"||url.pathname==="/health")return json({ok:true,service:"freewifi-edge",version:VERSION});
    if(url.pathname==="/proxy")return handleProxy(req,url);
    if(url.pathname==="/kick")return handleKick(url);
    if(url.pathname==="/haru-clip")return handleHaru(url);
    return text("not found",404);
  }
};
