from pathlib import Path
import json, math
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "youtube" / "config.json"
OUT = ROOT / "youtube" / "logos" / "general"
RAW = "https://raw.githubusercontent.com/ajiousama/himitsu/main/youtube/logos/general/"

ITEMS = [
("youtube.fukuoka_airport","yt_72_fukuoka_airport.png","福岡空港","airport_sakura"),
("youtube.yamaguchi_ube_airport","yt_73_yamaguchi_ube_airport.png","山口宇部空港","airport_coast"),
("youtube.airport_okadama","yt_74_airport_okadama.png","札幌丘珠空港","airport_snow"),
("youtube.airport_aomori","yt_75_airport_aomori.png","青森空港","airport_nebuta"),
("youtube.airport_akita","yt_76_airport_akita.png","秋田空港","airport_akita"),
("youtube.airport_shonai","yt_77_airport_shonai.png","庄内空港","airport_fields"),
("youtube.airport_matsumoto","yt_78_airport_matsumoto.png","信州まつもと空港","airport_castle"),
("youtube.airport_komaki","yt_79_airport_komaki.png","名古屋空港・小牧","airport_shachi"),
("youtube.airport_toyama","yt_80_airport_toyama.png","富山空港","airport_tulip"),
("youtube.airport_shizuoka","yt_81_airport_shizuoka.png","富士山静岡空港","airport_fuji"),
("youtube.airport_ibaraki_hyakuri","yt_82_airport_ibaraki_hyakuri.png","茨城空港・百里基地","airport_fighter"),
("youtube.airport_takamatsu","yt_83_airport_takamatsu.png","高松空港","airport_seto"),
("youtube.airport_kochi","yt_84_airport_kochi.png","高知龍馬空港","airport_ryoma"),
("youtube.airport_saga","yt_85_airport_saga.png","九州佐賀国際空港","airport_balloons"),
("youtube.airport_kagoshima","yt_86_airport_kagoshima.png","鹿児島空港","airport_volcano"),
("youtube.airport_amakusa","yt_87_airport_amakusa.png","天草空港","airport_islands"),
("youtube.airport_shimojishima","yt_88_airport_shimojishima.png","みやこ下地島空港","airport_tropical"),
("youtube.matsuyama_airport_rnb","yt_89_matsuyama_airport_rnb.png","松山空港【南海放送】","airport_matsuyama"),
("youtube.osaka_nanko","yt_90_osaka_nanko.png","大阪南港","port_osaka"),
("youtube.kobe_port_island","yt_91_kobe_port_island.png","神戸ポートアイランド","port_kobe"),
("youtube.rokko_island","yt_92_rokko_island.png","六甲アイランド","port_rokko"),
("youtube.kabukicho","yt_93_kabukicho.png","東京・新宿 歌舞伎町","city_neon"),
("youtube.umeda_station","yt_94_umeda_station.png","大阪・梅田","city_umeda"),
("youtube.dotonbori","yt_95_dotonbori.png","大阪・道頓堀","city_canal"),
("youtube.namba_station","yt_96_namba_station.png","大阪・なんば駅","city_namba"),
("youtube.shijo_kawaramachi","yt_97_shijo_kawaramachi.png","京都・四条河原町","city_kyoto"),
("youtube.tennoji_station","yt_98_tennoji_station.png","大阪・天王寺駅","city_tennoji"),
("youtube.sannomiya_station","yt_99_sannomiya_station.png","神戸・三ノ宮駅","city_sannomiya"),
("youtube.nishinomiya_kitaguchi","yt_100_nishinomiya_kitaguchi.png","西宮北口駅・西宮車庫","rail_nishinomiya"),
("youtube.shin_osaka_station","yt_101_shin_osaka_station.png","新大阪駅","rail_shinosaka"),
("youtube.shin_kobe_station","yt_102_shin_kobe_station.png","新神戸駅","rail_shinkobe"),
]

