from __future__ import annotations
import json,re,shutil
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont

ROOT=Path('logos/youtube'); ROOT.mkdir(parents=True,exist_ok=True)
RAW='https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/youtube/'
SRC=[Path('general_youtube_sources.json'),Path('general_youtube_sources_ports.json'),Path('general_youtube_sources_airports.json')]
PL=[Path('general_youtube.m3u'),Path('freewifi'),Path('kana_tube.m3u')]
SIZE=512; KANA='youtube.kana_tube'
FONTS=[
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJKjp-Bold.otf',
    '/usr/share/fonts/opentype/noto/NotoSansCJKjp-Bold.ttf',
    '/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc',
]
FONT=next((x for x in FONTS if Path(x).exists()),None)
if not FONT:
    raise RuntimeError('Japanese font missing: install fonts-noto-cjk before generating YouTube logos')

def ft(n):
    return ImageFont.truetype(FONT,n)

def fit(d,s,w,n=48,m=18):
    for z in range(n,m-1,-2):
        f=ft(z); b=d.textbbox((0,0),s,font=f)
        if b[2]-b[0]<=w:return f
    return ft(m)

def center(d,s,y,f,c):
    b=d.textbbox((0,0),s,font=f); d.text(((SIZE-(b[2]-b[0]))/2-b[0],y-b[1]),s,font=f,fill=c)

def items():
    out=[]; seen=set()
    for p in SRC:
        if not p.exists():continue
        for x in json.loads(p.read_text(encoding='utf-8')):
            cid=str(x.get('id') or '')
            if cid.startswith('youtube.') and cid not in seen: seen.add(cid); out.append(x)
    return out

def slug(cid):return re.sub(r'[^a-z0-9_]+','_',cid.split('.',1)[-1].lower()).strip('_')
def fname(n,cid):return f'yt_{n:02d}_{slug(cid)}.png'

def kind(x):
    cid=str(x.get('id') or '').lower(); name=str(x.get('name') or ''); grp=str(x.get('group') or '')
    tests=[
      ('airport','airport' in cid or '空港' in name),('horse','konodo' in cid or '馬' in name),('dog','柴犬' in name),
      ('animal','monkey' in cid or 'チンチラ' in name or grp=='動物'),('baseball','mandarin' in cid),
      ('shrine','fushimi' in cid or 'jinja' in cid or '神社' in name),('temple','daigoji' in cid or '寺' in name),
      ('castle','castle' in cid or '城' in name),('factory','clean' in cid or 'クリーンセンター' in name),
      ('hot','dogo' in cid or '温泉' in name),('parking','parking' in cid or '駐車場' in name),('dam','dam' in cid or 'ダム' in name),
      ('mountain','ropeway' in cid or 'スキー' in name or '山系' in name or '皿ヶ嶺' in name),
      ('bridge','bridge' in cid or 'しまなみ' in name or '大橋' in name or '瀬戸大橋' in name),
      ('harbor','port' in cid or '港' in name or '湾' in name or 'waterfront' in cid or '海側' in name),
      ('river','katsuragawa' in cid or '桂川' in name),('train','rail' in cid or 'station' in cid or 'loop' in cid or grp=='交通')]
    if cid==KANA:return 'kana'
    return next((k for k,v in tests if v),'city')

