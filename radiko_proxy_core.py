#!/usr/bin/env python3
import base64,concurrent.futures,json,os,random,re,secrets,socket,threading,time,urllib.error,urllib.parse,urllib.request
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urljoin
from radiko_epg import build_xmltv

HOST=os.environ.get('RADIKO_PROXY_HOST','127.0.0.1')
PORT=int(os.environ.get('RADIKO_PROXY_PORT','9395'))
FREEWIFI_REMOTE=os.environ.get('RADIKO_FREEWIFI_URL','https://raw.githubusercontent.com/ajiousama/himitsu/main/freewifi')
API='https://api.radiko.jp'; WEB='https://radiko.jp'
STATIC_URL='https://raw.githubusercontent.com/jackyzy823/rajiko/master/modules/static.js'
COORD=[(43.064615,141.346807),(40.824308,140.739998),(39.703619,141.152684),(38.268837,140.8721),(39.718614,140.102364),(38.240436,140.363633),(37.750299,140.467551),(36.341811,140.446793),(36.565725,139.883565),(36.390668,139.060406),(35.856999,139.648849),(35.605057,140.123306),(35.689488,139.691706),(35.447507,139.642345),(37.902552,139.023095),(36.695291,137.211338),(36.594682,136.625573),(36.065178,136.221527),(35.664158,138.568449),(36.651299,138.180956),(35.391227,136.722291),(34.97712,138.383084),(35.180188,136.906565),(34.730283,136.508588),(35.004531,135.86859),(35.021247,135.755597),(34.686297,135.519661),(34.691269,135.183071),(34.685334,135.832742),(34.225987,135.167509),(35.503891,134.497503),(35.472295,133.0505),(34.661751,133.934406),(34.39656,132.459622),(34.185956,131.470649),(34.065718,134.55936),(34.340149,134.043444),(33.841624,132.765681),(33.559706,133.531079),(33.606576,130.418297),(33.249442,130.299794),(32.744839,129.873756),(32.789827,130.741667),(33.238172,131.612619),(31.911096,131.423893),(31.560146,130.557978),(26.2124,127.680932)]
LOCK=threading.RLock()
S={'identity':None,'session':None,'premium':None,'premium_error':None,'tokens':{},'local':None,'stations':None,'epg':None}

def http_error(stage,e):
 code=getattr(e,'code','')
 reason=getattr(e,'reason','')
 return RuntimeError(f'{stage} failed: HTTP {code} {reason}'.strip())

def open_url(url,headers=None,data=None,timeout=20,method=None):
 req=urllib.request.Request(url,headers=headers or {},data=data,method=method)
 return urllib.request.urlopen(req,timeout=timeout)

def version_key(v):
 try:return tuple(int(x) for x in v.split('.'))
 except:return (0,)

def identity(force=False):
 with LOCK:
  if S['identity'] and not force:return S['identity']
 try:
  with open_url(STATIC_URL,{'User-Agent':'Mozilla/5.0'},timeout=30) as r:text=r.read().decode('utf-8','replace')
 except Exception as e:raise http_error('Radiko app metadata download',e) from e
 keys=dict(re.findall(r'(?m)^\s*const\s+(aSmartPhone[A-Za-z0-9]+)_fullkey_b64\s*=\s*"([^"]+)"',text))
 m=re.search(r'export\s+const\s+APP_VERSION_MAP\s*=\s*\{(.*?)\}\s*;?',text,re.S)
 versions=re.findall(r'"([0-9.]+)"\s*:\s*"([^"]+)"',m.group(1) if m else '')
 versions=[x for x in versions if x[1] in keys]
 if not versions:raise RuntimeError('current Radiko app version/key was not found')
 ver,app=max(versions,key=lambda x:version_key(x[0]))
 try:key=base64.b64decode(keys[app],validate=True)
 except Exception as e:raise RuntimeError(f'current Radiko app key decode failed: {e}') from e
 um=re.search(r'export\s+const\s+USER_AGENT\s*=\s*"([^"]+)"',text)
 ua=um.group(1) if um else 'Mozilla/5.0 (Linux; Android 10; Pixel 4 XL) AppleWebKit/537.36 Chrome/80 Mobile Safari/537.36'
 info={'app':app,'ver':ver,'device':'35.GV0BP','user':secrets.token_hex(16),'ua':ua,'key':key}
 with LOCK:S['identity']=info
 print(f"[radiko] current auth identity app={app} version={ver} device={info['device']}",flush=True)
 return info

