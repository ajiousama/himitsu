from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT=Path("logos/public_sports/venues")
OUT.mkdir(parents=True,exist_ok=True)
SIZE=512

VENUES=[
("kawaguchi","川口",(28,105,180)),
("isesaki","伊勢崎",(45,145,82)),
("hamamatsu","浜松",(215,62,57)),
("sanyo","山陽",(230,137,35)),
("iizuka","飯塚",(105,76,170)),
]

FONTS=[
"/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
"/usr/share/fonts/opentype/noto/NotoSansCJKjp-Bold.otf",
"/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
"/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
def font(n):
    for p in FONTS:
        if Path(p).exists():
            try:return ImageFont.truetype(p,n)
            except:pass
    return ImageFont.load_default()

def fit(d,t,w,start=116,minimum=52):
    for n in range(start,minimum-1,-2):
        f=font(n); b=d.textbbox((0,0),t,font=f)
        if b[2]-b[0]<=w:return f
    return font(minimum)

def bike(d,c):
    # Oval race track
    d.ellipse((88,102,424,320),outline=(210,214,218),width=16)
    d.arc((88,102,424,320),205,350,fill=c,width=16)
    # Auto-race motorcycle/rider silhouette
    d.ellipse((150,224,218,292),outline=c,width=11)
    d.ellipse((300,224,368,292),outline=c,width=11)
    d.line((184,257,245,225),fill=c,width=13)
    d.line((245,225,326,258),fill=c,width=13)
    d.line((238,226,278,181),fill=c,width=13)
    d.line((278,181,320,211),fill=c,width=13)
    d.ellipse((253,139,292,178),fill=c)
    d.line((270,176,238,220),fill=c,width=15)
    d.line((270,178,315,203),fill=c,width=14)
    d.line((238,220,205,260),fill=c,width=11)
    d.line((315,203,334,258),fill=c,width=10)

def render(slug,name,c):
    im=Image.new("RGB",(SIZE,SIZE),"white"); d=ImageDraw.Draw(im)
    d.rounded_rectangle((14,14,498,498),radius=54,fill="white",outline=c,width=8)

    # Unified AUTORACE header
    d.rounded_rectangle((32,30,220,78),radius=18,fill=(32,36,42))
    hf=font(27)
    d.text((49,39),"AUTO RACE",font=hf,fill="white")
    d.rounded_rectangle((232,30,480,78),radius=18,fill=c)
    sf=font(22)
    d.text((255,42),"MOTORCYCLE SPEEDWAY",font=sf,fill="white")

    bike(d,c)

    tf=fit(d,name,410,112,54); b=d.textbbox((0,0),name,font=tf)
    x=(SIZE-(b[2]-b[0]))/2-b[0]
    d.text((x,326-b[1]),name,font=tf,fill=(28,30,34))

    jf=font(34); label="オートレース"
    jb=d.textbbox((0,0),label,font=jf)
    jx=(SIZE-(jb[2]-jb[0]))/2-jb[0]
    d.text((jx,414-jb[1]),label,font=jf,fill=c)
    d.rounded_rectangle((86,461,426,479),radius=9,fill=c)

    out=OUT/f"autorace_{slug}.png"
    im.save(out,"PNG",optimize=True)
    print("generated",out)

def main():
    for x in VENUES:render(*x)
if __name__=="__main__":main()
