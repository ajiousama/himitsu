from pathlib import Path
import math
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "youtube" / "logos" / "general"

ITEMS = [
("yt_01_natsu_shiba.png","柴犬なつ","dog"),
("yt_11_dogo.png","松山・道後","dogo"),
("yt_12_honmachi.png","松山・本町","honmachi"),
("yt_13_yawatahama_sea.png","八幡浜・海","yawatahama_sea"),
("yt_14_yawatahama_parking.png","八幡浜・駐車場","yawatahama_parking"),
("yt_15_uwajima.png","宇和島","uwajima"),
("yt_22_ehime_hashihama_port.png","今治・波止浜港","hashihama"),
("yt_23_ehime_misaki_port.png","伊方・三崎港","misaki"),
("yt_24_ehime_misho_port.png","愛南・御荘港","misho"),
("yt_65_fushimi_inari.png","京都・伏見稲荷","fushimi"),
("yt_67_oharano_jinja.png","京都・大原野神社","oharano"),
("yt_70_tsukamoto.png","松山・束本","tsukamoto"),
("yt_71_masaki_hama.png","松前町・浜","masaki"),
]

W=H=512

def font_path():
    for p in [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]:
        if Path(p).exists():
            return p
    raise FileNotFoundError("font")
FONT=font_path()
def fnt(n): return ImageFont.truetype(FONT,n)

def gradient(im, a, b):
    px=im.load()
    for y in range(H):
        t=y/(H-1)
        c=tuple(int(a[i]*(1-t)+b[i]*t) for i in range(3))
        for x in range(W): px[x,y]=(*c,255)

def poly(d,pts,fill,outline=None,width=1):
    d.polygon(pts,fill=fill)
    if outline: d.line(pts+[pts[0]],fill=outline,width=width,joint="curve")

def mountain(d, base=260, peakx=300, peaky=110, color="#5b8fb0", snow=False):
    poly(d,[(0,base),(peakx,peaky),(512,base)],color)
    if snow:
        poly(d,[(peakx,peaky),(peakx-55,165),(peakx-20,150),(peakx,175),(peakx+28,148),(peakx+70,168)],"#f7fbff")

def water(d,y=280):
    d.rectangle((0,y,512,430),fill="#2fa8d5")
    for yy in range(y+16,425,24): d.line((10,yy,500,yy),fill="#8ee4f2",width=3)

def city(d,base=355):
    colors=["#5f7792","#708aa2","#55728f"]
    xs=[15,70,125,185,245,310,375,440]; hs=[100,130,85,150,110,140,95,120]
    for i,x in enumerate(xs):
        h=hs[i]; d.rectangle((x,base-h,x+45,base),fill=colors[i%3])
        for yy in range(base-h+15,base-10,20):
            for xx in range(x+8,x+40,15): d.rectangle((xx,yy,xx+6,yy+7),fill="#d5edf4")

