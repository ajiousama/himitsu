from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path("logos/ehime_catv")
OUT.mkdir(parents=True, exist_ok=True)
SIZE = 512

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Bold.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def get_font(size):
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def centered(draw, text, y, size, fill, max_width=430):
    f = get_font(size)
    while size > 20:
        box = draw.textbbox((0, 0), text, font=f)
        if box[2] - box[0] <= max_width:
            break
        size -= 2
        f = get_font(size)
    box = draw.textbbox((0, 0), text, font=f)
    x = (SIZE - (box[2] - box[0])) / 2 - box[0]
    draw.text((x, y - box[1]), text, font=f, fill=fill)


def build():
    blue = (31, 104, 190)
    sea = (43, 151, 210)
    green = (66, 137, 79)
    img = Image.new("RGB", (SIZE, SIZE), (239, 249, 255))
    d = ImageDraw.Draw(img)

    d.rectangle((0, 0, SIZE, 28), fill=blue)
    d.rectangle((0, 315, SIZE, SIZE), fill=sea)
    d.polygon([(0, 350), (90, 275), (170, 325), (250, 245), (340, 320), (430, 260), (512, 335), (512, 390), (0, 390)], fill=green)
    for x in range(15, 500, 90):
        d.arc((x, 335, x + 55, 360), 10, 170, fill=(255, 255, 255), width=5)

    centered(d, "愛南", 76, 108, blue, 330)
    centered(d, "ライブカメラ", 205, 58, blue, 430)
    centered(d, "愛媛CATV", 432, 42, (255, 255, 255), 300)

    d.rounded_rectangle((60, 402, 452, 475), radius=22, fill=blue)
    centered(d, "愛媛CATV", 418, 38, (255, 255, 255), 300)

    for name in ("14_ainan_livecam.png", "14_ainan_livecam_v2.png"):
        img.save(OUT / name, "PNG", optimize=True)
        print("generated", OUT / name)


if __name__ == "__main__":
    build()