W = H = 512

def font_path():
    for p in [
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]:
        if Path(p).exists():
            return p
    raise FileNotFoundError("Japanese font not found")

FONT = font_path()

def fnt(size):
    return ImageFont.truetype(FONT, size)

def gradient(im, top, bottom):
    px = im.load()
    for y in range(H):
        t = y/(H-1)
        c = tuple(int(top[i]*(1-t)+bottom[i]*t) for i in range(3))
        for x in range(W):
            px[x,y] = (*c,255)

def poly(d, pts, fill, outline=None, width=1):
    d.polygon(pts, fill=fill)
    if outline:
        d.line(pts+[pts[0]], fill=outline, width=width, joint="curve")

def mountain(d, base_y=235, peak_x=280, peak_y=95, color="#5c93bf", snow=True):
    poly(d, [(15,base_y),(peak_x,peak_y),(505,base_y)], color)
    if snow:
        poly(d, [(peak_x,peak_y),(peak_x-58,160),(peak_x-25,146),(peak_x,172),(peak_x+28,143),(peak_x+66,164)], "#f4fbff")

def terminal(d, y=276):
    d.rounded_rectangle((75,y,440,y+84), 8, fill="#eaf4f8", outline="#437ca0", width=4)
    d.rectangle((92,y+22,410,y+46), fill="#6ca8c4")
    for x in range(105,400,38):
        d.rectangle((x,y+25,x+24,y+44), fill="#a9d9ec")
    d.rectangle((362,y-68,395,y+4), fill="#eef7f9", outline="#477791", width=3)
    d.rectangle((356,y-78,401,y-61), fill="#4b7894")

def runway(d, y=360):
    d.polygon([(0,y),(512,y-18),(512,455),(0,455)], fill="#6f767c")
    d.line((0,y+42,512,y+10), fill="#f7f1cf", width=5)

def plane(d, x=220, y=210, s=1.0, fighter=False):
    if fighter:
        poly(d, [(x-72*s,y),(x+55*s,y-14*s),(x+82*s,y),(x+52*s,y+10*s),(x-58*s,y+10*s)], "#667c8f")
        poly(d, [(x-5*s,y-4*s),(x+25*s,y-38*s),(x+40*s,y-34*s),(x+23*s,y)], "#4f6577")
        return
    d.ellipse((x-78*s,y-15*s,x+60*s,y+15*s), fill="#f8fbff", outline="#405d78", width=max(1,int(3*s)))
    poly(d, [(x-10*s,y),(x+12*s,y-42*s),(x+35*s,y-38*s),(x+20*s,y)], "#dcebf3")
    poly(d, [(x-16*s,y+2*s),(x+15*s,y+40*s),(x+35*s,y+35*s),(x+20*s,y)], "#dcebf3")
    poly(d, [(x+45*s,y-10*s),(x+56*s,y-34*s),(x+67*s,y-31*s),(x+60*s,y)], "#2660a0")
    d.line((x-50*s,y,x+45*s,y), fill="#2460a5", width=max(1,int(4*s)))

def flower(d, x,y,r=18,color="#ff6388", center="#ffd166"):
    for a in range(0,360,72):
        dx=math.cos(math.radians(a))*r; dy=math.sin(math.radians(a))*r
        d.ellipse((x+dx-r*.55,y+dy-r*.55,x+dx+r*.55,y+dy+r*.55), fill=color)
    d.ellipse((x-r*.35,y-r*.35,x+r*.35,y+r*.35), fill=center)

