#!/usr/bin/env python3
import base64,concurrent.futures,json,os,re,shutil,socket,subprocess,threading,time,urllib.error,urllib.parse,urllib.request
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urljoin
from radiko_epg import build_xmltv

HOST=os.environ.get("RADIKO_PROXY_HOST","127.0.0.1");PORT=int(os.environ.get("RADIKO_PROXY_PORT","9395"))
FREEWIFI_REMOTE=os.environ.get("RADIKO_FREEWIFI_URL","https://raw.githubusercontent.com/ajiousama/himitsu/main/freewifi")
API_BASE="https://api.radiko.jp";WEB_BASE="https://radiko.jp"
AUTHKEY=b"bcd151073c03b352e1ef2fd66c32209da9ca0afa"
BASE_HEADERS={"X-Radiko-App":"pc_html5","X-Radiko-App-Version":"0.0.1","X-Radiko-Device":"pc","X-Radiko-User":"dummy_user"}
_lock=threading.RLock();S={"session":None,"premium":None,"premium_error":None,"tokens":{},"local":None,"stations":None,"epg":None}

def open_url(url,headers=None,data=None,timeout=15):
 h={"User-Agent":"curl/8.0","Accept":"*/*"};h.update(headers or {})
 return urllib.request.urlopen(urllib.request.Request(url,headers=h,data=data),timeout=timeout)

def _curl_login(mail,pw):
 exe=shutil.which("curl.exe") or shutil.which("curl")
 if not exe:raise RuntimeError("curl was not found")
 body=urllib.parse.urlencode({"mail":mail,"pass":pw}).encode()
 p=subprocess.run([exe,"-fsS","--request","POST","--header","Content-Type: application/x-www-form-urlencoded","--data-binary","@-",WEB_BASE+"/v4/api/member/login"],input=body,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=35)
 if p.returncode:raise RuntimeError(p.stderr.decode("utf-8","replace").strip() or f"curl exit {p.returncode}")
 return json.loads(p.stdout.decode("utf-8","replace"))

def premium(force=False):
 mail=os.environ.get("RADIKO_MAIL","").strip();pw=os.environ.get("RADIKO_PASSWORD","").strip()
 if not mail or not pw:return None,False
 with _lock:
  if S["session"] and S["premium"] is True and not force:return S["session"],True
  if S["premium_error"] and not force:raise RuntimeError(S["premium_error"])
 try:
  try:o=_curl_login(mail,pw)
  except Exception:
   d=urllib.parse.urlencode({"mail":mail,"pass":pw}).encode()
   with open_url(WEB_BASE+"/v4/api/member/login",{"Content-Type":"application/x-www-form-urlencoded"},d,30) as r:o=json.loads(r.read().decode())
  sess=str(o.get("radiko_session") or "").strip()
  paid=str(o.get("areafree") or "") == "1" or str(o.get("paid_member") or "") not in ("","0","false","False")
  status=str(o.get("status") or "200")
  if status not in ("200","0","true","True") or not sess:raise RuntimeError("Radiko Premium login was rejected")
  if not paid:raise RuntimeError("Radiko account is not enabled for area-free")
 except Exception as e:
  msg=f"Premium login failed: {type(e).__name__}: {e}"
  with _lock:S["premium_error"]=msg;S["session"]=None;S["premium"]=False
  raise RuntimeError(msg) from e
 with _lock:S["session"]=sess;S["premium"]=True;S["premium_error"]=None
 print("[radiko] Premium area-free login OK",flush=True);return sess,True

def local_area(force=False):
 with _lock:
  if S["local"] and not force:return S["local"]
 with open_url(WEB_BASE+"/area",timeout=20) as r:t=r.read().decode("utf-8","replace")
 m=re.search(r'class=["\'](JP\d{1,2})["\']',t) or re.search(r'\b(JP\d{1,2})\b',t)
 if not m:raise RuntimeError("Radiko local area could not be detected")
 a="JP"+str(int(m.group(1)[2:]));
 with _lock:S["local"]=a
 return a

