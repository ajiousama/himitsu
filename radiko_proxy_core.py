#!/usr/bin/env python3
import base64,concurrent.futures,json,os,re,shutil,socket,subprocess,threading,time,urllib.error,urllib.parse,urllib.request
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import urljoin
from radiko_epg import build_xmltv

HOST=os.environ.get('RADIKO_PROXY_HOST','127.0.0.1')
PORT=int(os.environ.get('RADIKO_PROXY_PORT','9395'))
FREEWIFI_REMOTE=os.environ.get('RADIKO_FREEWIFI_URL','https://raw.githubusercontent.com/ajiousama/himitsu/main/freewifi')
API='https://api.radiko.jp'; WEB='https://radiko.jp'
AUTHKEY=b'bcd151073c03b352e1ef2fd66c32209da9ca0afa'
AUTH1_HEADERS={'X-Radiko-App':'pc_html5','X-Radiko-App-Version':'0.0.1','X-Radiko-Device':'pc','X-Radiko-User':'dummy_user'}
L=threading.RLock(); S={'session':None,'premium':None,'premium_error':None,'token':None,'area':None,'mode':None,'auth_time':0,'stations':None,'epg':None}

def open_url(url,headers=None,data=None,timeout=20):
 h={'User-Agent':'curl/8.0','Accept':'*/*'}; h.update(headers or {})
 return urllib.request.urlopen(urllib.request.Request(url,headers=h,data=data),timeout=timeout)

def curl_login(mail,pw):
 exe=shutil.which('curl.exe') or shutil.which('curl')
 if not exe: raise RuntimeError('curl was not found')
 body=urllib.parse.urlencode({'mail':mail,'pass':pw}).encode()
 p=subprocess.run([exe,'-fsS','-X','POST','-H','Content-Type: application/x-www-form-urlencoded','--data-binary','@-',WEB+'/v4/api/member/login'],input=body,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=35)
 if p.returncode: raise RuntimeError(p.stderr.decode('utf-8','replace').strip() or f'curl exit {p.returncode}')
 return json.loads(p.stdout.decode('utf-8','replace'))

def premium_login(force=False):
 mail=os.environ.get('RADIKO_MAIL','').strip(); pw=os.environ.get('RADIKO_PASSWORD','').strip()
 if not mail or not pw: return None,False
 with L:
  if S['session'] and S['premium'] is True and not force: return S['session'],True
  if S['premium_error'] and not force: raise RuntimeError(S['premium_error'])
 try:
  try: o=curl_login(mail,pw)
  except Exception:
   data=urllib.parse.urlencode({'mail':mail,'pass':pw}).encode()
   with open_url(WEB+'/v4/api/member/login',{'Content-Type':'application/x-www-form-urlencoded'},data,30) as r: o=json.loads(r.read().decode())
  sess=str(o.get('radiko_session') or '').strip()
  paid=(str(o.get('areafree') or '')=='1' or str(o.get('paid_member') or '') not in ('','0','false','False'))
  status=str(o.get('status') or '200')
  if status not in ('200','0','true','True') or not sess: raise RuntimeError('Radiko Premium login was rejected')
  if not paid: raise RuntimeError('Radiko account is not enabled for area-free')
 except Exception as e:
  msg=f'Premium login failed: {type(e).__name__}: {e}'
  with L: S['session']=None; S['premium']=False; S['premium_error']=msg
  raise RuntimeError(msg) from e
 with L: S['session']=sess; S['premium']=True; S['premium_error']=None
 print('[radiko] Premium area-free login OK',flush=True)
 return sess,True

def ensure_auth(force=False):
 with L:
  if S['token'] and not force and time.time()-S['auth_time']<3900: return S['session'],S['token'],S['area'],S['mode']
 mail=os.environ.get('RADIKO_MAIL','').strip(); pw=os.environ.get('RADIKO_PASSWORD','').strip()
 session=None; premium=False
 if mail and pw: session,premium=premium_login(force=force)
 with open_url(API+'/v2/api/auth1',AUTH1_HEADERS,timeout=30) as r:
  token=r.headers.get('X-Radiko-AuthToken'); off=r.headers.get('X-Radiko-KeyOffset'); ln=r.headers.get('X-Radiko-KeyLength')
 if not token or off is None or ln is None: raise RuntimeError('Radiko auth1 headers are incomplete')
 off=int(off); ln=int(ln); part=AUTHKEY[off:off+ln]
 if len(part)!=ln: raise RuntimeError(f'Radiko partial-key range invalid offset={off} length={ln}')
 h={'X-Radiko-Device':'pc','X-Radiko-User':'dummy_user','X-Radiko-AuthToken':token,'X-Radiko-PartialKey':base64.b64encode(part).decode()}
 url=API+'/v2/api/auth2'
 if session: url+='?radiko_session='+urllib.parse.quote(session,safe='')
 with open_url(url,h,timeout=30) as r: body=r.read().decode('utf-8','replace').strip()
 if not body or body=='OUT': raise RuntimeError('Radiko auth2 returned OUT')
 area=body.split(',')[0].strip(); mode='premium' if premium else 'free'
 if not re.fullmatch(r'JP\d{1,2}',area): raise RuntimeError(f'Radiko auth2 returned invalid area: {body[:80]}')
 with L: S.update(session=session,token=token,area=area,mode=mode,auth_time=time.time())
 print(f'[radiko] auth OK area={area} mode={mode}',flush=True)
 return session,token,area,mode

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

