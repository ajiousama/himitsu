from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path('logos/youtube')
ROOT.mkdir(parents=True, exist_ok=True)
SIZE = 384
FONT = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'

# Dedicated labels for sources that previously shared one generic logo.
LOGOS = {
    'airport_okayama.png': ('OKJ', 'AIRPORT'),
    'airport_hiroshima.png': ('HIJ', 'AIRPORT'),
    'airport_nagasaki.png': ('NGS', 'AIRPORT'),
    'airport_goto.png': ('FUJ', 'AIRPORT'),
    'airport_kumamoto.png': ('KMJ', 'AIRPORT'),
    'airport_oita.png': ('OIT', 'AIRPORT'),
    'airport_miyazaki.png': ('KMI', 'AIRPORT'),
    'airport_amami.png': ('ASJ', 'AIRPORT'),
    'airport_naha.png': ('OKA', 'AIRPORT'),
    'airport_sendai.png': ('SDJ', 'AIRPORT'),
    'airport_hanamaki.png': ('HNA', 'AIRPORT'),
    'airport_yamagata.png': ('GAJ', 'AIRPORT'),
    'airport_fukushima.png': ('FKS', 'AIRPORT'),
    'airport_obihiro.png': ('OBO', 'AIRPORT'),
    'ehime_port_toyo.png': ('TOYO', 'PORT'),
    'ehime_port_hashihama.png': ('HASHI', 'PORT'),
    'ehime_port_misaki.png': ('MISAKI', 'PORT'),
    'ehime_kuma_skiland.png': ('KUMA', 'SKI'),
    'ehime_saragamine.png': ('SARAGA', 'MT.'),
    'ehime_omogo_ishizuchi.png': ('ISHIZU', 'MT.'),
    'ehime_ainan_ebc.png': ('AINAN', 'LIVE'),
    'ehime_dogo_honkan.png': ('DOGO', 'LIVE'),
}


def font_for(draw, text, max_width, start):
    size = start
    while size >= 18:
        try:
            f = ImageFont.truetype(FONT, size)
        except Exception:
            f = ImageFont.load_default()
        b = draw.textbbox((0, 0), text, font=f)
        if b[2] - b[0] <= max_width:
            return f
        size -= 2
    return f


def centered(draw, text, y, font, fill):
    b = draw.textbbox((0, 0), text, font=font)
    x = (SIZE - (b[2] - b[0])) / 2 - b[0]
    draw.text((x, y - b[1]), text, font=font, fill=fill)


def draw_symbol(draw, kind):
    # Simple monochrome symbols keep all icons readable in IPTV players.
    if kind == 'AIRPORT':
        draw.polygon([(192,54),(209,116),(292,145),(292,162),(207,153),(200,213),(184,213),(177,153),(92,162),(92,145),(175,116)], fill='black')
    elif kind == 'PORT':
        draw.rectangle((184,72,200,154), fill='black')
        draw.polygon([(145,119),(192,74),(239,119)], outline='black')
        draw.arc((108,136,276,214), 10, 170, fill='black', width=8)
        draw.arc((108,158,276,236), 10, 170, fill='black', width=8)
    elif kind in {'MT.','SKI'}:
        draw.polygon([(79,190),(153,90),(195,146),(235,96),(310,190)], outline='black')
        draw.line((79,190,310,190), fill='black', width=8)
    else:
        draw.ellipse((143,78,241,176), outline='black', width=9)
        draw.ellipse((177,112,207,142), fill='black')


def build_one(filename, label, kind):
    img = Image.new('RGB', (SIZE, SIZE), 'white')
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((16,16,SIZE-16,SIZE-16), radius=34, outline='black', width=8)
    draw_symbol(draw, kind)
    draw.rounded_rectangle((34,224,SIZE-34,SIZE-34), radius=22, fill='black')

    main = font_for(draw, label, 286, 70)
    sub = font_for(draw, kind, 230, 30)
    centered(draw, label, 237, main, 'white')
    centered(draw, kind, 319, sub, 'white')

    out = ROOT / filename
    img.save(out, 'PNG', optimize=True)
    print('generated', out)


def main():
    for filename, (label, kind) in LOGOS.items():
        build_one(filename, label, kind)


if __name__ == '__main__':
    main()