def title(d, text):
    size = 52 if len(text) <= 8 else 43 if len(text) <= 11 else 36
    font=fnt(size)
    bbox=d.textbbox((0,0),text,font=font,stroke_width=0)
    tw=bbox[2]-bbox[0]
    while tw > 470 and size > 26:
        size-=2; font=fnt(size); bbox=d.textbbox((0,0),text,font=font); tw=bbox[2]-bbox[0]
    x=(512-tw)//2
    d.text((x,18),text,font=font,fill="white",stroke_width=8,stroke_fill="#133a72")
    badge=(170,430,342,492)
    d.rounded_rectangle(badge,16,fill="#f0202e",outline="white",width=4)
    poly(d,[(195,447),(195,477),(222,462)],"white")
    d.text((232,439),"LIVE",font=fnt(38),fill="white")

def water(d,y=280):
    d.rectangle((0,y,512,430),fill="#2fa9d6")
    for yy in range(y+15,425,24):
        d.line((20,yy,490,yy),fill="#8de8f4",width=3)

def city(d, base=310, night=False):
    colors=["#3d5e83","#54769b","#6f8aa4"] if not night else ["#142650","#20356c","#2a417c"]
    xs=[20,75,130,190,250,315,380,440]
    hs=[110,155,95,180,130,165,105,145]
    for i,x in enumerate(xs):
        h=hs[i]
        d.rectangle((x,base-h,x+48,base), fill=colors[i%len(colors)])
        for yy in range(base-h+15,base-8,20):
            for xx in range(x+8,x+42,15):
                d.rectangle((xx,yy,xx+6,yy+7),fill="#ffd65a" if night else "#bfe7f4")

def castle(d,x=380,y=250):
    d.rectangle((x-45,y,x+45,y+55),fill="#f4f3ed",outline="#4b4b49",width=3)
    poly(d,[(x-60,y),(x,y-35),(x+60,y)],"#333b45")
    d.rectangle((x-28,y-18,x+28,y),fill="#f4f3ed")
    poly(d,[(x-42,y-18),(x,y-42),(x+42,y-18)],"#26313c")

