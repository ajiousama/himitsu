#!/usr/bin/env python3
import base64, concurrent.futures, hashlib, json, os, socket, threading, urllib.parse, urllib.request, urllib.error
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urljoin
from radiko_epg import build_xmltv

AUTH_KEY = "bcd151073c03b352e1ef2fd66c32209da9ca0afa"
BASE_HEADERS = {"X-Radiko-App":"pc_html5","X-Radiko-App-Version":"0.0.1","X-Radiko-Device":"pc","X-Radiko-User":"dummy_user","User-Agent":"Mozilla/5.0"}
HOST=os.environ.get("RADIKO_PROXY_HOST","127.0.0.1")
PORT=int(os.environ.get("RADIKO_PROXY_PORT","9395"))
FREEWIFI_REMOTE=os.environ.get("RADIKO_FREEWIFI_URL","https://raw.githubusercontent.com/ajiousama/himitsu/main/freewifi")
API_BASE="https://api.radiko.jp"
WEB_BASE="https://radiko.jp"
_state_lock=threading.Lock(); _state={"session":None,"token":None,"area":None,"stations":None,"epg":None,"mode":None,"premium_failed":False}

def open_url(url,headers=None,data=None,timeout=15):
 return urllib.request.urlopen(urllib.request.Request(url,headers=headers or {},data=data),timeout=timeout)

def premium_login():
 mail=os.environ.get("RADIKO_MAIL","").strip(); password=os.environ.get("RADIKO_PASSWORD","").strip()
 if not mail or not password: raise RuntimeError("Premium credentials are not set")
 data=urllib.parse.urlencode({"mail":mail,"pass":password}).encode()
 with open_url(WEB_BASE+"/v4/api/member/login",data=data,timeout=30) as r: obj=json.loads(r.read().decode())
 session=str(obj.get("radiko_session") or "").strip()
 if not session: raise RuntimeError("Radiko account login failed")
 return session,str(obj.get("areafree") or "0")=="1"

def _auth_once(base,session=None):
 with open_url(base+"/v2/api/auth1",headers=BASE_HEADERS,timeout=30) as r:
  token=r.headers.get("X-Radiko-AuthToken")
  off=r.headers.get("X-Radiko-KeyOffset")
  length=r.headers.get("X-Radiko-KeyLength")
 if not token or off is None or length is None: raise RuntimeError("auth1 headers missing")
 off=int(off); length=int(length)
 partial=base64.b64encode(AUTH_KEY[off:off+length].encode()).decode()
 h=dict(BASE_HEADERS); h.update({"X-Radiko-AuthToken":token,"X-Radiko-PartialKey":partial})
 url=base+"/v2/api/auth2"
 if session:url+="?radiko_session="+urllib.parse.quote(session)
 with open_url(url,headers=h,timeout=30) as r: body=r.read().decode().strip()
 if not body or body=="OUT": raise RuntimeError("auth2 returned OUT")
 return token,body.split(",")[0]

def auth(session=None):
 errors=[]
 # radiko.jp is the PC web-player endpoint and is known to work on Windows.
 # api.radiko.jp is retained as a fallback because availability differs by network.
 for base in (WEB_BASE,API_BASE):
  try:return _auth_once(base,session)
  except Exception as e:errors.append(f"{base}:{type(e).__name__}:{getattr(e,'code','')}:{e}")
 raise RuntimeError("radiko auth failed | "+" | ".join(errors))

def ensure_auth(force=False):
 with _state_lock:
  if not force and _state["token"]: return _state["session"],_state["token"],_state["area"],_state["mode"]
  premium_failed=_state["premium_failed"]
 session=None; token=None; area=None; mode="free"
 mail=os.environ.get("RADIKO_MAIL","").strip(); password=os.environ.get("RADIKO_PASSWORD","").strip()
 if mail and password and not premium_failed:
  try:
   session,areafree=premium_login(); token,area=auth(session); mode="premium" if areafree else "free-account"
  except Exception:
   with _state_lock:_state["premium_failed"]=True
   session=None; token=None; area=None; mode="free"
 if token is None:
  token,area=auth(None)
 with _state_lock:_state.update(session=session,token=token,area=area,mode=mode)
 return session,token,area,mode

def region_for_prefecture(n):
 if n==1:return "北海道"
 if n<=7:return "東北"
 if n<=14:return "関東"
 if n<=20:return "甲信越"
 if n<=24:return "東海"
 if n<=30:return "近畿"
 if n<=35:return "中国"
 if n<=39:return "四国"
 return "九州沖縄"

