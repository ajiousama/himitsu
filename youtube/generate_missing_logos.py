from pathlib import Path
import json
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
CFG = ROOT / "youtube" / "config.json"
RAW_PREFIX = "https://raw.githubusercontent.com/ajiousama/himitsu/main/"
W = H = 512

PALETTES = {
    "空港": ((24, 113, 196), (205, 235, 255)),
    "愛媛県内ライブカメラ": ((209, 105, 31), (255, 233, 194)),
    "関西": ((36, 70, 130), (218, 229, 247)),
    "橋": ((24, 127, 170), (207, 240, 249)),
    "動物": ((47, 133, 78), (219, 242, 224)),
    "その他LIVE": ((103, 59, 145), (233, 219, 246)),
}

def font_path():
    for p in (
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ):
        if Path(p).exists():
            return p
    raise FileNotFoundError("Japanese font not found")

FONT = font_path()

def fnt(size):
    return ImageFont.truetype(FONT, size)

def fit(draw, text, max_width, start=58, minimum=26):
    size = start
    while size > minimum:
        font = fnt(size)
        if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
            return font
        size -= 2
    return fnt(minimum)

def gradient(im, top, bottom):
    px = im.load()
    for y in range(H):
        t = y / (H - 1)
        color = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        for x in range(W):
            px[x, y] = (*color, 255)

def normalize_name(name):
    for suffix in (" LIVE", " live", " Live"):
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    return name.strip()

def split_name(name):
    name = normalize_name(name)
    if len(name) <= 11:
        return [name]
    for sep in ("・", " ", "【", "［"):
        pos = name.find(sep, max(3, len(name) // 3))
        if 3 <= pos <= len(name) - 3:
            return [name[:pos].strip(), name[pos:].strip()]
    mid = len(name) // 2
    return [name[:mid], name[mid:]]

def is_port_item(item):
    ident = str(item.get("id") or "").lower()
    name = str(item.get("name") or "")
    query = str(item.get("query") or "")
    # Do not mistake "airport" for a seaport. Japanese 港 names and explicit
    # *_port IDs are harbor channels; airport entries keep the airport artwork.
    if "airport" in ident or "空港" in name or "空港" in query:
        return False
    text = f"{ident} {name} {query}".lower()
    return ("港" in text) or ("_port" in ident) or ("harbor" in text) or ("seaport" in text)

def draw_port_scene(d):
    # Harbor illustration: sea, pier, ferry and port crane.
    d.rectangle((28, 240, 484, 408), fill=(34, 132, 181, 255))
    for y in (282, 322, 362):
        d.arc((42, y - 12, 180, y + 18), 0, 180, fill="white", width=5)
        d.arc((190, y - 8, 340, y + 22), 0, 180, fill="white", width=5)
    d.rectangle((300, 274, 460, 314), fill=(88, 92, 98, 255))
    d.rectangle((350, 205, 366, 276), fill=(235, 190, 60, 255))
    d.line((358, 212, 430, 238), fill=(235, 190, 60, 255), width=10)
    d.line((430, 238, 430, 284), fill=(235, 190, 60, 255), width=6)
    d.polygon([(78, 312), (224, 312), (204, 350), (102, 350)], fill=(248, 248, 248, 255))
    d.rectangle((116, 274, 184, 312), fill=(248, 248, 248, 255))
    d.rectangle((130, 282, 144, 294), fill=(56, 95, 132, 255))
    d.rectangle((154, 282, 168, 294), fill=(56, 95, 132, 255))
    d.line((112, 351, 212, 351), fill=(18, 78, 120, 255), width=7)

def draw_logo(item, out):
    top, bottom = PALETTES.get(item.get("group"), ((58, 94, 124), (226, 237, 243)))
    im = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    gradient(im, top, bottom)
    d = ImageDraw.Draw(im)

    # Clean broadcast tile. No pictograms.
    d.rounded_rectangle((12, 12, 500, 500), 34, outline="white", width=8)

    d.rounded_rectangle((28, 30, 484, 144), 24, fill=(255, 255, 255, 242))
    d.rounded_rectangle((48, 52, 170, 124), 18, fill="#ff0000")
    d.polygon([(91, 70), (91, 107), (126, 88)], fill="white")
    d.text((188, 52), "YouTube", font=fnt(48), fill="#111111")

    d.rounded_rectangle((58, 164, 454, 232), 18, fill="#e90016", outline="white", width=4)
    live_font = fnt(44)
    live = "LIVE"
    bb = d.textbbox((0, 0), live, font=live_font)
    d.text(((512 - (bb[2] - bb[0])) // 2, 168), live, font=live_font, fill="white")

    if is_port_item(item):
        draw_port_scene(d)

    lines = split_name(item["name"])
    name_y = 365 if is_port_item(item) else 286
    if len(lines) == 1:
        font = fit(d, lines[0], 450, 62, 30)
        bb = d.textbbox((0, 0), lines[0], font=font)
        d.text(((512 - (bb[2] - bb[0])) // 2, name_y), lines[0], font=font,
               fill="white", stroke_width=5, stroke_fill="#102a43")
    else:
        y = 338 if is_port_item(item) else 260
        for line in lines[:2]:
            font = fit(d, line, 450, 48, 27)
            bb = d.textbbox((0, 0), line, font=font)
            d.text(((512 - (bb[2] - bb[0])) // 2, y), line, font=font,
                   fill="white", stroke_width=5, stroke_fill="#102a43")
            y += 66

    group = item.get("group") or "LIVE"
    if group == "愛媛県内ライブカメラ":
        group = "愛媛 LIVE"
    gf = fit(d, group, 390, 27, 20)
    gb = d.textbbox((0, 0), group, font=gf)
    d.rounded_rectangle((50, 430, 462, 482), 16, fill=(255, 255, 255, 228))
    d.text(((512 - (gb[2] - gb[0])) // 2, 438), group, font=gf, fill="#173b70")

    im.save(out, optimize=True)

def main():
    cfg = json.loads(CFG.read_text(encoding="utf-8"))
    count = 0
    for item in cfg.get("general", []):
        url = (item.get("logo") or "").split("?", 1)[0]
        if not url.startswith(RAW_PREFIX):
            continue
        rel = url[len(RAW_PREFIX):]
        path = ROOT / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            continue
        draw_logo(item, path)
        count += 1
    print(f"generated_missing_logos={count}")

if __name__ == "__main__":
    main()