def icon(d,k):
    navy=(32,59,83); blue=(67,160,218); red=(216,67,58); brown=(118,77,48); green=(69,151,85); white=(250,250,250)
    if k=='airport':
        d.rectangle((75,275,440,330),fill=(200,220,234),outline=navy,width=5); d.polygon([(80,190),(325,145),(430,178),(325,202),(275,250),(245,250),(260,205),(150,220)],fill=white,outline=navy)
    elif k=='train':
        d.rounded_rectangle((85,135,425,305),28,fill=white,outline=navy,width=7); d.rectangle((115,165,395,215),fill=(115,185,225),outline=navy,width=4); d.rectangle((105,240,405,262),fill=blue); d.ellipse((135,280,180,325),fill=navy); d.ellipse((330,280,375,325),fill=navy)
    elif k=='harbor':
        d.rectangle((60,255,452,330),fill=blue); d.polygon([(110,235),(350,235),(320,285),(145,285)],fill=white,outline=navy); d.rectangle((205,180,292,235),fill=white,outline=navy,width=5); d.rectangle((238,140,258,180),fill=red)
    elif k=='bridge':
        d.rectangle((55,295,455,340),fill=blue); d.line((70,260,445,260),fill=navy,width=12); d.line((125,260,125,175),fill=navy,width=12); d.line((385,260,385,175),fill=navy,width=12); d.arc((125,175,385,330),180,360,fill=navy,width=8)
    elif k=='river':
        d.polygon([(205,90),(310,90),(285,165),(345,245),(275,350),(185,350),(235,255),(175,180)],fill=blue); d.polygon([(55,315),(155,205),(235,315)],fill=green); d.polygon([(260,315),(360,190),(460,315)],fill=(75,130,80))
    elif k in ('horse','dog','animal'):
        col=(177,111,62) if k=='horse' else (221,143,66) if k=='dog' else (205,158,100); d.ellipse((165,125,355,320),fill=col,outline=brown,width=6); d.polygon([(180,160),(145,95),(215,140)],fill=col,outline=brown); d.polygon([(340,160),(375,95),(305,140)],fill=col,outline=brown); d.ellipse((220,210,300,280),fill=(240,214,178)); d.ellipse((205,180,225,200),fill=navy); d.ellipse((295,180,315,200),fill=navy)
    elif k=='shrine':
        d.rectangle((130,140,155,325),fill=red); d.rectangle((355,140,380,325),fill=red); d.rectangle((95,125,415,155),fill=red); d.rectangle((125,180,385,200),fill=(238,126,45))
    elif k=='temple':
        for y,w in [(145,230),(205,190),(260,145)]:
            x=(SIZE-w)//2; d.polygon([(x,y+30),(x+w//2,y),(x+w,y+30),(x+w-25,y+45),(x+25,y+45)],fill=navy)
    elif k=='castle':
        d.rectangle((195,215,315,325),fill=white,outline=navy,width=5); d.polygon([(160,225),(255,170),(350,225)],fill=navy); d.rectangle((215,150,295,205),fill=white,outline=navy,width=5); d.polygon([(185,160),(255,115),(325,160)],fill=navy)
    elif k=='factory':
        d.rectangle((110,225,410,330),fill=(190,200,206),outline=navy,width=5); d.rectangle((150,135,195,225),fill=(110,125,140),outline=navy,width=5); d.rectangle((255,165,300,225),fill=(110,125,140),outline=navy,width=5)
    elif k=='hot':
        d.rounded_rectangle((105,230,405,330),28,fill=blue,outline=navy,width=6); [d.arc((x-28,120,x+28,225),80,280,fill=red,width=8) for x in (185,255,325)]
    elif k=='parking':
        d.rounded_rectangle((115,115,265,310),12,fill=(47,124,203)); center(d,'P',145,ft(120),white); d.rounded_rectangle((280,235,430,315),18,fill=red,outline=navy,width=5)
    elif k=='dam':
        d.rectangle((85,120,180,330),fill=blue); d.polygon([(180,140),(405,210),(360,330),(180,330)],fill=(185,194,200),outline=navy)
    elif k=='mountain':
        d.polygon([(80,325),(225,135),(315,325)],fill=green,outline=navy); d.polygon([(230,325),(355,175),(455,325)],fill=(75,130,80),outline=navy); d.line((120,125,400,125),fill=(110,125,140),width=5); d.rectangle((285,105,345,150),fill=red,outline=navy,width=4)
    elif k=='baseball':
        d.ellipse((165,120,345,300),fill=white,outline=navy,width=6); d.arc((175,135,255,285),280,80,fill=red,width=5); d.arc((255,135,335,285),100,260,fill=red,width=5); d.line((355,100,395,330),fill=brown,width=16)
    else:
        for x,y,w,h in [(95,190,80,135),(190,135,100,190),(310,170,105,155)]: d.rectangle((x,y,x+w,y+h),fill=(85,151,198),outline=navy,width=5)