def title(d,text,badge="#e51f2c"):
    size=48 if len(text)<=8 else 40 if len(text)<=11 else 34
    font=fnt(size)
    while d.textbbox((0,0),text,font=font)[2] > 470 and size>28:
        size-=2; font=fnt(size)
    tw=d.textbbox((0,0),text,font=font)[2]
    d.text(((512-tw)//2,20),text,font=font,fill="white",stroke_width=8,stroke_fill="#173b70")
    d.rounded_rectangle((170,430,342,492),16,fill=badge,outline="white",width=4)
    poly(d,[(195,447),(195,477),(222,462)],"white")
    d.text((230,439),"LIVE",font=fnt(38),fill="white")

def port(d, boats=3):
    mountain(d,245,290,125,"#5f9068",False)
    water(d,245)
    d.rectangle((0,375,512,430),fill="#b5b7b4")
    for i in range(boats):
        x=40+i*135
        poly(d,[(x,320),(x+95,320),(x+78,355),(x+15,355)],"#f6f9fb",outline="#315f7a",width=3)
        d.rectangle((x+25,292,x+68,321),fill="#f4f7f8",outline="#315f7a",width=2)
        d.line((x+47,292,x+47,260),fill="#444",width=3)

def shrine(d, torii=False):
    d.rectangle((0,300,512,430),fill="#d2b27f")
    d.rectangle((110,205,402,360),fill="#8c5a34")
    d.rectangle((145,230,365,360),fill="#f2efe4")
    poly(d,[(90,205),(256,145),(420,205)],"#3c3b3b")
    if torii:
        for x in range(20,500,55):
            d.rectangle((x,155,x+15,410),fill="#e34b2f")
            d.rectangle((x-10,165,x+28,180),fill="#e34b2f")
    else:
        d.ellipse((40,335,85,380),fill="#c9c9c0")
        d.ellipse((430,335,475,380),fill="#c9c9c0")

def dog(d):
    mountain(d,250,300,120,"#6a9d72",False)
    d.rectangle((0,250,512,430),fill="#79b966")
    d.ellipse((135,255,360,430),fill="#d99a58",outline="#8d5c33",width=5)
    d.ellipse((170,190,325,340),fill="#d99a58",outline="#8d5c33",width=5)
    poly(d,[(185,210),(210,150),(235,215)],"#c27f43")
    poly(d,[(270,210),(300,150),(315,220)],"#c27f43")
    d.ellipse((205,245,225,265),fill="#222"); d.ellipse((275,245,295,265),fill="#222")
    d.ellipse((235,275,270,305),fill="#2d2620")

def street(d):
    mountain(d,245,285,135,"#628a74",False); city(d,330)
    d.polygon([(180,300),(335,300),(420,430),(80,430)],fill="#cfd5d7")
    d.line((255,310,255,430),fill="white",width=8)
    for x in (80,420):
        d.rectangle((x,230,x+18,360),fill="#6f4f33")

def draw(theme,text):
    im=Image.new("RGBA",(W,H),(255,255,255,255)); gradient(im,(52,182,246),(205,242,255)); d=ImageDraw.Draw(im)
    badge="#e51f2c"
    if theme=="dog":
        dog(d); badge="#36a241"
    elif theme=="dogo":
        d.rectangle((0,250,512,430),fill="#d5c19a")
        d.rectangle((80,170,430,340),fill="#8c5c3d")
        d.rectangle((120,210,390,340),fill="#efe8d6")
        poly(d,[(60,170),(255,95),(450,170)],"#3d4143")
        mountain(d,245,380,130,"#6c9371",False)
    elif theme=="honmachi":
        street(d)
        # tram
        d.rounded_rectangle((210,270,330,365),12,fill="#d66d37",outline="#6f3b25",width=4)
        d.rectangle((225,285,265,320),fill="#bfe3ec"); d.rectangle((275,285,315,320),fill="#bfe3ec")
    elif theme=="yawatahama_sea":
        port(d,2)
    elif theme=="yawatahama_parking":
        mountain(d,245,300,125,"#648f69",False); water(d,245)
        d.rectangle((0,320,512,430),fill="#c9c8c3")
        for i,x in enumerate([45,170,300,405]):
            d.rounded_rectangle((x,340,x+70,385),8,fill=["#f4f5f3","#d2d4d5","#fafafa","#e3e4e3"][i],outline="#666",width=2)
    elif theme=="uwajima":
        mountain(d,245,330,135,"#668f72",False)
        d.rectangle((0,300,512,430),fill="#79a968")
        d.rectangle((170,220,350,345),fill="#f2f0e7",outline="#414141",width=3)
        poly(d,[(145,220),(260,160),(375,220)],"#343b42")
        d.rectangle((205,185,315,235),fill="#f2f0e7",outline="#414141",width=3)
        poly(d,[(185,185),(260,140),(335,185)],"#343b42")
    elif theme in {"hashihama","misaki","misho"}:
        port(d,3)
        if theme=="misaki":
            d.rectangle((360,245,385,335),fill="#f3f3ef",outline="#566d78",width=3); d.ellipse((352,232,393,255),fill="#f3f3ef",outline="#566d78",width=3)
    elif theme=="fushimi":
        shrine(d,True)
    elif theme=="oharano":
        shrine(d,False)
    elif theme=="tsukamoto":
        mountain(d,230,280,130,"#678f73",False); city(d,345)
        d.rectangle((0,345,512,430),fill="#d0d4d5")
        for x in range(40,500,85):
            d.rectangle((x,285,x+60,360),fill="#f1eee5",outline="#6b6b67",width=2)
            poly(d,[(x-5,285),(x+30,255),(x+65,285)],"#56544d")
        badge="#36a241"
    elif theme=="masaki":
        mountain(d,250,330,165,"#6d956d",False); water(d,245)
        d.rectangle((0,375,512,430),fill="#e9d59b")
        d.arc((260,260,520,450),180,355,fill="#f3f0df",width=14)
        badge="#2f7fd5"
    title(d,text,badge)
    mask=Image.new("L",(W,H),0); md=ImageDraw.Draw(mask); md.rounded_rectangle((0,0,W-1,H-1),36,fill=255)
    out=Image.new("RGBA",(W,H),(255,255,255,0)); out.paste(im,(0,0),mask)
    return out

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    for fn,text,theme in ITEMS:
        draw(theme,text).save(OUT/fn,optimize=True)
        print(fn)

if __name__=="__main__":
    main()
