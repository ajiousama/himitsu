from PIL import Image, ImageDraw, ImageFont
from pathlib import Path
import math, re

W = H = 512
WHITE = (255, 255, 255)
BLUE = (18, 91, 190)
ORANGE = (255, 112, 0)

OUT = Path('logos/ehime_catv')
OUT.mkdir(parents=True, exist_ok=True)

FONT_CANDIDATES = [
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
]
FONT = next(p for p in FONT_CANDIDATES if Path(p).exists())

CHANNELS = [
    ('01_town_premium.png', 'たうん', 'プレミアム', 'town'),
    ('02_town_news24.png', 'たうん', 'News24', 'news'),
    ('03_machicam24.png', '街カメ', '24', 'camera'),
    ('04_info.png', 'お知らせ', 'チャンネル', 'info'),
    ('05_program_promo.png', '番組宣伝', 'ch', 'megaphone'),
    ('06_event_premium.png', 'イベント', 'プレミアム', 'star'),
    ('07_event_selection.png', 'イベント', 'セレクション', 'ticket'),
    ('08_ehime_channel.png', 'えひめ', 'チャンネル', 'ehime'),
    ('09_ehime_bousai.png', 'えひめ・防災', 'チャンネル', 'shield'),
    ('10_igo_shogi.png', '囲碁・将棋', 'チャンネル', 'board'),
    ('11_fishing_vision.png', '釣り', 'ビジョン', 'fish'),
    ('12_cnnj.png', 'CNN', 'j', 'globe'),
    ('13_nikkei_cnbc.png', '日経', 'CNBC', 'chart'),
    ('14_ainan_livecam.png', '愛南', 'ライブカメラ', 'camera'),
]

def fit_font(draw, text, maxw, maxh, start=100):
    size = start
    while size >= 18:
        font = ImageFont.truetype(FONT, size)
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= maxw and box[3] - box[1] <= maxh:
            return font
        size -= 2
    return ImageFont.truetype(FONT, 18)

def draw_brand(draw):
    draw.arc((48, 55, 128, 124), 205, 520, fill=ORANGE, width=18)
    draw.ellipse((111, 100, 128, 117), fill=BLUE)
    draw.text((145, 67), '愛媛CATV', font=ImageFont.truetype(FONT, 49), fill=BLUE)

def draw_wave(draw):
    pts = []
    for x in range(0, W + 1, 8):
        y = 438 - int(25 * math.sin((x / W) * math.pi * 0.95))
        pts.append((x, y))
    pts += [(W, H), (0, H)]
    draw.polygon(pts, fill=ORANGE)

    pts = []
    for x in range(0, W + 1, 8):
        y = 463 - int(22 * math.sin((x / W) * math.pi * 0.9))
        pts.append((x, y))
    pts += [(W, H), (0, H)]
    draw.polygon(pts, fill=BLUE)

def draw_camera(draw, x, y, s):
    draw.rounded_rectangle((x, y, x+s*.68, y+s*.42), radius=int(s*.06), fill=BLUE)
    draw.polygon([(x+s*.68,y+s*.08),(x+s*.96,y),(x+s*.96,y+s*.42),(x+s*.68,y+s*.34)], fill=BLUE)
    draw.line((x+s*.30,y+s*.42,x+s*.30,y+s*.70), fill=BLUE, width=max(5,int(s*.08)))
    draw.line((x+s*.13,y+s*.70,x+s*.47,y+s*.70), fill=BLUE, width=max(5,int(s*.08)))