def lines(name):
    s=re.sub(r'【([^】]+)】',r' \1',name).replace(' LIVE','').strip()
    if len(s)<=12:return [s]
    for sep in ('・',' ','／','ライブカメラ'):
        if sep in s:
            p=[x.strip() for x in s.split(sep) if x.strip()]
            if len(p)>1:return [p[0],('・' if sep=='・' else ' ').join(p[1:])]
    n=len(s)//2; return [s[:n],s[n:]]

def render(n,x,f):
    out=ROOT/f
    if x.get('id')==KANA and out.exists() and out.stat().st_size>1000:return
    k=kind(x); img=Image.new('RGB',(SIZE,SIZE),(249,249,246)); d=ImageDraw.Draw(img); accent=(227,73,103) if k=='kana' else (31,111,181)
    d.rounded_rectangle((8,8,SIZE-8,SIZE-8),38,fill=(248,250,250),outline=accent,width=8); d.rectangle((16,352,SIZE-16,SIZE-16),fill='white'); icon(d,k)
    badge=f'{n:02d}'; d.ellipse((18,18,125,125),fill=accent,outline=(53,45,45),width=6); bf=fit(d,badge,90,58,34); b=d.textbbox((0,0),badge,font=bf); d.text((71-(b[2]-b[0])/2-b[0],69-(b[3]-b[1])/2-b[1]),badge,font=bf,fill='white')
    ls=lines(str(x.get('name') or slug(str(x.get('id')))))
    if len(ls)==1:center(d,ls[0],395,fit(d,ls[0],450,46,20),(48,56,64))
    else:center(d,ls[0],375,fit(d,ls[0],450,40,19),(48,56,64)); center(d,ls[1],428,fit(d,ls[1],450,36,18),accent)
    img.resize((418,418),Image.Resampling.LANCZOS).save(out,'PNG',optimize=True)

def patch_sources(mp):
    for p in SRC:
        if not p.exists():continue
        a=json.loads(p.read_text(encoding='utf-8'))
        for x in a:
            if x.get('id') in mp:x['logo']=RAW+mp[x['id']]
        p.write_text(json.dumps(a,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def patch_playlist(p,mp):
    if not p.exists():return
    out=[]
    for line in p.read_text(encoding='utf-8-sig',errors='replace').splitlines():
        if line.startswith('#EXTINF:'):
            m=re.search(r'tvg-id="([^"]+)"',line); f=mp.get(m.group(1)) if m else None
            if f:
                u=RAW+f
                line=re.sub(r'tvg-logo="[^"]*"',f'tvg-logo="{u}"',line,count=1) if 'tvg-logo="' in line else line.replace(' group-title=',f' tvg-logo="{u}" group-title=',1)
        out.append(line)
    p.write_text('\n'.join(out).rstrip()+'\n',encoding='utf-8')

def cleanup():
    for p in list(ROOT.iterdir()):
        if p.name.startswith(('yt43_','yt_unified_','ehime_port_')) or p.name in {'unified','guinea_youtube.jpg'}:
            shutil.rmtree(p) if p.is_dir() else p.unlink()

def main():
    a=items(); mp={}
    for n,x in enumerate(a,1): mp[x['id']]=fname(n,x['id']); render(n,x,mp[x['id']])
    patch_sources(mp)
    for p in PL:patch_playlist(p,mp)
    cleanup(); print('canonical YouTube logos',len(mp))

if __name__=='__main__':main()