def draw_logo(title_text, theme):
    im=Image.new("RGBA",(W,H),(255,255,255,255))
    top=(50,177,244); bottom=(200,241,255)
    if theme=="city_neon": top=(18,25,78); bottom=(87,38,120)
    gradient(im,top,bottom)
    d=ImageDraw.Draw(im)

    # scenery classes
    if theme.startswith("airport_"):
        if theme in {"airport_snow","airport_nebuta"}:
            mountain(d,245,285,98,"#8cb7d5",True)
            d.rectangle((0,235,512,430),fill="#ecf7fb")
        elif theme=="airport_fuji":
            mountain(d,250,345,58,"#4b85b5",True)
        elif theme in {"airport_castle","airport_tulip","airport_fields"}:
            mountain(d,250,280,100,"#5c98bd",True)
        elif theme in {"airport_coast","airport_seto","airport_islands","airport_tropical"}:
            mountain(d,238,290,130,"#518f8b",False)
            water(d,235)
        elif theme=="airport_volcano":
            mountain(d,250,290,105,"#667c74",False)
            d.ellipse((260,78,350,130),fill="#a7afb5")
        else:
            mountain(d,250,290,120,"#6ba084",False)
        terminal(d,280); runway(d,362)
        plane(d,235,210,0.85, theme=="airport_fighter")

        if theme=="airport_sakura":
            for x,y in [(35,250),(65,280),(25,315),(95,330)]: flower(d,x,y,18,"#ff9cbd")
        elif theme=="airport_coast":
            for x,y in [(38,310),(72,335),(28,355)]: flower(d,x,y,19,"#e94656")
        elif theme=="airport_snow":
            d.ellipse((32,315,100,383),fill="white",outline="#acd1e4",width=3); d.ellipse((42,278,91,328),fill="white")
            d.ellipse((58,295,64,301),fill="#333"); d.ellipse((74,295,80,301),fill="#333")
        elif theme=="airport_nebuta":
            d.ellipse((365,260,500,410),fill="#f2b44a",outline="#b92a25",width=8)
            d.arc((390,290,455,345),180,350,fill="#982219",width=7)
        elif theme=="airport_akita":
            d.ellipse((35,295,150,420),fill="#e3a15a",outline="#8b5a34",width=5)
            poly(d,[(55,315),(75,270),(92,318)],"#d98b46"); poly(d,[(105,318),(128,274),(142,326)],"#d98b46")
            for x,y in [(25,250),(60,235),(110,245)]: flower(d,x,y,14,"#f07a36","#8b4a22")
        elif theme=="airport_fields":
            d.rectangle((0,350,512,430),fill="#78b44d")
            for x in range(15,500,35): flower(d,x,390,8,"#f4d43c","#e8a914")
        elif theme=="airport_castle":
            castle(d,400,292)
        elif theme=="airport_shachi":
            poly(d,[(410,315),(458,270),(475,320),(447,355)],"#e4b125",outline="#8f6500",width=4)
        elif theme=="airport_tulip":
            for x in range(18,500,40):
                for y in (365,400):
                    d.ellipse((x,y,x+24,y+30),fill=["#f24c56","#f7bd2e","#e95a98"][((x+y)//10)%3])
        elif theme=="airport_fuji":
            d.rectangle((0,352,512,430),fill="#5ca33f")
            for y in range(360,430,18): d.line((0,y,512,y-10),fill="#357b32",width=7)
        elif theme=="airport_fighter":
            for x in (30,65,100,135): flower(d,x,385,20,"#f2c229","#7a5522")
        elif theme=="airport_seto":
            castle(d,425,310)
        elif theme=="airport_ryoma":
            d.ellipse((40,260,115,345),fill="#4f756f")
            d.rectangle((55,335,103,415),fill="#4f756f")
            for x,y in [(30,365),(75,390),(115,370)]: flower(d,x,y,18,"#e8424f")
        elif theme=="airport_balloons":
            for x,y,c in [(65,175,"#f05655"),(130,135,"#f2bd42"),(385,150,"#5bbbd3"),(440,115,"#ef6aa8")]:
                d.ellipse((x-24,y-32,x+24,y+32),fill=c,outline="white",width=3); d.line((x,y+32,x,y+52),fill="#70523c",width=3)
        elif theme=="airport_volcano":
            for x,y in [(25,360),(75,390),(120,360)]: flower(d,x,y,20,"#e73e4d")
        elif theme=="airport_islands":
            d.arc((310,300,500,430),180,355,fill="#f1f4f5",width=12)
            d.rectangle((415,320,470,410),fill="#f9faf8",outline="#8799a5",width=3); poly(d,[(408,320),(442,280),(478,320)],"#e7edf1")
        elif theme=="airport_tropical":
            for x,y in [(30,350),(70,385),(115,355)]: flower(d,x,y,20,"#e83d50")
            d.ellipse((26,280,100,360),fill="#bb6b34",outline="#6f351c",width=5)
        elif theme=="airport_matsuyama":
            castle(d,390,215)
            for x,y in [(390,375),(435,390),(470,360)]: d.ellipse((x-18,y-18,x+18,y+18),fill="#ef9326",outline="#c56b11",width=3)

    elif theme.startswith("port_"):
        water(d,250); city(d,270,False)
        d.rectangle((0,390,512,430),fill="#547278")
        # ferry
        poly(d,[(35,330),(230,330),(200,380),(65,380)],"#f5f7f9",outline="#244d70",width=4)
        d.rectangle((70,295,185,335),fill="#f5f7f9")
        if theme=="port_osaka":
            for x in (280,330,380):
                d.line((x,180,x,330),fill="#e44d35",width=10); d.line((x,180,x+55,225),fill="#e44d35",width=8)
            d.ellipse((390,195,485,290),outline="#e5574a",width=8)
        elif theme=="port_kobe":
            poly(d,[(275,310),(300,125),(325,310)],"#d74738",outline="#a83228",width=5)
        else:
            d.arc((245,260,380,360),180,360,fill="#e6f1f5",width=12)

    elif theme.startswith("city_"):
        if theme in {"city_neon","city_canal"}:
            city(d,330,True); water(d,330)
            d.rounded_rectangle((110,145,402,195),10,outline="#f24b3d",width=12)
            if theme=="city_canal": d.polygon([(180,385),(345,385),(320,420),(205,420)],fill="#f4c44e")
        elif theme=="city_kyoto":
            d.rectangle((0,280,512,430),fill="#d9b07e")
            for x in range(10,500,80):
                d.rectangle((x,210,x+64,365),fill="#6e4a32"); d.polygon([(x-5,210),(x+32,180),(x+70,210)],fill="#39312d")
            d.rectangle((370,95,392,280),fill="#f3f0e9"); d.ellipse((350,110,412,140),outline="#d34234",width=8)
        else:
            city(d,345,False)
            d.rectangle((0,345,512,430),fill="#d7dedf")
            if theme=="city_tennoji":
                d.rectangle((95,105,145,345),fill="#78a7bd")
                d.ellipse((390,300,465,385),fill="#d7c5a5")
            if theme=="city_sannomiya":
                poly(d,[(80,340),(105,125),(130,340)],"#d74738")
            if theme=="city_umeda":
                d.rectangle((125,220,390,360),fill="#aebcc8",outline="#6c7f8d",width=4)
            if theme=="city_namba":
                d.rectangle((290,190,430,340),fill="#527da3")
        # generic street/greenery
        for x in range(15,500,55):
            d.ellipse((x,325,x+40,365),fill="#4d9b53")

    elif theme.startswith("rail_"):
        d.rectangle((0,330,512,430),fill="#777")
        city(d,300,False)
        for y in (360,390,420): d.line((0,y,512,y),fill="#44372e",width=6)
        if theme=="rail_nishinomiya":
            for x in (70,250):
                d.rounded_rectangle((x,285,x+150,370),12,fill="#7a2247",outline="#e1bac9",width=4)
                d.rectangle((x+15,300,x+55,330),fill="#b5dce8"); d.rectangle((x+85,300,x+130,330),fill="#b5dce8")
            for x,y in [(35,250),(460,270),(420,230)]: flower(d,x,y,14,"#f6a3bf")
        elif theme=="rail_shinosaka":
            # Shinkansen
            d.ellipse((55,330,390,395),fill="#eef6f9",outline="#587a91",width=4)
            poly(d,[(40,362),(100,330),(170,332),(150,390),(60,392)],"#f8fbfc")
            d.line((130,350,355,350),fill="#2f78ad",width=7)
        else:
            mountain(d,260,250,120,"#4f865d",False)
            d.rectangle((80,250,435,330),fill="#edf3f4",outline="#617f8f",width=4)
            for x,y in [(390,365),(430,390),(470,360)]: flower(d,x,y,15,"#7d74d8","#d3d0fa")

    title(d,title_text)
    # rounded transparent corners
    mask=Image.new("L",(W,H),0); md=ImageDraw.Draw(mask); md.rounded_rectangle((0,0,W-1,H-1),36,fill=255)
    out=Image.new("RGBA",(W,H),(255,255,255,0)); out.paste(im,(0,0),mask)
    return out

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    cfg=json.loads(CFG.read_text(encoding="utf-8"))
    by_id={x["id"]:x for x in cfg["general"]}
    changed=False
    for cid,fn,title_text,theme in ITEMS:
        path=OUT/fn
        if not path.exists():
            draw_logo(title_text,theme).save(path,optimize=True)
            changed=True
        item=by_id.get(cid)
        if item is None:
            print(f"warning: config id missing: {cid}")
            continue
        url=RAW+fn
        if item.get("logo") != url:
            item["logo"]=url
            changed=True
    if changed:
        CFG.write_text(json.dumps(cfg,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"generated={len(ITEMS)} changed={changed}")

if __name__ == "__main__":
    main()