def draw_icon(draw, kind, x, y, s):
    lw = max(5, int(s*.07))
    if kind == 'camera':
        draw_camera(draw, x, y, s)
    elif kind == 'town':
        draw.polygon([(x,y+s*.35),(x+s*.35,y),(x+s*.70,y+s*.35)], fill=BLUE)
        draw.rectangle((x+s*.12,y+s*.35,x+s*.58,y+s*.72), fill=BLUE)
        draw.rectangle((x+s*.29,y+s*.50,x+s*.41,y+s*.72), fill=WHITE)
    elif kind == 'news':
        draw.rounded_rectangle((x,y,x+s*.72,y+s*.72), radius=int(s*.04), outline=BLUE, width=lw)
        for i in range(4):
            yy = y+s*.15+i*s*.12
            draw.line((x+s*.12,yy,x+s*.58,yy), fill=BLUE, width=lw)
    elif kind == 'info':
        draw.ellipse((x,y,x+s*.70,y+s*.70), outline=BLUE, width=lw)
        draw.text((x+s*.22,y+s*.04),'i',font=ImageFont.truetype(FONT,int(s*.52)),fill=BLUE)
    elif kind == 'megaphone':
        draw.polygon([(x,y+s*.22),(x+s*.58,y),(x+s*.58,y+s*.55),(x,y+s*.38)], fill=BLUE)
        draw.rectangle((x+s*.05,y+s*.37,x+s*.22,y+s*.68), fill=BLUE)
    elif kind == 'star':
        cx, cy = x+s*.35, y+s*.34
        pts=[]
        for i in range(10):
            a=-math.pi/2+i*math.pi/5
            r=s*(.34 if i%2==0 else .14)
            pts.append((cx+math.cos(a)*r,cy+math.sin(a)*r))
        draw.polygon(pts, fill=BLUE)
    elif kind == 'ticket':
        draw.rounded_rectangle((x,y+s*.08,x+s*.72,y+s*.58), radius=int(s*.07), fill=BLUE)
        draw.line((x+s*.36,y+s*.12,x+s*.36,y+s*.54), fill=WHITE, width=lw)
    elif kind == 'ehime':
        draw.ellipse((x+s*.05,y+s*.10,x+s*.65,y+s*.65), outline=BLUE, width=lw)
        draw.text((x+s*.17,y+s*.16),'E',font=ImageFont.truetype(FONT,int(s*.34)),fill=BLUE)
    elif kind == 'shield':
        draw.polygon([(x+s*.35,y),(x+s*.68,y+s*.12),(x+s*.60,y+s*.52),(x+s*.35,y+s*.70),(x+s*.10,y+s*.52),(x+s*.02,y+s*.12)], fill=BLUE)
        draw.line((x+s*.18,y+s*.34,x+s*.30,y+s*.46,x+s*.52,y+s*.21), fill=WHITE, width=lw)
    elif kind == 'board':
        draw.rectangle((x,y,x+s*.68,y+s*.68), outline=BLUE, width=lw)
        for i in range(1,4):
            xx=x+i*s*.17; yy=y+i*s*.17
            draw.line((xx,y,xx,y+s*.68), fill=BLUE, width=3)
            draw.line((x,yy,x+s*.68,yy), fill=BLUE, width=3)
        draw.ellipse((x+s*.20,y+s*.20,x+s*.31,y+s*.31), fill=BLUE)
        draw.ellipse((x+s*.40,y+s*.38,x+s*.51,y+s*.49), fill=ORANGE)
    elif kind == 'fish':
        draw.ellipse((x,y+s*.16,x+s*.52,y+s*.52), fill=BLUE)
        draw.polygon([(x+s*.50,y+s*.34),(x+s*.72,y+s*.12),(x+s*.72,y+s*.56)], fill=BLUE)
        draw.ellipse((x+s*.10,y+s*.25,x+s*.16,y+s*.31), fill=WHITE)
    elif kind == 'globe':
        draw.ellipse((x,y,x+s*.68,y+s*.68), outline=BLUE, width=lw)
        draw.ellipse((x+s*.18,y,x+s*.50,y+s*.68), outline=BLUE, width=max(2,lw//2))
        draw.line((x,y+s*.34,x+s*.68,y+s*.34), fill=BLUE, width=max(2,lw//2))
    elif kind == 'chart':
        draw.line((x,y+s*.65,x+s*.70,y+s*.65), fill=BLUE, width=lw)
        draw.line((x,y+s*.65,x,y), fill=BLUE, width=lw)
        draw.line((x+s*.10,y+s*.52,x+s*.28,y+s*.38,x+s*.45,y+s*.47,x+s*.66,y+s*.16), fill=BLUE, width=lw)

def make_logo(main, sub, icon):
    img = Image.new('RGB', (W, H), WHITE)
    draw = ImageDraw.Draw(img)
    draw_brand(draw)
    draw.line((48,145,464,145), fill=(225,232,242), width=2)
    draw_icon(draw, icon, 354, 185, 110)
    main_font = fit_font(draw, main, 290, 110, 94)
    sub_font = fit_font(draw, sub, 385, 105, 82)
    draw.text((48,184), main, font=main_font, fill=BLUE)
    draw.text((48,302), sub, font=sub_font, fill=ORANGE)
    draw_wave(draw)
    return img

for filename, main, sub, icon in CHANNELS:
    make_logo(main, sub, icon).save(OUT / filename, optimize=True)

# Ensure the newly-added Ainan stream uses the new matching logo.
freewifi = Path('freewifi')
if freewifi.exists():
    text = freewifi.read_text(encoding='utf-8-sig')
    logo_url = 'https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/ehime_catv/14_ainan_livecam.png'
    pattern = r'#EXTINF:-1 tvg-id="ecatv\.ainan_livecam"[^\n]*,愛南ライブカメラ'
    replacement = f'#EXTINF:-1 tvg-id="ecatv.ainan_livecam" group-title="愛媛CATV" tvg-logo="{logo_url}",愛南ライブカメラ'
    text2, n = re.subn(pattern, replacement, text, count=1)
    if n:
        freewifi.write_text(text2, encoding='utf-8')

print(f'Generated {len(CHANNELS)} unified Ehime CATV logos')
