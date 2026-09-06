from pathlib import Path
from PIL import Image, ImageDraw, ImageFont
import json, re, math

SRC=Path('general_youtube_sources.json')
PLAYLISTS=[Path('general_youtube.m3u'),Path('freewifi')]
OUTDIR=Path('logos/youtube/unified')
RAW='https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/youtube/unified/'
W=H=512

FONT_CANDIDATES=[
 '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
 '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
 '/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc',
 '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
]

def font(size):
    for p in FONT_CANDIDATES:
        if Path(p).exists(): return ImageFont.truetype(p,size)
    return ImageFont.load_default()

def slug(tvg):
    s=tvg.replace('youtube.','').replace('.','_')
    s=re.sub(r'[^A-Za-z0-9_-]+','_',s).strip('_')
    return s or 'youtube'

def category(item):
    name=item.get('name',''); group=item.get('group','')
    if '空港' in name or 'airport' in item.get('id',''): return 'AIR'
    if any(k in name for k in ['港','海峡','ウォーターフロント','瀬戸大橋']): return 'SEA'
    if any(k in name for k in ['駅','鉄道','環状線','バス','サービスエリア','道路']): return 'RAIL'
    if group=='動物' or any(k in name for k in ['犬','馬','猿','チンチラ','ナミビア']): return 'ANIMAL'
    if any(k in name for k in ['野球','パイレーツ']): return 'SPORT'
    if any(k in name for k in ['山','ダム','桂川','スキー','石鎚','皿ヶ嶺','道後','城']): return 'SCENIC'
    if item.get('id')=='youtube.kana_tube': return 'KANA'
    return 'LIVE'

ACCENTS={
 'AIR':(38,122,218,255),'SEA':(0,140,170,255),'RAIL':(245,145,25,255),
 'ANIMAL':(49,150,88,255),'SPORT':(0,116,188,255),'SCENIC':(89,120,55,255),
 'KANA':(235,55,55,255),'LIVE':(170,70,180,255),
}
LABELS={'AIR':'AIRPORT','SEA':'WATERFRONT','RAIL':'TRAFFIC','ANIMAL':'ANIMAL','SPORT':'SPORTS','SCENIC':'LIVE CAM','KANA':'KANA TUBE','LIVE':'LIVE CAM'}

def rounded(draw,box,r,fill,outline=None,width=1): draw.rounded_rectangle(box,radius=r,fill=fill,outline=outline,width=width)

def play_badge(draw,x,y,s):
    rounded(draw,(x,y,x+s,y+s),int(s*.22),(255,0,0,255))
    tri=[(x+s*.40,y+s*.28),(x+s*.40,y+s*.72),(x+s*.72,y+s*.50)]
    draw.polygon(tri,fill=(255,255,255,255))

def icon(draw,cat,cx,cy,s,accent):
    # Deliberately simple geometric pictograms: consistent, readable at IPTV icon size.
    if cat=='AIR':
        pts=[(cx-s*.38,cy+s*.05),(cx+s*.38,cy-s*.18),(cx+s*.16,cy+s*.05),(cx+s*.34,cy+s*.27),(cx+s*.18,cy+s*.31),(cx,cy+s*.12),(cx-s*.23,cy+s*.28),(cx-s*.34,cy+s*.23),(cx-s*.16,cy+s*.03)]
        draw.polygon(pts,fill=accent)
    elif cat=='SEA':
        draw.polygon([(cx-s*.34,cy),(cx+s*.34,cy),(cx+s*.18,cy+s*.22),(cx-s*.22,cy+s*.22)],fill=accent)
        draw.line((cx-s*.32,cy+s*.31,cx+s*.32,cy+s*.31),fill=accent,width=max(3,int(s*.08)))
        draw.rectangle((cx-s*.05,cy-s*.30,cx+s*.05,cy),fill=accent)
    elif cat=='RAIL':
        rounded(draw,(cx-s*.28,cy-s*.30,cx+s*.28,cy+s*.25),int(s*.08),accent)
        draw.rectangle((cx-s*.18,cy-s*.18,cx-s*.03,cy-s*.02),fill='white')
        draw.rectangle((cx+s*.03,cy-s*.18,cx+s*.18,cy-s*.02),fill='white')
        draw.ellipse((cx-s*.18,cy+s*.17,cx-s*.07,cy+s*.28),fill=(40,40,40,255)); draw.ellipse((cx+s*.07,cy+s*.17,cx+s*.18,cy+s*.28),fill=(40,40,40,255))
    elif cat=='ANIMAL':
        for dx,dy in [(-.20,-.15),(0,-.24),(.20,-.15)]: draw.ellipse((cx+s*(dx-.09),cy+s*(dy-.09),cx+s*(dx+.09),cy+s*(dy+.09)),fill=accent)
        draw.ellipse((cx-s*.23,cy-s*.02,cx+s*.23,cy+s*.32),fill=accent)
    elif cat=='SPORT':
        draw.ellipse((cx-s*.30,cy-s*.30,cx+s*.30,cy+s*.30),fill=accent)
        draw.arc((cx-s*.22,cy-s*.22,cx+s*.22,cy+s*.22),0,360,fill='white',width=max(2,int(s*.05)))
        draw.line((cx-s*.28,cy,cx+s*.28,cy),fill='white',width=max(2,int(s*.05)))
    else:
        rounded(draw,(cx-s*.31,cy-s*.22,cx+s*.31,cy+s*.22),int(s*.08),accent)
        draw.ellipse((cx-s*.12,cy-s*.12,cx+s*.12,cy+s*.12),outline='white',width=max(3,int(s*.05)))
        draw.ellipse((cx+s*.17,cy-s*.14,cx+s*.24,cy-s*.07),fill='white')

