from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance

ROOT = Path('logos/youtube')
ROOT.mkdir(parents=True, exist_ok=True)
BASE = ROOT / 'youtube_live_camera_default.png'

# Dedicated labels for sources that previously shared the generic live-camera logo.
# Airport labels use IATA codes so they render reliably on GitHub Actions without
# depending on Japanese fonts. Ehime live cameras use short Roman labels.
# Keep this list synchronized with the supplemental airport/port source files.
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


def fit_font(draw, text, max_width, start_size, font_path=None):
    size = start_size
    while size >= 18:
        try:
            font = ImageFont.truetype(font_path or '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf', size)
        except Exception:
            font = ImageFont.load_default()
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= max_width:
            return font
        size -= 2
    return font


def build_one(filename, label, kind):
    if not BASE.exists():
        raise FileNotFoundError(BASE)
    img = Image.open(BASE).convert('RGBA')
    # Keep the existing project look, while slightly dimming the source image so
    # the dedicated code is readable at IPTV icon size.
    rgb = ImageEnhance.Brightness(img.convert('RGB')).enhance(0.72)
    img = rgb.convert('RGBA')
    w, h = img.size
    draw = ImageDraw.Draw(img, 'RGBA')

    pad = max(12, w // 24)
    panel_top = int(h * 0.58)
    draw.rounded_rectangle(
        (pad, panel_top, w - pad, h - pad),
        radius=max(12, w // 28),
        fill=(0, 0, 0, 188),
        outline=(255, 255, 255, 220),
        width=max(2, w // 110),
    )

    main = fit_font(draw, label, int(w * 0.78), max(42, int(h * 0.19)))
    sub = fit_font(draw, kind, int(w * 0.72), max(20, int(h * 0.075)))

    mb = draw.textbbox((0, 0), label, font=main)
    sw = mb[2] - mb[0]
    sh = mb[3] - mb[1]
    y = panel_top + max(4, int((h - pad - panel_top) * 0.16))
    draw.text(((w - sw) / 2, y - mb[1]), label, font=main, fill=(255, 255, 255, 255))

    sb = draw.textbbox((0, 0), kind, font=sub)
    ssw = sb[2] - sb[0]
    sy = min(h - pad - (sb[3] - sb[1]) - 5, y + sh + max(4, h // 55))
    draw.text(((w - ssw) / 2, sy - sb[1]), kind, font=sub, fill=(240, 240, 240, 255))

    out = ROOT / filename
    img.convert('RGB').save(out, 'PNG', optimize=True)
    print('generated', out)


def main():
    for filename, (label, kind) in LOGOS.items():
        build_one(filename, label, kind)


if __name__ == '__main__':
    main()