def app_headers():
 i=identity()
 return {'X-Radiko-App':i['app'],'X-Radiko-App-Version':i['ver'],'X-Radiko-Device':i['device'],'X-Radiko-User':i['user'],'User-Agent':i['ua']}

def premium_login(force=False):
 mail=os.environ.get('RADIKO_MAIL','').strip(); pw=os.environ.get('RADIKO_PASSWORD','').strip()
 if not mail or not pw:return None,False
 with LOCK:
  if S['session'] and S['premium'] is True and not force:return S['session'],True
  if S['premium_error'] and not force:raise RuntimeError(S['premium_error'])
 data=urllib.parse.urlencode({'mail':mail,'pass':pw}).encode()
 try:
  with open_url(WEB+'/v4/api/member/login',{'User-Agent':'Mozilla/5.0','Content-Type':'application/x-www-form-urlencoded'},data,30,'POST') as r:
   raw=r.read().decode('utf-8','replace'); obj=json.loads(raw)
 except urllib.error.HTTPError as e:
  msg=str(http_error('Premium login',e));
  with LOCK:S['premium_error']=msg
  raise RuntimeError(msg) from e
 except Exception as e:
  msg=f'Premium login failed: {type(e).__name__}: {e}'
  with LOCK:S['premium_error']=msg
  raise RuntimeError(msg) from e
 sess=str(obj.get('radiko_session') or '').strip()
 paid=str(obj.get('areafree') or '0')=='1'
 if not sess:
  msg='Premium login rejected: no radiko_session returned'
  with LOCK:S['premium_error']=msg
  raise RuntimeError(msg)
 if not paid:
  msg='Premium login succeeded but area-free is not enabled on this account'
  with LOCK:S['premium_error']=msg
  raise RuntimeError(msg)
 with LOCK:S['session']=sess;S['premium']=True;S['premium_error']=None;S['tokens'].clear()
 print('[radiko] Premium area-free login OK',flush=True)
 return sess,True

def local_area(force=False):
 with LOCK:
  if S['local'] and not force:return S['local']
 try:
  with open_url(WEB+'/area',{'User-Agent':'Mozilla/5.0'},timeout=20) as r:text=r.read().decode('utf-8','replace')
 except Exception as e:raise http_error('Local area detection',e) from e
 m=re.search(r'class=["\'](JP\d{1,2})["\']',text) or re.search(r'\b(JP\d{1,2})\b',text)
 if not m:raise RuntimeError('Local area detection failed: JP area was not found')
 area='JP'+str(int(m.group(1)[2:]))
 with LOCK:S['local']=area
 return area

def gps(area):
 n=int(area[2:]);lat,lon=COORD[n-1]
 lat+=random.random()/40*(1 if random.random()>.5 else -1);lon+=random.random()/40*(1 if random.random()>.5 else -1)
 return f'{lat:.6f},{lon:.6f},gps'

