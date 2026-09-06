from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path("logos/public_sports/venues")
OUT.mkdir(parents=True, exist_ok=True)
SIZE = 512
BLUE = (8, 82, 165)
DARK = (20, 25, 32)
NIGHT = (8, 49, 112)
YELLOW = (255, 209, 38)

VENUES = [
    ("kiryu","桐生",(23,99,190),True),
    ("toda","戸田",(211,47,47),False),
    ("edogawa","江戸川",(55,158,214),False),
    ("heiwajima","平和島",(31,78,150),False),
    ("tamagawa","多摩川",(45,145,78),False),
    ("hamanako","浜名湖",(63,169,210),False),
    ("gamagori","蒲郡",(23,99,190),True),
    ("tokoname","常滑",(211,47,47),False),
    ("tsu","津",(232,143,28),False),
    ("mikuni","三国",(31,78,150),False),
    ("biwako","びわこ",(63,169,210),False),
    ("suminoe","住之江",(109,76,170),True),
    ("amagasaki","尼崎",(23,99,190),False),
    ("naruto","鳴門",(211,47,47),False),
    ("marugame","まるがめ",(45,145,78),True),
    ("kojima","児島",(23,99,190),False),
    ("miyajima","宮島",(232,143,28),False),
    ("tokuyama","徳山",(63,169,210),False),
    ("shimonoseki","下関",(206,65,130),True),
    ("wakamatsu","若松",(23,99,190),True),
    ("ashiya","芦屋",(45,145,78),False),
    ("fukuoka","福岡",(211,47,47),False),
    ("karatsu","からつ",(23,99,190),False),
    ("omura","大村",(23,99,190),True),
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

def fit(draw, text, maxw, start=126, minimum=58):
    for size in range(start, minimum-1, -2):
        f=font(size)
        b=draw.textbbox((0,0),text,font=f)
        if b[2]-b[0] <= maxw:
            return f
    return font(minimum)

def draw_boatrace_mark(d):
    # Compact official-mark-style header: blue wave disc + BOAT RACE wordmark.
    cx,cy,r=75,84,40
    d.ellipse((cx-r,cy-r,cx+r,cy+r), fill=BLUE)
    for off in (-14,0,14):
        d.arc((cx-30,cy-25+off,cx+30,cy+10+off), 200, 345, fill="white", width=7)
    wf=font(48)
    d.text((132,56),"BOAT RACE",font=wf,fill=BLUE)

def draw_night(d):
    x0,y0,x1,y1=326,126,474,180
    d.rounded_rectangle((x0,y0,x1,y1),radius=20,fill=NIGHT)
    d.ellipse((344,138,370,164),fill=YELLOW)
    d.ellipse((353,134,377,158),fill=NIGHT)
    nf=font(25)
    d.text((382,139),"ナイター",font=nf,fill="white")

def render(slug, name, accent, night):
    im=Image.new("RGB",(SIZE,SIZE),"white")
    d=ImageDraw.Draw(im)
    d.rounded_rectangle((14,14,498,498),radius=54,fill="white",outline=(225,228,233),width=4)
    draw_boatrace_mark(d)
    if night:
        draw_night(d)

    f=fit(d,name,420,126,62)
    b=d.textbbox((0,0),name,font=f)
    tw,th=b[2]-b[0],b[3]-b[1]
    x=(SIZE-tw)/2-b[0]
    y=240-b[1]
    d.text((x,y),name,font=f,fill=DARK)

    # Strong venue-color underline, matching the adopted 24-venue reference sheet.
    d.rounded_rectangle((74,390,438,418),radius=14,fill=accent)
    d.rounded_rectangle((174,438,338,449),radius=6,fill=BLUE)

    out=OUT/f"boat_{slug}.png"
    im.save(out,"PNG",optimize=True)
    print("generated",out)

def main():
    for args in VENUES:
        render(*args)

if __name__=="__main__":
    main()