def _fetch_area_stations(n):
 area=f"JP{n}"; region=region_for_prefecture(n)
 try:
  with open_url(f"{WEB_BASE}/v3/station/list/{area}.xml",headers={"User-Agent":"Mozilla/5.0"},timeout=8) as r: root=ET.fromstring(r.read())
 except Exception:return []
 found=[]
 for st in root.findall("station"):
  sid=(st.findtext("id") or "").strip(); name=(st.findtext("name") or sid).strip(); logo=""; candidates=[]
  for node in st.findall("logo"):
   if node.text and node.text.strip():
    try: score=int(node.get("width") or 0)*int(node.get("height") or 0)
    except ValueError: score=0
    candidates.append((score,node.text.strip()))
  if candidates: logo=max(candidates,key=lambda x:x[0])[1]
  if not logo: logo=next(((st.findtext(tag) or "").strip() for tag in ("logo_large","logo_medium","logo_small","logo_xsmall") if (st.findtext(tag) or "").strip()),"")
  if sid: found.append((sid,{"name":name,"logo":logo,"region":region,"pref":n}))
 return found

def discover_stations(force=False):
 with _state_lock:
  if _state["stations"] is not None and not force:return _state["stations"]
 stations={}; results={}
 with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
  fs={ex.submit(_fetch_area_stations,n):n for n in range(1,48)}
  for f in concurrent.futures.as_completed(fs):results[fs[f]]=f.result()
 for n in range(1,48):
  for sid,meta in results.get(n,[]): stations.setdefault(sid,meta)
 with _state_lock:_state["stations"]=stations
 return stations

def get_epg(force=False):
 with _state_lock:
  if _state["epg"] is not None and not force:return _state["epg"]
 data=build_xmltv(3)
 with _state_lock:_state["epg"]=data
 return data

def playlist_create_urls(station,areafree):
 out=[]
 try:
  for base in (API_BASE,WEB_BASE):
   try:
    with open_url(f"{base}/v3/station/stream/pc_html5/{station}.xml",headers={"User-Agent":"Mozilla/5.0"},timeout=10) as r:root=ET.fromstring(r.read())
    want="1" if areafree else "0"
    for node in root.findall("url"):
     if node.get("areafree")==want and node.get("timefree","0")=="0":
      p=node.find("playlist_create_url")
      if p is not None and p.text and p.text.strip() not in out:out.append(p.text.strip())
    if out:break
   except Exception:continue
 except Exception:pass
 current="https://alliance-stream-radiko.smartstream.ne.jp/so/playlist.m3u8"
 if current not in out:out.insert(0,current)
 return out

def auth_headers(token,session=None):
 h={"X-Radiko-AuthToken":token,"User-Agent":"Mozilla/5.0"}
 if session:h["Cookie"]="radiko_session="+session
 return h

def get_live_master(station,refresh=False):
 session,token,_,mode=ensure_auth(force=refresh); errors=[]; areafree=(mode=="premium")
 types=("c","b") if areafree else ("b",)
 for base in playlist_create_urls(station,areafree):
  for typ in types:
   q=urllib.parse.urlencode({"station_id":station,"l":195,"lsid":"alliance","type":typ,"noad":1}); url=base+("&" if "?" in base else "?")+q
   try:
    with open_url(url,headers=auth_headers(token,session),timeout=15) as r:body=r.read().decode("utf-8","replace")
    if "#EXTM3U" in body:return url,body
   except Exception as e:errors.append(f"{type(e).__name__}:{getattr(e,'code','')}")
 if not refresh:return get_live_master(station,refresh=True)
 raise RuntimeError(f"no playable URL for {station} ({mode}): {','.join(errors[-5:])}")

def get_live_auto():
 _,_,area,_=ensure_auth(); stations=discover_stations()
 try:pref=int(area[2:]) if area.startswith("JP") else 0
 except Exception:pref=0
 candidates=[sid for sid,meta in stations.items() if meta.get("pref")==pref]
 if not candidates:candidates=list(stations)[:12]
 errors=[]
 for sid in candidates[:12]:
  try:
   source,text=get_live_master(sid); return sid,source,text
  except Exception as e:errors.append(f"{sid}:{e}")
 raise RuntimeError("no local live station: "+" | ".join(errors[-3:]))

def rewrite_m3u(text,source_url,base_proxy):
 out=[]
 for line in text.splitlines():
  s=line.strip()
  if s and not s.startswith("#"):line=base_proxy+"/proxy?u="+urllib.parse.quote(urljoin(source_url,s),safe="")
  out.append(line)
 return "\n".join(out)+"\n"

def get_freewifi_for_client(base_proxy):
 with open_url(FREEWIFI_REMOTE,headers={"User-Agent":"Mozilla/5.0"},timeout=20) as r:text=r.read().decode("utf-8-sig","replace")
 text=text.replace("http://127.0.0.1:9395/",base_proxy+"/")
 return text.encode("utf-8")