def auth_area(area,force=False):
 mail=os.environ.get('RADIKO_MAIL','').strip();pw=os.environ.get('RADIKO_PASSWORD','').strip()
 session,premium=premium_login(force=force) if mail and pw else (None,False)
 if not premium:
  local=local_area()
  if area!=local:raise RuntimeError(f'{area} is outside local Radiko area {local}; Premium is required')
 with LOCK:
  c=S['tokens'].get(area)
  if c and not force and c['premium']==premium and time.time()-c['time']<3900:return c['token'],premium
 i=identity(); h=app_headers()
 try:
  with open_url(API+'/v2/api/auth1',h,timeout=30) as r:
   token=r.headers.get('X-Radiko-AuthToken');off=r.headers.get('X-Radiko-KeyOffset');ln=r.headers.get('X-Radiko-KeyLength')
 except urllib.error.HTTPError as e:raise http_error('auth1',e) from e
 except Exception as e:raise RuntimeError(f'auth1 failed: {type(e).__name__}: {e}') from e
 if not token or off is None or ln is None:raise RuntimeError('auth1 failed: response headers are incomplete')
 off=int(off);ln=int(ln);part=i['key'][off:off+ln]
 if len(part)!=ln:raise RuntimeError(f'auth1 partial-key range invalid offset={off} length={ln} keylen={len(i["key"])}')
 h=app_headers();h.update({'X-Radiko-AuthToken':token,'X-Radiko-Partialkey':base64.b64encode(part).decode(),'X-Radiko-Location':gps(area)})
 if session:h['X-Radiko-Session']=session
 try:
  with open_url(API+'/v2/api/auth2',h,timeout=30) as r:body=r.read().decode('utf-8','replace').strip()
 except urllib.error.HTTPError as e:raise http_error(f'auth2 area={area}',e) from e
 except Exception as e:raise RuntimeError(f'auth2 area={area} failed: {type(e).__name__}: {e}') from e
 if body=='OUT':raise RuntimeError(f'auth2 area={area} returned OUT')
 with LOCK:S['tokens'][area]={'token':token,'premium':premium,'time':time.time()}
 print(f"[radiko] auth OK area={area} mode={'premium' if premium else 'free'}",flush=True)
 return token,premium

def region(n):
 if n==1:return '北海道'
 if n<=7:return '東北'
 if n<=14:return '関東'
 if n<=20:return '甲信越'
 if n<=24:return '東海'
 if n<=30:return '近畿'
 if n<=35:return '中国'
 if n<=39:return '四国'
 return '九州沖縄'

def fetch_station_area(n):
 area=f'JP{n}'
 try:
  with open_url(f'{WEB}/v3/station/list/{area}.xml',{'User-Agent':'Mozilla/5.0'},timeout=10) as r:root=ET.fromstring(r.read())
 except Exception:return []
 out=[]
 for st in root.findall('station'):
  sid=(st.findtext('id') or '').strip();name=(st.findtext('name') or sid).strip();logos=[]
  for node in st.findall('logo'):
   if node.text and node.text.strip():
    try:score=int(node.get('width') or 0)*int(node.get('height') or 0)
    except:score=0
    logos.append((score,node.text.strip()))
  logo=max(logos,key=lambda x:x[0])[1] if logos else ''
  if sid:out.append((sid,{'name':name,'logo':logo,'region':region(n),'pref':n,'area':area}))
 return out

def stations(force=False):
 with LOCK:
  if S['stations'] is not None and not force:return S['stations']
 result={};by_pref={}
 with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
  fs={ex.submit(fetch_station_area,n):n for n in range(1,48)}
  for f in concurrent.futures.as_completed(fs):by_pref[fs[f]]=f.result()
 for n in range(1,48):
  for sid,m in by_pref.get(n,[]):
   if sid not in result:m['areas']=[m['area']];result[sid]=m
   elif m['area'] not in result[sid]['areas']:result[sid]['areas'].append(m['area'])
 with LOCK:S['stations']=result
 return result

def epg(force=False):
 with LOCK:
  if S['epg'] is not None and not force:return S['epg']
 data=build_xmltv(3)
 with LOCK:S['epg']=data
 return data