def auth_area(area,force=False):
 local=local_area();has=bool(os.environ.get("RADIKO_MAIL","").strip() and os.environ.get("RADIKO_PASSWORD","").strip())
 sess,af=premium(force=force) if has else (None,False)
 if not af and area!=local:raise RuntimeError(f"{area} is outside local Radiko area {local}; Premium is required")
 with _lock:
  c=S["tokens"].get(area)
  if c and not force and c["premium"]==af and time.time()-c["time"]<3900:return c["token"],af
 with open_url(API_BASE+"/v2/api/auth1",BASE_HEADERS,timeout=30) as r:
  token=r.headers.get("X-Radiko-AuthToken");off=r.headers.get("X-Radiko-KeyOffset");ln=r.headers.get("X-Radiko-KeyLength")
 if not token or off is None or ln is None:raise RuntimeError("Radiko auth1 headers are incomplete")
 off=int(off);ln=int(ln);part=AUTHKEY[off:off+ln]
 if len(part)!=ln:raise RuntimeError(f"Radiko partial-key range invalid offset={off} length={ln}")
 h={"X-Radiko-Device":"pc","X-Radiko-User":"dummy_user","X-Radiko-AuthToken":token,"X-Radiko-PartialKey":base64.b64encode(part).decode()}
 u=API_BASE+"/v2/api/auth2"
 if sess:u+="?radiko_session="+urllib.parse.quote(sess,safe="")
 with open_url(u,h,timeout=30) as r:body=r.read().decode("utf-8","replace").strip()
 if not body or body=="OUT":raise RuntimeError("Radiko auth2 returned OUT")
 with _lock:S["tokens"][area]={"token":token,"premium":af,"time":time.time()}
 print(f"[radiko] auth OK area={area} mode={'premium' if af else 'free'}",flush=True);return token,af

def region(n):
 if n==1:return"北海道"
 if n<=7:return"東北"
 if n<=14:return"関東"
 if n<=20:return"甲信越"
 if n<=24:return"東海"
 if n<=30:return"近畿"
 if n<=35:return"中国"
 if n<=39:return"四国"
 return"九州沖縄"
def _fetch_st(n):
 area=f"JP{n}"
 try:
  with open_url(f"{WEB_BASE}/v3/station/list/{area}.xml",timeout=10) as r:root=ET.fromstring(r.read())
 except:return[]
 out=[]
 for st in root.findall("station"):
  sid=(st.findtext("id") or "").strip();name=(st.findtext("name") or sid).strip();logos=[]
  for x in st.findall("logo"):
   if x.text and x.text.strip():
    try:score=int(x.get("width") or 0)*int(x.get("height") or 0)
    except:score=0
    logos.append((score,x.text.strip()))
  logo=max(logos,key=lambda x:x[0])[1] if logos else ""
  if sid:out.append((sid,{"name":name,"logo":logo,"region":region(n),"pref":n,"area":area}))
 return out
def stations(force=False):
 with _lock:
  if S["stations"] is not None and not force:return S["stations"]
 R={};res={}
 with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
  fs={ex.submit(_fetch_st,n):n for n in range(1,48)}
  for f in concurrent.futures.as_completed(fs):res[fs[f]]=f.result()
 for n in range(1,48):
  for sid,m in res.get(n,[]):
   if sid not in R:m["areas"]=[m["area"]];R[sid]=m
   elif m["area"] not in R[sid]["areas"]:R[sid]["areas"].append(m["area"])
 with _lock:S["stations"]=R
 return R
def epg(force=False):
 with _lock:
  if S["epg"] is not None and not force:return S["epg"]
 d=build_xmltv(3)
 with _lock:S["epg"]=d
 return d
