from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path('logos/youtube')
ROOT.mkdir(parents=True, exist_ok=True)
SIZE = 512
RED = '#ff0033'
TEXT = '#111111'
MUTED = '#555555'
BORDER = '#e5e7eb'

# Keep the early numbered YouTube logos (かなチューブ / コノド etc.) untouched.
# Regenerate only the later/add-on assets in one matching, readable YouTube-LIVE style.
LOGOS = {
    'airport_okayama.png': ('岡山空港', 'AIRPORT LIVE'),
    'airport_hiroshima.png': ('広島空港', 'AIRPORT LIVE'),
    'airport_nagasaki.png': ('長崎空港', 'AIRPORT LIVE'),
    'airport_goto.png': ('五島つばき空港', 'AIRPORT LIVE'),
    'airport_kumamoto.png': ('阿蘇くまもと空港', 'AIRPORT LIVE'),
    'airport_oita.png': ('大分空港', 'AIRPORT LIVE'),
    'airport_miyazaki.png': ('宮崎空港', 'AIRPORT LIVE'),
    'airport_amami.png': ('奄美空港', 'AIRPORT LIVE'),
    'airport_naha.png': ('那覇空港', 'AIRPORT LIVE'),
    'airport_sendai.png': ('仙台空港', 'AIRPORT LIVE'),
    'airport_hanamaki.png': ('花巻空港', 'AIRPORT LIVE'),
    'airport_yamagata.png': ('山形空港', 'AIRPORT LIVE'),
    'airport_fukushima.png': ('福島空港', 'AIRPORT LIVE'),
    'airport_obihiro.png': ('帯広空港', 'AIRPORT LIVE'),
    'ehime_port_mishima_kawanoe.png': ('三島川之江港', 'PORT LIVE'),
    'ehime_port_toyo.png': ('東予港', 'PORT LIVE'),
    'ehime_port_hashihama.png': ('波止浜港', 'PORT LIVE'),
    'ehime_port_misaki.png': ('三崎港', 'PORT LIVE'),
    'ehime_port_misho.png': ('御荘港', 'PORT LIVE'),
    'ehime_kuma_skiland.png': ('久万スキーランド', 'EHIME LIVE'),
    'ehime_saragamine.png': ('皿ヶ嶺方面', 'EHIME LIVE'),
    'ehime_omogo_ishizuchi.png': ('面河・石鎚山系', 'EHIME LIVE'),
    'ehime_ainan_ebc.png': ('愛南町・御荘湾', 'EHIME LIVE'),
    'ehime_dogo_honkan.png': ('道後温泉本館', 'EHIME LIVE'),
    'yt54_44_maiko_villa_akashi.png': ('舞子ビラ・明石海峡', 'LIVE CAMERA'),
    'yt54_45_tokyo_dome_city.png': ('東京ドームシティ', 'LIVE CAMERA'),
    'yt54_46_shinhotaka_ropeway.png': ('新穂高ロープウェイ', 'LIVE CAMERA'),
}

FONT_CANDIDATES = [
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJKjp-Bold.otf',
    '/usr/share/fonts/opentype/noto/NotoSansJP-Bold.ttf',
    '/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
]


def choose_font():
    for path in FONT_CANDIDATES:
        p = Path(path)
        if not p.exists():
            continue
        try:
            ImageFont.truetype(str(p), 32)
            return str(p)
        except Exception:
            pass
    return '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'


FONT = choose_font()


def font_for(draw, text, max_width, start, minimum=22):
    size = start
    while size >= minimum:
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


def title_lines(title):
    # Prefer one strong line; split only the longest labels so the venue/place name stays large.
    if title == '舞子ビラ・明石海峡':
        return ['舞子ビラ', '明石海峡']
    if title == '新穂高ロープウェイ':
        return ['新穂高', 'ロープウェイ']
    return [title]


def build_one(filename, title, category):
    img = Image.new('RGB', (SIZE, SIZE), 'white')
    draw = ImageDraw.Draw(img)

    # Same visual language as the early YouTube set: white tile, red LIVE header,
    # large plain name, thin red accent, no busy pictograms or black blocks.
    draw.rounded_rectangle((16, 16, SIZE - 16, SIZE - 16), radius=46,
                           outline=BORDER, width=8, fill='white')
    draw.rounded_rectangle((44, 54, SIZE - 44, 140), radius=22, fill=RED)
    draw.polygon([(112, 76), (112, 118), (156, 97)], fill='white')
    live_font = font_for(draw, 'YouTube LIVE', 270, 38, 28)
    centered(draw, 'YouTube LIVE', 81, live_font, 'white')

    lines = title_lines(title)
    if len(lines) == 1:
        main = font_for(draw, lines[0], 420, 70, 36)
        centered(draw, lines[0], 235, main, TEXT)
    else:
        main = font_for(draw, max(lines, key=len), 390, 64, 34)
        centered(draw, lines[0], 205, main, TEXT)
        centered(draw, lines[1], 278, main, TEXT)

    draw.rectangle((88, 350, SIZE - 88, 354), fill=RED)
    sub = font_for(draw, category, 300, 30, 22)
    centered(draw, category, 390, sub, MUTED)

    out = ROOT / filename
    img.save(out, 'PNG', optimize=True)
    print('generated', out)


def main():
    print('logo font:', FONT)
    for filename, (title, category) in LOGOS.items():
        build_one(filename, title, category)


if __name__ == '__main__':
    main()
