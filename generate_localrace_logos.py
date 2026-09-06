from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT=Path("logos/public_sports/venues")
OUT.mkdir(parents=True,exist_ok=True)
SIZE=512
GREEN=(30,112,72)

VENUES=[
("obihiro","帯広","ばんえい十勝",(50,145,75)),
("mombetsu","門別","門別競馬",(35,84,150)),
("morioka","盛岡","盛岡競馬",(48,139,73)),
("mizusawa","水沢","水沢競馬",(42,108,177)),
("urawa","浦和","浦和競馬",(40,132,145)),
("funabashi","船橋","船橋競馬",(48,139,73)),
("oi","大井","大井競馬",(205,48,54)),
("kawasaki","川崎","川崎競馬",(34,139,157)),
("kanazawa","金沢","金沢競馬",(190,132,42)),
("kasamatsu","笠松","笠松競馬",(48,139,73)),
("nagoya","名古屋","名古屋競馬",(205,139,38)),
("sonoda","園田","園田競馬",(204,52,55)),
("himeji","姫路","姫路競馬",(42,108,177)),
("kochi","高知","高知競馬",(204,52,55)),
("saga","佐賀","佐賀競馬",(42,125,165)),
]

FONT_CANDIDATES=[
"/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
"/usr/share/fonts/opentype/noto/NotoSansCJKjp-Bold.otf",
"/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
"/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
def font(size):
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            try:return ImageFont.truetype(p,size)
            except:pass
    return ImageFont.load_default()

def fit(d,text,maxw,start=112,minimum=50):
    for s in range(start,minimum-1,-2):
        f=font(s); b=d.textbbox((0,0),text,font=f)
        if b[2]-b[0]<=maxw:return f
    return font(minimum)

def horse_mark(d,color):
    # Consistent official-like NAR horse/track emblem.
    d.ellipse((138,94,374,286),outline=color,width=13)
    d.arc((155,110,357,270),195,350,fill=color,width=13)
    d.polygon([(178,222),(218,150),(266,126),(326,144),(286,160),(324,202),(270,184),(236,226)],fill=color)
    d.ellipse((270,136,280,146),fill="white")
    d.arc((170,168,345,282),190,340,fill="white",width=8)

def render(slug,short,name,color):
    im=Image.new("RGB",(SIZE,SIZE),"white"); d=ImageDraw.Draw(im)
    d.rounded_rectangle((14,14,498,498),radius=54,fill="white",outline=(222,228,224),width=4)
    # NAR family header
    d.rounded_rectangle((32,32,116,78),radius=16,fill=GREEN)
    nf=font(27); d.text((47,39),"NAR",font=nf,fill="white")
    horse_mark(d,color)

    f=fit(d,name,420,100,48); b=d.textbbox((0,0),name,font=f)
    x=(SIZE-(b[2]-b[0]))/2-b[0]
    d.text((x,300-b[1]),name,font=f,fill=color)

    ef=font(25); eng=f"NAR {slug.upper()} RACECOURSE"
    eb=d.textbbox((0,0),eng,font=ef)
    ex=(SIZE-(eb[2]-eb[0]))/2-eb[0]
    d.text((ex,406-eb[1]),eng,font=ef,fill=(65,70,68))
    d.rounded_rectangle((82,456,430,474),radius=9,fill=color)
    out=OUT/f"localrace_{slug}.png"
    im.save(out,"PNG",optimize=True); print("generated",out)

def main():
    for x in VENUES:render(*x)
if __name__=="__main__":main()