def fetch_proxied(url,refresh=False):
 session,token,_,_=ensure_auth(force=refresh)
 try:return open_url(url,headers=auth_headers(token,session),timeout=20)
 except urllib.error.HTTPError as e:
  if e.code in (401,403) and not refresh:return fetch_proxied(url,refresh=True)
  raise

def local_ip():
 try:
  s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.connect(("8.8.8.8",80)); ip=s.getsockname()[0]; s.close(); return ip
 except Exception:return "PC-LAN-IP"

class Handler(BaseHTTPRequestHandler):
 server_version="RadikoProxy/1.9"
 def log_message(self,fmt,*args):print("[radiko] "+fmt%args,flush=True)
 def send_bytes(self,status,data,content_type):
  self.send_response(status);self.send_header("Content-Type",content_type);self.send_header("Content-Length",str(len(data)));self.send_header("Cache-Control","no-store");self.send_header("Access-Control-Allow-Origin","*");self.end_headers();self.wfile.write(data)
 def do_GET(self):
  p=urllib.parse.urlsplit(self.path);base_proxy=f"http://{self.headers.get('Host',f'{HOST}:{PORT}')}"
  try:
   if p.path=="/health":self.send_bytes(200,b"OK\n","text/plain; charset=utf-8");return
   if p.path=="/ready":
    _,_,area,mode=ensure_auth();stations=discover_stations();self.send_bytes(200,f"OK {area} mode={mode} stations={len(stations)}\n".encode(),"text/plain; charset=utf-8");return
   if p.path=="/epg.xml":self.send_bytes(200,get_epg(),"application/xml; charset=utf-8");return
   if p.path=="/freewifi.m3u":self.send_bytes(200,get_freewifi_for_client(base_proxy),"audio/x-mpegurl; charset=utf-8");return
   if p.path in ("/","/playlist.m3u"):
    stations=discover_stations();lines=[f'#EXTM3U url-tvg="{base_proxy}/epg.xml"'];order={name:i for i,name in enumerate(("北海道","東北","関東","甲信越","東海","近畿","四国","中国","九州沖縄"))}
    items=sorted(stations.items(),key=lambda kv:(order.get(kv[1].get("region",""),99),kv[1].get("pref",99),kv[1].get("name","")))
    for sid,meta in items:lines.append(f'#EXTINF:-1 tvg-id="radiko.{sid}" tvg-logo="{meta.get("logo","")}" group-title="{meta.get("region","その他")}",{meta["name"]}');lines.append(f"{base_proxy}/live/{urllib.parse.quote(sid)}")
    self.send_bytes(200,("\n".join(lines)+"\n").encode("utf-8"),"audio/x-mpegurl; charset=utf-8");return
   if p.path=="/live-auto":
    sid,source,text=get_live_auto();data=(f"# auto-station={sid}\n"+rewrite_m3u(text,source,base_proxy)).encode("utf-8");self.send_bytes(200,data,"application/vnd.apple.mpegurl");return
   if p.path.startswith("/live/"):
    sid=urllib.parse.unquote(p.path.split("/",2)[2]);source,text=get_live_master(sid);self.send_bytes(200,rewrite_m3u(text,source,base_proxy).encode("utf-8"),"application/vnd.apple.mpegurl");return
   if p.path=="/proxy":
    target=(urllib.parse.parse_qs(p.query).get("u") or [""])[0]
    if not target.startswith(("http://","https://")):self.send_error(400,"bad proxy URL");return
    with fetch_proxied(target) as r:
     data=r.read();ctype=r.headers.get_content_type();is_m3u="mpegurl" in ctype or target.lower().split("?",1)[0].endswith((".m3u8",".m3u")) or data.startswith(b"#EXTM3U")
     if is_m3u:data=rewrite_m3u(data.decode("utf-8","replace"),target,base_proxy).encode("utf-8");ctype="application/vnd.apple.mpegurl"
     self.send_bytes(200,data,ctype or "application/octet-stream")
    return
   self.send_error(404)
  except Exception as e:
   print(f"[radiko] ERROR {p.path}: {type(e).__name__}: {e}",flush=True)
   try:self.send_error(502,str(e))
   except Exception:pass

def main():
 ip=local_ip()
 print(f"radiko proxy listening: http://{HOST}:{PORT}",flush=True)
 print(f"PC playlist: http://127.0.0.1:{PORT}/playlist.m3u",flush=True)
 print(f"LAN radiko playlist: http://{ip}:{PORT}/playlist.m3u",flush=True)
 print(f"LAN FreeWiFi playlist: http://{ip}:{PORT}/freewifi.m3u",flush=True)
 print(f"XMLTV EPG: http://{ip}:{PORT}/epg.xml",flush=True)
 ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()

if __name__=="__main__":main()
