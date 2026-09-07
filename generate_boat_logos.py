from pathlib import Path
import math

from PIL import Image, ImageDraw, ImageFont, ImageFilter

# BOATRACE 24場ロゴ — 2026-09-04 ユーザー承認デザイン
#
# 承認済み見本の共通仕様:
#   ・白い角丸タイル + 薄い影
#   ・上部に青い BOAT RACE マーク / ワードマーク
#   ・中央に場名を大きく青で表示
#   ・下部に青い波 + 白ライン + 赤いスピードライン
#   ・ナイター等の追加バッジは付けない
#
# このスクリプトを唯一の生成元にして、旧「黒文字 + 色別下線 + ナイターバッジ」
# デザインへ戻らないようにする。

OUT = Path("logos/public_sports/venues")
OUT.mkdir(parents=True, exist_ok=True)
SIZE = 512

BLUE = (8, 78, 166)
RED = (235, 10, 28)
PAGE = (248, 248, 248)
BORDER = (226, 228, 232)

VENUES = [
    ("kiryu", "桐生"),
    ("toda", "戸田"),
    ("edogawa", "江戸川"),
    ("heiwajima", "平和島"),
    ("tamagawa", "多摩川"),
    ("hamanako", "浜名湖"),
    ("gamagori", "蒲郡"),
    ("tokoname", "常滑"),
    ("tsu", "津"),
    ("mikuni", "三国"),
    ("biwako", "びわこ"),
    ("suminoe", "住之江"),
    ("amagasaki", "尼崎"),
    ("naruto", "鳴門"),
    ("marugame", "丸亀"),
    ("kojima", "児島"),
    ("miyajima", "宮島"),
    ("tokuyama", "徳山"),
    ("shimonoseki", "下関"),
    ("wakamatsu", "若松"),
    ("ashiya", "芦屋"),
    ("fukuoka", "福岡"),
    ("karatsu", "唐津"),
    ("omura", "大村"),
]

JP_FONTS = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Bold.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]
EN_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-BoldOblique.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _font(size: int, english: bool = False):
    for p in (EN_FONTS if english else JP_FONTS):
        if Path(p).exists():
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _fit(draw, text, max_width=420, start=170, minimum=70):
    for size in range(start, minimum - 1, -2):
        f = _font(size)
        b = draw.textbbox((0, 0), text, font=f)
        if b[2] - b[0] <= max_width:
            return f
    return _font(minimum)


def _curve_points(y_base, amplitude, phase=0.0, left=18, right=494, steps=100):
    pts = []
    for i in range(steps + 1):
        x = left + (right - left) * i / steps
        y = y_base + amplitude * math.sin((x / SIZE) * math.pi * 2 + phase)
        pts.append((x, y))
    return pts


def _draw_boatrace_mark(draw):
    # 承認見本の上部マークを小サイズでも潰れない形で再現。
    cx, cy, r = 75, 82, 38
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=BLUE)

    # 円内の白い流線。右上へ抜ける BOAT RACE マーク風の動きを作る。
    for k in range(6):
        points = []
        for i in range(36):
            x = cx - r + 5 + i * (2 * r - 10) / 35
            rel = (x - (cx - r)) / (2 * r)
            y = cy + 22 - k * 8 - 19 * math.sin(rel * math.pi * 0.96)
            points.append((x, y))
        draw.line(points, fill="white", width=5)

    word = _font(43, english=True)
    draw.text((124, 53), "BOAT RACE", font=word, fill=BLUE)


def _draw_bottom_motif(draw):
    # 赤いスピードライン（承認見本の右上がりの細い舟形アクセント）。
    draw.polygon(
        [(274, 402), (474, 380), (431, 404), (330, 414)],
        fill=RED,
    )

    # 青い波。上端を波形にし、太い白ラインで二層に見せる。
    top = _curve_points(425, 10, phase=0.35)
    draw.polygon(top + [(494, 493), (18, 493)], fill=BLUE)

    white1 = _curve_points(442, 10, phase=0.28)
    draw.line(white1, fill="white", width=12, joint="curve")
    white2 = _curve_points(454, 8, phase=0.18)
    draw.line(white2, fill="white", width=4, joint="curve")


def render(slug: str, name: str):
    # 背景と影
    base = Image.new("RGBA", (SIZE, SIZE), PAGE + (255,))
    shadow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((24, 23, 488, 489), radius=54, fill=(0, 0, 0, 42))
    shadow = shadow.filter(ImageFilter.GaussianBlur(10))
    base = Image.alpha_composite(base, shadow)

    card = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    d = ImageDraw.Draw(card)
    d.rounded_rectangle(
        (18, 16, 494, 492),
        radius=54,
        fill="white",
        outline=BORDER,
        width=2,
    )

    _draw_boatrace_mark(d)

    # 場名は承認見本どおり「大きい青文字」。
    f = _fit(d, name)
    b = d.textbbox((0, 0), name, font=f)
    tw, th = b[2] - b[0], b[3] - b[1]
    x = (SIZE - tw) / 2 - b[0]
    center_y = 270
    y = center_y - th / 2 - b[1]
    d.text((x, y), name, font=f, fill=BLUE)

    _draw_bottom_motif(d)

    image = Image.alpha_composite(base, card).convert("RGB")
    out = OUT / f"boat_{slug}.png"
    image.save(out, "PNG", optimize=True)
    print("generated", out)


def main():
    for slug, name in VENUES:
        render(slug, name)

    files = sorted(OUT.glob("boat_*.png"))
    expected = {f"boat_{slug}.png" for slug, _ in VENUES}
    actual = {p.name for p in files if p.name in expected}
    if actual != expected:
        missing = sorted(expected - actual)
        raise SystemExit(f"BOATRACE logo generation incomplete: {missing}")
    print(f"BOATRACE approved-style logos generated: {len(expected)}")


if __name__ == "__main__":
    main()