def station_area(sid,af):
 m=stations().get(sid)
 if not m:raise RuntimeError(f"unknown Radiko station: {sid}")
 local=local_area();areas=m.get("areas") or [m["area"]]
 if local in areas:return local
 if af:return areas[0]
 raise RuntimeError(f"{sid} is not available in local area {local}; Premium is required")
def stream_urls(sid,af):
 out=[]
 for b in (API_BASE,WEB_BASE):
  try:
   with open_url(f"{b}/v3/station/stream/pc_html5/{sid}.xml",timeout=15) as r:root=ET.fromstring(r.read())
  except:continue
  want="1" if af else "0"
  for node in root.findall("url"):
   if node.get("areafree")==want and node.get("timefree","0")=="0":
    p=node.find("playlist_create_url")
    if p is not None and p.text and p.text.strip() not in out:out.append(p.text.strip())
  if out:break
 fb="https://alliance-stream-radiko.smartstream.ne.jp/so/playlist.m3u8"
 if fb not in out:out.insert(0,fb)
 return out
def mh(token,area):return{"X-Radiko-AuthToken":token,"X-Radiko-AreaId":area}
def live(sid,refresh=False):
 has=bool(os.environ.get("RADIKO_MAIL","").strip() and os.environ.get("RADIKO_PASSWORD","").strip());af=premium(force=refresh)[1] if has else False;area=station_area(sid,af);token,af=auth_area(area,force=refresh);errs=[]
 for b in stream_urls(sid,af):
  for typ in (("c","b") if af else ("b",)):
   q=urllib.parse.urlencode({"station_id":sid,"l":195,"lsid":"alliance","type":typ,"noad":1});u=b+("&" if "?" in b else "?")+q
   try:
    with open_url(u,mh(token,area),timeout=20) as r:t=r.read().decode("utf-8","replace")
    if "#EXTM3U" in t:return area,u,t
   except Exception as e:errs.append(f"{typ}:{type(e).__name__}:{getattr(e,'code','')}")
 if not refresh:return live(sid,True)
 raise RuntimeError(f"no playable URL for {sid} area={area} mode={'premium' if af else 'free'}: {','.join(errs[-8:])}")
def live_auto():
 local=local_area();errs=[]
 for sid,m in stations().items():
  if local not in m.get("areas",[]):continue
  try:a,u,t=live(sid);return sid,a,u,t
  except Exception as e:errs.append(f"{sid}:{e}")
  if len(errs)>=20:break
 raise RuntimeError("no local live station: "+" | ".join(errs[-3:]))
def rewrite_m3u(text,src,base,area=None):
 out=[]
 for line in text.splitlines():
  s=line.strip()
  if s and not s.startswith("#"):
   line=base+"/proxy?u="+urllib.parse.quote(urljoin(src,s),safe="")
   if area:line+="&a="+urllib.parse.quote(area,safe="")
  out.append(line)
 return"\n".join(out)+"\n"
def freewifi(base):
 with open_url(FREEWIFI_REMOTE,timeout=20) as r:t=r.read().decode("utf-8-sig","replace")
 return t.replace("http://127.0.0.1:9395/",base+"/").encode()
def proxied(url,area,refresh=False):
 if not area:raise RuntimeError("missing Radiko area for proxied media")
 token,_=auth_area(area,force=refresh)
 try:return open_url(url,mh(token,area),timeout=25)
 except urllib.error.HTTPError as e:
  if e.code in(401,403) and not refresh:return proxied(url,area,True)
  raise
def local_ip():
 try:
  s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.connect(("8.8.8.8",80));ip=s.getsockname()[0];s.close();return ip
 except:return"PC-LAN-IP"
