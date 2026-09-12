const http = require('node:http');
const { Readable } = require('node:stream');
const dns = require('node:dns').promises;
const net = require('node:net');

const PORT = Number(process.env.PORT || 10000);
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/152 Safari/537.36';
const ALLOWED = [
  'streaks.jp','googlevideo.com','youtube.com','youtu.be','youtube-nocookie.com','ytimg.com',
  'charandom.blog','jp-primehome.com','boatrace.jp','jlc.ne.jp','githubusercontent.com','github.com',
  'greenchannel.jp','live-video.net','kick.com'
];
const EXACT = new Set(['118.68.167.114']);

function priv4(ip){const p=ip.split('.').map(Number);if(p.length!==4)return true;const[a,b]=p;return a===0||a===10||a===127||(a===169&&b===254)||(a===172&&b>=16&&b<=31)||(a===192&&b===168)||(a===100&&b>=64&&b<=127)||a>=224;}
function priv6(ip){const s=ip.toLowerCase();return s==='::'||s==='::1'||s.startsWith('fc')||s.startsWith('fd')||/^fe[89ab]/.test(s);}
function privateIp(ip){const f=net.isIP(ip);return f===4?priv4(ip):f===6?priv6(ip):true;}
function allowedHost(h){
  h=h.toLowerCase().replace(/\.$/,'');
  if(EXACT.has(h)) return true;
  if(ALLOWED.some(s=>h===s||h.endsWith('.'+s))) return true;
  if(h.endsWith('.amazonaws.com') && h.includes('video-weaver.')) return true;
  return false;
}
async function checked(raw){
  let u; try{u=new URL(raw);}catch{throw Error('invalid url');}
  if(!['http:','https:'].includes(u.protocol)||u.username||u.password)throw Error('unsupported url');
  const h=u.hostname.toLowerCase();
  if(!allowedHost(h))throw Error('target host not allowed: '+h);
  if(net.isIP(h)){if(privateIp(h))throw Error('private target blocked');return u;}
  const a=await dns.lookup(h,{all:true,verbatim:true});
  if(!a.length||a.some(x=>privateIp(x.address)))throw Error('private target blocked');
  return u;
}
function upHeaders(u,req){
  const h=new Headers({'User-Agent':UA,'Accept':req.headers.accept||'*/*','Accept-Language':req.headers['accept-language']||'ja-JP,ja;q=.9,en;q=.7','Cache-Control':'no-cache','Pragma':'no-cache'});
  if(req.headers.range)h.set('Range',req.headers.range);
  const host=u.hostname.toLowerCase(),full=u.href.toLowerCase();
  if(host.endsWith('streaks.jp')){
    if(full.includes('boatrace')||full.includes('cp-boatrace-prod')){
      h.set('Origin','https://front.player.boatrace-cdn.jp');
      h.set('Referer','https://front.player.boatrace-cdn.jp/');
    }else if(full.includes('/gch/')||full.includes('live-gch')||full.includes('greenchannel')){
      h.set('Origin','https://www.greenchannel.jp');
      h.set('Referer','https://www.greenchannel.jp/');
    }else{
      h.set('Origin','https://tver.jp');
      h.set('Referer','https://tver.jp/');
    }
  }else if(host.endsWith('live-video.net') || (host.endsWith('.amazonaws.com') && host.includes('video-weaver.')) || host==='kick.com' || host.endsWith('.kick.com')){
    h.set('Origin','https://kick.com');
    h.set('Referer','https://kick.com/');
  }else if(host.endsWith('googlevideo.com')){
    h.set('Origin','https://www.youtube.com');h.set('Referer','https://www.youtube.com/');
  }else if(host.endsWith('charandom.blog')){
    h.set('Referer','https://haru.charandom.blog/');
  }
  return h;
}
async function getUp(raw,req){
  let u=await checked(raw);
  for(let i=0;i<6;i++){
    const ac=new AbortController(),t=setTimeout(()=>ac.abort(),20000);let r;
    try{r=await fetch(u,{method:req.method==='HEAD'?'HEAD':'GET',headers:upHeaders(u,req),redirect:'manual',signal:ac.signal});}
    finally{clearTimeout(t);}
    if(r.status>=300&&r.status<400&&r.headers.get('location')){u=await checked(new URL(r.headers.get('location'),u).href);continue;}
    return r;
  }
  throw Error('too many redirects');
}
function pxy(abs){return '/proxy?url='+encodeURIComponent(abs);}
function fixJra(text,url){
  const l=url.toLowerCase();
  if(!l.includes('west_master')&&!l.includes('hokaido_master'))return text;
  const v=l.includes('west_master')?'manifest_6.m3u8':'manifest_5.m3u8';
  return text.split(/\r?\n/).map(x=>x.startsWith('#EXT-X-MEDIA')&&x.includes('TYPE=AUDIO')?x.replace(/manifest_\d+\.m3u8/g,'manifest_8.m3u8'):(x.trim()&&!x.startsWith('#')&&x.includes('.m3u8')?x.replace(/manifest_\d+\.m3u8/g,v):x)).join('\n');
}
function rewrite(text,base){
  text=fixJra(text,base);
  return text.split(/\r?\n/).map(line=>{
    if(!line)return line;
    if(line.startsWith('#'))return line.replace(/URI=\"([^\"]+)\"/g,(_,r)=>'URI=\"'+px(new URL(r,base).href)+'\"').replace(/URI='([^']+)'/g,(_,r)=>"URI='"+px(new URL(r,base).href)+"'");
    try{return pxy(new URL(line.trim(),base).href);}catch{return line;}
  }).join('\n');
}
function cors(res){res.setHeader('Access-Control-Allow-Origin','*');res.setHeader('Access-Control-Allow-Methods','GET,HEAD,OPTIONS');res.setHeader('Access-Control-Allow-Headers','Range,Content-Type,Accept');res.setHeader('Access-Control-Expose-Headers','Content-Length,Content-Range,Accept-Ranges,Content-Type');res.setHeader('Cross-Origin-Resource-Policy','cross-origin');res.setHeader('X-Content-Type-Options','nosniff');}
function copy(r,res,n){const v=r.headers.get(n);if(v)res.setHeader(n,v);}

const server=http.createServer(async(req,res)=>{
  cors(res);
  const parsed=new URL(req.url,'http://'+(req.headers.host||'localhost'));
  if(req.method==='OPTIONS'){res.statusCode=204;return res.end();}
  if(parsed.pathname==='/'||parsed.pathname==='/health'){
    res.setHeader('Content-Type','application/json; charset=utf-8');
    res.setHeader('Cache-Control','no-store');
    return res.end(JSON.stringify({ok:true,service:'iptv-9x-browser-proxy',version:'3',gch:true,kick:true}));
  }
  if(parsed.pathname==='/youtube'){
    const id=parsed.searchParams.get('id')||'';
    if(!/^[A-Za-z0-9_-]{11}$/.test(id)){res.statusCode=400;return res.end('bad id');}
    const origin='https://'+req.headers.host;
    const src='https://www.youtube.com/embed/'+encodeURIComponent(id)+'?autoplay=1&mute=1&playsinline=1&rel=0&enablejsapi=1&origin='+encodeURIComponent(origin);
    res.setHeader('Content-Type','text/html; charset=utf-8');
    res.setHeader('Referrer-Policy','strict-origin-when-cross-origin');
    res.setHeader('Cache-Control','no-store');
    return res.end(`<!doctype html><html><head><meta name="referrer" content="strict-origin-when-cross-origin"><style>html,body,iframe{margin:0;width:100%;height:100%;border:0;background:#000;overflow:hidden}</style></head><body><iframe src="${src}" referrerpolicy="strict-origin-when-cross-origin" allow="autoplay; encrypted-media; picture-in-picture" allowfullscreen></iframe></body></html>`);
  }
  if(parsed.pathname!=='/proxy'){res.statusCode=404;return res.end('not found');}
  if(!['GET','HEAD'].includes(req.method)){res.statusCode=405;return res.end('method not allowed');}
  const target=parsed.searchParams.get('url');
  if(!target){res.statusCode=400;return res.end('missing url');}
  try{
    const r=await getUp(target,req),final=r.url||target,ct=(r.headers.get('content-type')||'').toLowerCase();
    res.statusCode=r.status;
    for(const n of ['content-type','content-range','accept-ranges','etag','last-modified'])copy(r,res,n);
    if(req.method==='HEAD'){copy(r,res,'content-length');return res.end();}
    let path='';try{path=new URL(final).pathname.toLowerCase();}catch{}
    if(ct.includes('mpegurl')||path.endsWith('.m3u8')){
      const b=await r.text();
      res.setHeader('Content-Type','application/vnd.apple.mpegurl; charset=utf-8');
      res.setHeader('Cache-Control','no-store');
      res.removeHeader('content-length');
      return res.end(rewrite(b,final));
    }
    copy(r,res,'content-length');
    res.setHeader('Cache-Control',r.headers.get('cache-control')||'public,max-age=5');
    if(!r.body)return res.end();
    Readable.fromWeb(r.body).on('error',e=>res.destroy(e)).pipe(res);
  }catch(e){
    res.statusCode=502;
    res.setHeader('Content-Type','text/plain; charset=utf-8');
    res.setHeader('Cache-Control','no-store');
    res.end('proxy error: '+(e.message||e));
  }
});
server.listen(PORT,'0.0.0.0',()=>console.log('IPTV browser proxy v3 listening on',PORT));
