from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path("logos/public_sports/venues")
OUT.mkdir(parents=True, exist_ok=True)
SIZE = 512

COLORS = {
    "333": (38, 112, 192),
    "400": (55, 150, 85),
    "500": (232, 139, 39),
    "DOME": (112, 78, 170),
    "PIST6": (220, 58, 123),
}

VENUES = [
    ("hakodate","函館","400"),
    ("aomori","青森","400"),
    ("iwakitaira","いわき平","400"),
    ("yahiko","弥彦","400"),
    ("maebashi","前橋","DOME"),
    ("toride","取手","400"),
    ("utsunomiya","宇都宮","500"),
    ("omiya","大宮","500"),
    ("seibuen","西武園","400"),
    ("keiogatsu","京王閣","400"),
    ("tachikawa","立川","400"),
    ("matsudo","松戸","333"),
    ("kawasaki","川崎","400"),
    ("hiratsuka","平塚","400"),
    ("odawara","小田原","333"),
    ("ito","伊東温泉","333"),
    ("shizuoka","静岡","400"),
    ("nagoya","名古屋","400"),
    ("gifu","岐阜","400"),
    ("ogaki","大垣","400"),
    ("toyohashi","豊橋","400"),
    ("toyama","富山","333"),
    ("matsusaka","松阪","400"),
    ("yokkaichi","四日市","400"),
    ("fukui","福井","400"),
    ("nara","奈良","333"),
    ("mukomachi","京都向日町","400"),
    ("wakayama","和歌山","400"),
    ("kishiwada","岸和田","400"),
    ("tamano","玉野","400"),
    ("hiroshima","広島","400"),
    ("hofu","防府","333"),
    ("takamatsu","高松","400"),
    ("komatsushima","小松島","400"),
    ("kochi","高知","500"),
    ("matsuyama","松山","400"),
    ("kokura","小倉","DOME"),
    ("kurume","久留米","400"),
    ("takeo","武雄","400"),
    ("sasebo","佐世保","400"),
    ("beppu","別府","400"),
    ("kumamoto","熊本","400"),
    ("pist6","PIST6","PIST6"),
]

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Bold.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]

def font(size):
    for p in FONT_CANDIDATES:
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()

def fit(draw, text, maxw, start=118, minimum=54):
    for size in range(start, minimum-1, -2):
        f=font(size)
        b=draw.textbbox((0,0), text, font=f)
        if b[2]-b[0] <= maxw:
            return f
    return font(minimum)

def cyclist(draw, color):
    # Simple track + cyclist silhouette matching the Library's illustrated keirin family.
    draw.arc((88,120,424,410), 205, 345, fill=color, width=16)
    draw.ellipse((148,174,190,216), fill=color)
    draw.line((170,210,220,252), fill=color, width=14)
    draw.line((220,252,278,236), fill=color, width=14)
    draw.line((222,252,192,310), fill=color, width=12)
    draw.line((272,236,312,292), fill=color, width=12)
    draw.ellipse((155,285,225,355), outline=color, width=10)
    draw.ellipse((285,275,355,345), outline=color, width=10)
    draw.line((193,320,320,310), fill=color, width=9)
    draw.line((208,252,178,320), fill=color, width=9)
    draw.line((276,236,320,310), fill=color, width=9)

def render(slug, name, bank):
    color=COLORS[bank]
    im=Image.new("RGB",(SIZE,SIZE),"white")
    d=ImageDraw.Draw(im)

    d.rounded_rectangle((14,14,498,498), radius=54, fill="white", outline=color, width=8)
    d.rounded_rectangle((28,28,160,78), radius=18, fill=color)

    badge = "250m" if bank=="PIST6" else ("DOME" if bank=="DOME" else f"{bank}m")
    bf=fit(d,badge,110,30,20)
    bb=d.textbbox((0,0),badge,font=bf)
    d.text((94-(bb[2]-bb[0])/2-bb[0],42-bb[1]),badge,font=bf,fill="white")

    cyclist(d,color)

    title = name
    tf=fit(d,title,420,112,50)
    tb=d.textbbox((0,0),title,font=tf)
    tx=(SIZE-(tb[2]-tb[0]))/2-tb[0]
    d.text((tx,330-tb[1]),title,font=tf,fill=(28,28,32))

    sf=font(28)
    label = "けいりん" if name!="PIST6" else "TIPSTAR DOME CHIBA"
    sb=d.textbbox((0,0),label,font=sf)
    sx=(SIZE-(sb[2]-sb[0]))/2-sb[0]
    d.text((sx,412-sb[1]),label,font=sf,fill=color)

    d.rounded_rectangle((96,458,416,476),radius=9,fill=color)

    out=OUT/f"keirin_{slug}.png"
    im.save(out,"PNG",optimize=True)
    print("generated",out)

def main():
    for item in VENUES:
        render(*item)

if __name__=="__main__":
    main()