class Handler(BaseHTTPRequestHandler):
 server_version="RadikoProxy/3.1"
 def log_message(self,fmt,*args):print("[radiko] "+fmt%args,flush=True)
 def sendb(self,status,data,ct):
  self.send_response(status);self.send_header("Content-Type",ct);self.send_header("Content-Length",str(len(data)));self.send_header("Cache-Control","no-store");self.send_header("Access-Control-Allow-Origin","*");self.end_headers();self.wfile.write(data)
 def do_GET(self):
  p=urllib.parse.urlsplit(self.path);base=f"http://{self.headers.get('Host',f'{HOST}:{PORT}')}"
  try:
   if p.path=="/health":self.sendb(200,b"OK\n","text/plain");return
   if p.path=="/ready":
    ss=stations();local=local_area();has=bool(os.environ.get("RADIKO_MAIL","").strip() and os.environ.get("RADIKO_PASSWORD","").strip())
    if has:premium(True);auth_area("JP13" if local!="JP13" else "JP27",True);mode="premium"
    else:auth_area(local,True);mode="free"
    self.sendb(200,f"OK {local} mode={mode} stations={len(ss)}\n".encode(),"text/plain");return
   if p.path=="/epg.xml":self.sendb(200,epg(),"application/xml");return
   if p.path=="/freewifi.m3u":self.sendb(200,freewifi(base),"audio/x-mpegurl");return
   if p.path in("/","/playlist.m3u"):
    ss=stations();order={x:i for i,x in enumerate(("北海道","東北","関東","甲信越","東海","近畿","四国","中国","九州沖縄"))};lines=[f'#EXTM3U url-tvg="{base}/epg.xml"']
    for sid,m in sorted(ss.items(),key=lambda x:(order.get(x[1]["region"],99),x[1]["pref"],x[1]["name"])):lines += [f'#EXTINF:-1 tvg-id="radiko.{sid}" tvg-logo="{m["logo"]}" group-title="{m["region"]}",{m["name"]}',f"{base}/live/{urllib.parse.quote(sid)}"]
    self.sendb(200,("\n".join(lines)+"\n").encode(),"audio/x-mpegurl");return
   if p.path=="/live-auto":
    sid,a,u,t=live_auto();self.sendb(200,(f"# auto-station={sid} area={a}\n"+rewrite_m3u(t,u,base,a)).encode(),"application/vnd.apple.mpegurl");return
   if p.path.startswith("/live/"):
    sid=urllib.parse.unquote(p.path.split("/",2)[2]);a,u,t=live(sid);self.sendb(200,rewrite_m3u(t,u,base,a).encode(),"application/vnd.apple.mpegurl");return
   if p.path=="/proxy":
    q=urllib.parse.parse_qs(p.query);u=(q.get("u") or [""])[0];a=(q.get("a") or [""])[0]
    if not u.startswith(("http://","https://")):self.send_error(400,"bad proxy URL");return
    with proxied(u,a) as r:
     d=r.read();ct=r.headers.get_content_type();ism="mpegurl" in ct or u.lower().split("?",1)[0].endswith((".m3u8",".m3u")) or d.startswith(b"#EXTM3U")
     if ism:d=rewrite_m3u(d.decode("utf-8","replace"),u,base,a).encode();ct="application/vnd.apple.mpegurl"
     self.sendb(200,d,ct or "application/octet-stream")
    return
   self.send_error(404)
  except Exception as e:
   print(f"[radiko] ERROR {p.path}: {type(e).__name__}: {e}",flush=True)
   try:self.send_error(502,str(e))
   except:pass
def main():
 ip=local_ip();print(f"radiko proxy listening: http://{HOST}:{PORT}",flush=True);print(f"PC playlist: http://127.0.0.1:{PORT}/playlist.m3u",flush=True);print(f"LAN radiko playlist: http://{ip}:{PORT}/playlist.m3u",flush=True);print(f"LAN FreeWiFi playlist: http://{ip}:{PORT}/freewifi.m3u",flush=True);print(f"XMLTV EPG: http://{ip}:{PORT}/epg.xml",flush=True);ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
if __name__=="__main__":main()