def station_area(sid,premium):
 meta=stations().get(sid)
 if not meta:raise RuntimeError(f'unknown Radiko station: {sid}')
 areas=meta.get('areas') or [meta['area']];local=local_area()
 if local in areas:return local
 if premium:return areas[0]
 raise RuntimeError(f'{sid} is not available in local area {local}; Premium is required')

def stream_urls(sid,areafree):
 out=[]
 for base in (API,WEB):
  try:
   with open_url(f'{base}/v3/station/stream/pc_html5/{sid}.xml',{'User-Agent':'Mozilla/5.0'},timeout=15) as r:root=ET.fromstring(r.read())
  except Exception:continue
  want='1' if areafree else '0'
  for node in root.findall('url'):
   if node.get('areafree')==want and node.get('timefree','0')=='0':
    p=node.find('playlist_create_url')
    if p is not None and p.text and p.text.strip() not in out:out.append(p.text.strip())
  if out:break
 fallback='https://alliance-stream-radiko.smartstream.ne.jp/so/playlist.m3u8'
 if fallback not in out:out.insert(0,fallback)
 return out

def media_headers(token,area):return {'X-Radiko-AuthToken':token,'X-Radiko-AreaId':area,'User-Agent':'Mozilla/5.0','Referer':'https://radiko.jp/'}

def get_live_master(sid,refresh=False):
 mail=os.environ.get('RADIKO_MAIL','').strip();pw=os.environ.get('RADIKO_PASSWORD','').strip()
 _,premium=premium_login(force=refresh) if mail and pw else (None,False)
 area=station_area(sid,premium);token,premium=auth_area(area,force=refresh);errs=[]
 for base in stream_urls(sid,premium):
  for typ in (('c','b') if premium else ('b',)):
   q=urllib.parse.urlencode({'station_id':sid,'l':195,'lsid':'alliance','type':typ,'noad':1});url=base+('&' if '?' in base else '?')+q
   try:
    with open_url(url,media_headers(token,area),timeout=20) as r:text=r.read().decode('utf-8','replace')
    if '#EXTM3U' in text:return area,url,text
   except Exception as e:errs.append(f'{typ}:{type(e).__name__}:{getattr(e,"code","")}')
 if not refresh:return get_live_master(sid,True)
 raise RuntimeError(f'no playable URL for {sid} area={area}: '+','.join(errs[-8:]))

def get_live_auto():
 local=local_area();errs=[]
 for sid,m in stations().items():
  if local not in m.get('areas',[]):continue
  try:a,u,t=get_live_master(sid);return sid,a,u,t
  except Exception as e:errs.append(f'{sid}:{e}')
  if len(errs)>=20:break
 raise RuntimeError('no local live station: '+' | '.join(errs[-3:]))

def rewrite_m3u(text,src,base,area=None):
 out=[]
 for line in text.splitlines():
  s=line.strip()
  if s and not s.startswith('#'):
   line=base+'/proxy?u='+urllib.parse.quote(urljoin(src,s),safe='')
   if area:line+='&a='+urllib.parse.quote(area,safe='')
  out.append(line)
 return '\n'.join(out)+'\n'

def freewifi(base):
 with open_url(FREEWIFI_REMOTE,{'User-Agent':'Mozilla/5.0'},timeout=20) as r:text=r.read().decode('utf-8-sig','replace')
 return text.replace('http://127.0.0.1:9395/',base+'/').encode()

def proxied(url,area,refresh=False):
 if not area:area=local_area()
 token,_=auth_area(area,force=refresh)
 try:return open_url(url,media_headers(token,area),timeout=25)
 except urllib.error.HTTPError as e:
  if e.code in (401,403) and not refresh:return proxied(url,area,True)
  raise

def local_ip():
 try:
  s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.connect(('8.8.8.8',80));ip=s.getsockname()[0];s.close();return ip
 except:return 'PC-LAN-IP'