def _fetch_st(n):
 area=f'JP{n}'
 try:
  with open_url(f'{WEB}/v3/station/list/{area}.xml',timeout=10) as r: root=ET.fromstring(r.read())
 except Exception:return []
 out=[]
 for st in root.findall('station'):
  sid=(st.findtext('id') or '').strip(); name=(st.findtext('name') or sid).strip(); logos=[]
  for x in st.findall('logo'):
   if x.text and x.text.strip():
    try:score=int(x.get('width') or 0)*int(x.get('height') or 0)
    except:score=0
    logos.append((score,x.text.strip()))
  logo=max(logos,key=lambda x:x[0])[1] if logos else ''
  if sid: out.append((sid,{'name':name,'logo':logo,'region':region(n),'pref':n,'area':area}))
 return out

def stations(force=False):
 with L:
  if S['stations'] is not None and not force:return S['stations']
 R={}; res={}
 with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
  fs={ex.submit(_fetch_st,n):n for n in range(1,48)}
  for f in concurrent.futures.as_completed(fs): res[fs[f]]=f.result()
 for n in range(1,48):
  for sid,m in res.get(n,[]):
   if sid not in R: m['areas']=[m['area']]; R[sid]=m
   elif m['area'] not in R[sid]['areas']: R[sid]['areas'].append(m['area'])
 with L:S['stations']=R
 return R

def epg(force=False):
 with L:
  if S['epg'] is not None and not force:return S['epg']
 d=build_xmltv(3)
 with L:S['epg']=d
 return d

def stream_urls(sid,areafree):
 out=[]; want='1' if areafree else '0'
 for base in (API,WEB):
  try:
   with open_url(f'{base}/v3/station/stream/pc_html5/{sid}.xml',timeout=15) as r: root=ET.fromstring(r.read())
  except Exception:continue
  for node in root.findall('url'):
   if node.get('areafree')==want and node.get('timefree','0')=='0':
    p=node.find('playlist_create_url')
    if p is not None and p.text and p.text.strip() not in out: out.append(p.text.strip())
  if out:break
 fallback='https://alliance-stream-radiko.smartstream.ne.jp/so/playlist.m3u8'
 if fallback not in out: out.insert(0,fallback)
 return out

def media_headers(token,area):return {'X-Radiko-AuthToken':token,'X-Radiko-AreaId':area}

def get_live_master(sid,refresh=False):
 session,token,area,mode=ensure_auth(force=refresh); af=(mode=='premium'); meta=stations().get(sid)
 if not meta: raise RuntimeError(f'unknown Radiko station: {sid}')
 if not af and area not in meta.get('areas',[]): raise RuntimeError(f'{sid} is outside local Radiko area {area}; Premium is required')
 errs=[]
 for base in stream_urls(sid,af):
  for typ in (('c','b') if af else ('b',)):
   q=urllib.parse.urlencode({'station_id':sid,'l':195,'lsid':'alliance','type':typ,'noad':1}); url=base+('&' if '?' in base else '?')+q
   try:
    with open_url(url,media_headers(token,area),timeout=20) as r: txt=r.read().decode('utf-8','replace')
    if '#EXTM3U' in txt:return area,url,txt
   except Exception as e: errs.append(f'{typ}:{type(e).__name__}:{getattr(e,"code","")}')
 if not refresh:return get_live_master(sid,True)
 raise RuntimeError(f'no playable URL for {sid} ({mode}): '+','.join(errs[-8:]))

def get_live_auto():
 _,_,area,_=ensure_auth(); errs=[]
 for sid,m in stations().items():
  if area not in m.get('areas',[]):continue
  try:a,u,t=get_live_master(sid); return sid,a,u,t
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
 with open_url(FREEWIFI_REMOTE,timeout=20) as r:t=r.read().decode('utf-8-sig','replace')
 return t.replace('http://127.0.0.1:9395/',base+'/').encode()

def proxied(url,area,refresh=False):
 _,token,current,_=ensure_auth(force=refresh); area=area or current
 try:return open_url(url,media_headers(token,area),timeout=25)
 except urllib.error.HTTPError as e:
  if e.code in (401,403) and not refresh:return proxied(url,area,True)
  raise

def local_ip():
 try:
  s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.connect(('8.8.8.8',80));ip=s.getsockname()[0];s.close();return ip
 except:return 'PC-LAN-IP'

class Handler(BaseHTTPRequestHandler):
 server_version='RadikoProxy/3.2'
 def log_message(self,fmt,*args):print('[radiko] '+fmt%args,flush=True)
 def sendb(self,status,data,ct):
  self.send_response(status);self.send_header('Content-Type',ct);self.send_header('Content-Length',str(len(data)));self.send_header('Cache-Control','no-store');self.send_header('Access-Control-Allow-Origin','*');self.end_headers();self.wfile.write(data)
 def do_GET(self):
  p=urllib.parse.urlsplit(self.path); base=f"http://{self.headers.get('Host',f'{HOST}:{PORT}')}"
  try:
   if p.path=='/health':self.sendb(200,b'OK\n','text/plain');return
   if p.path=='/ready':
    _,_,area,mode=ensure_auth(force=True); ss=stations()
    if mode=='premium':
     test='TBS' if area!='JP13' else 'ABC'; get_live_master(test)
    self.sendb(200,f'OK {area} mode={mode} stations={len(ss)}\n'.encode(),'text/plain');return
   if p.path=='/epg.xml':self.sendb(200,epg(),'application/xml');return
   if p.path=='/freewifi.m3u':self.sendb(200,freewifi(base),'audio/x-mpegurl');return
   if p.path in ('/','/playlist.m3u'):
    ss=stations(); order={x:i for i,x in enumerate(('北海道','東北','関東','甲信越','東海','近畿','四国','中国','九州沖縄'))}; lines=[f'#EXTM3U url-tvg="{base}/epg.xml"']
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