def split_lines(text):
    text=re.sub(r'\s+',' ',text).strip()
    # Remove noisy suffixes while keeping the identity visible.
    text=text.replace('公式ライブカメラ','').replace('ライブカメラ','').replace(' LIVE','').strip(' ・')
    if len(text)<=9: return [text]
    if len(text)<=18:
        mid=len(text)//2
        cut=min(range(max(1,mid-3),min(len(text),mid+4)),key=lambda i: abs(i-mid))
        return [text[:cut],text[cut:]]
    # long names: balanced 3 lines
    n=len(text); a=max(1,n//3); b=max(a+1,2*n//3)
    return [text[:a],text[a:b],text[b:]]

def fit_text(draw,lines,maxw,maxh):
    size=78 if len(lines)==1 else (63 if len(lines)==2 else 49)
    while size>=28:
        f=font(size); spacing=int(size*.18)
        widths=[]; heights=[]
        for t in lines:
            bb=draw.textbbox((0,0),t,font=f,stroke_width=1); widths.append(bb[2]-bb[0]); heights.append(bb[3]-bb[1])
        h=sum(heights)+spacing*(len(lines)-1)
        if max(widths or [0])<=maxw and h<=maxh: return f,spacing
        size-=2
    return font(28),5

def render(item,path):
    cat=category(item); accent=ACCENTS[cat]
    im=Image.new('RGBA',(W,H),(0,0,0,0)); d=ImageDraw.Draw(im)
    # white card + dark rim: survives both black and white player backgrounds.
    rounded(d,(12,12,500,500),54,(255,255,255,255),(28,28,31,255),14)
    # subtle category corner field
    rounded(d,(28,28,484,126),30,(246,247,249,255))
    play_badge(d,42,42,70)
    lab=LABELS[cat]; lf=font(25)
    d.text((128,60),lab,font=lf,fill=(38,38,42,255))
    rounded(d,(386,52,470,102),22,(255,0,0,255)); d.text((402,60),'LIVE',font=font(22),fill='white')
    icon(d,cat,420,190,92,accent)
    lines=split_lines(item.get('name','YouTube LIVE'))
    f,spacing=fit_text(d,lines,390,220)
    boxes=[d.textbbox((0,0),t,font=f,stroke_width=2) for t in lines]
    hs=[b[3]-b[1] for b in boxes]; total=sum(hs)+spacing*(len(lines)-1)
    y=270-total/2
    for t,b,h in zip(lines,boxes,hs):
        tw=b[2]-b[0]
        d.text(((W-tw)/2,y),t,font=f,fill=(26,26,30,255),stroke_width=2,stroke_fill=(255,255,255,255))
        y+=h+spacing
    # category accent rule and tiny YouTube marker
    rounded(d,(62,448,450,462),7,accent)
    im.save(path,optimize=True)

def patch_logo_in_text(text,mapping):
    out=[]
    for line in text.splitlines():
        if line.startswith('#EXTINF:'):
            m=re.search(r'tvg-id="([^"]+)"',line)
            if m and m.group(1) in mapping:
                url=mapping[m.group(1)]
                if re.search(r'tvg-logo="[^"]*"',line): line=re.sub(r'tvg-logo="[^"]*"',f'tvg-logo="{url}"',line,count=1)
                elif ' group-title=' in line: line=line.replace(' group-title=',f' tvg-logo="{url}" group-title=',1)
        out.append(line)
    return '\n'.join(out).rstrip()+'\n'

def main():
    OUTDIR.mkdir(parents=True,exist_ok=True)
    items=json.loads(SRC.read_text(encoding='utf-8'))
    targets=[x for x in items if str(x.get('id','')).startswith('youtube.')]
    mapping={}
    for item in targets:
        fn='yt_'+slug(item['id'])+'.png'; url=RAW+fn
        render(item,OUTDIR/fn); mapping[item['id']]=url; item['logo']=url
    SRC.write_text(json.dumps(items,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    for p in PLAYLISTS:
        if p.exists(): p.write_text(patch_logo_in_text(p.read_text(encoding='utf-8-sig',errors='replace'),mapping),encoding='utf-8')
    # Keep the dedicated kana updater from restoring an old logo URL.
    kp=Path('kana_tube_update.py')
    if kp.exists() and 'youtube.kana_tube' in mapping:
        s=kp.read_text(encoding='utf-8',errors='replace')
        s=re.sub(r'^LOGO\s*=\s*.*$',f'LOGO = "{mapping["youtube.kana_tube"]}"',s,flags=re.M)
        kp.write_text(s,encoding='utf-8')
    print('unified YouTube logos:',len(mapping))

if __name__=='__main__': main()