class Handler(BaseHTTPRequestHandler):
 server_version='RadikoProxy/4.0'
 def log_message(self,fmt,*args):print('[radiko] '+fmt%args,flush=True)
 def sendb(self,status,data,ct):
  self.send_response(status);self.send_header('Content-Type',ct);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.send_header('Access-Control-Allow-Origin','*');self.end_headers();self.wfile.write(data)
 def do_GET(self):
  p=urllib.parse.urlsplit(self.path);base=f"http://{self.headers.get('Host',f'{HOST}:{PORT}')}"
  try:
   if p.path=='/health':self.sendb(200,b'OK\n','text/plain');return
   if p.path=='/ready':
    local=local_area(force=True);mail=os.environ.get('RADIKO_MAIL','').strip();pw=os.environ.get('RADIKO_PASSWORD','').strip();mode='free'
    if mail and pw:premium_login(force=True);mode='premium'
    auth_area(local,force=True);ss=stations()
    self.sendb(200,f'OK {local} mode={mode} stations={len(ss)} auth=current-mobile\n'.encode(),'text/plain');return
   if p.path=='/epg.xml':self.sendb(200,epg(),'application/xml');return
   if p.path=='/freewifi.m3u':self.sendb(200,freewifi(base),'audio/x-mpegurl');return
   if p.path in ('/','/playlist.m3u'):
    ss=stations();order={x:i for i,x in enumerate(('北海道','東北','関東','甲信越','東海','近畿','四国','中国','九州沖縄'))};lines=[f'#EXTM3U url-tvg="{base}/epg.xml"']
    for sid,m in sorted(ss.items(),key=lambda x:(order.get(x[1]['region'],99),x[1]['pref'],x[1]['name'])):lines += [f'#EXTINF:-1 tvg-id="radiko.{sid}" tvg-logo="{m["logo"]}" group-title="{m["region"]}",{m["name"]}',f'{base}/live/{urllib.parse.quote(sid)}']
    self.sendb(200,('\n'.join(lines)+'\n').encode(),'audio/x-mpegurl');return
   if p.path=='/live-auto':
    sid,a,u,t=get_live_auto();self.sendb(200,(f'# auto-station={sid} area={a}\n'+rewrite_m3u(t,u,base,a)).encode(),'application/vnd.apple.mpegurl');return
   if p.path.startswith('/live/'):
    sid=urllib.parse.unquote(p.path.split('/',2)[2]);a,u,t=get_live_master(sid);self.sendb(200,rewrite_m3u(t,u,base,a).encode(),'application/vnd.apple.mpegurl');return
   if p.path=='/proxy':
    q=urllib.parse.parse_qs(p.query);u=(q.get('u') or [''])[0];a=(q.get('a') or [''])[0]
    if not u.startswith(('http://','https://')):self.send_error(400,'bad proxy URL');return
    with proxied(u,a) as r:
     d=r.read();ct=r.headers.get_content_type();ism='mpegurl' in ct or u.lower().split('?',1)[0].endswith(('.m3u8','.m3u')) or d.startswith(b'#EXTM3U')
     if ism:d=rewrite_m3u(d.decode('utf-8','replace'),u,base,a).encode();ct='application/vnd.apple.mpegurl'
     self.sendb(200,d,ct or 'application/octet-stream')
    return
   self.send_error(404)
  except Exception as e:
   print(f'[radiko] ERROR {p.path}: {type(e).__name__}: {e}',flush=True)
   try:self.send_error(502,str(e))
   except:pass

def main():
 ip=local_ip();print(f'radiko proxy listening: http://{HOST}:{PORT}',flush=True);print(f'PC playlist: http://127.0.0.1:{PORT}/playlist.m3u',flush=True);print(f'LAN radiko playlist: http://{ip}:{PORT}/playlist.m3u',flush=True);print(f'LAN FreeWiFi playlist: http://{ip}:{PORT}/freewifi.m3u',flush=True);print(f'XMLTV EPG: http://{ip}:{PORT}/epg.xml',flush=True);ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
if __name__=='__main__':main()
