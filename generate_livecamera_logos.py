from __future__ import annotations

import json
import math
import re
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path("logos/youtube")
ROOT.mkdir(parents=True, exist_ok=True)
RAW = "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/youtube/"
SIZE = 512

SOURCE_FILES = [
    Path("general_youtube_sources.json"),
    Path("general_youtube_sources_ports.json"),
    Path("general_youtube_sources_airports.json"),
]
PLAYLIST_FILES = [
    Path("general_youtube.m3u"),
    Path("freewifi"),
    Path("kana_tube.m3u"),
]
SKIP_IDS = {
    "jra.official",
    "youtube.narita_t1",
    "youtube.kobe_waterfront2",
}

FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKjp-Bold.otf",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def choose_font():
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return path
    return FONT_CANDIDATES[-1]


FONT = choose_font()


def font(size):
    try:
        return ImageFont.truetype(FONT, size)
    except Exception:
        return ImageFont.load_default()


def load_items():
    rows = []
    for path in SOURCE_FILES:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for item in data:
            cid = str(item.get("id") or "").strip()
            if not cid or cid in SKIP_IDS or not item.get("enabled", True):
                continue
            rows.append((path, item))
    return rows


def safe_slug(cid):
    slug = cid.split(".", 1)[-1]
    slug = re.sub(r"[^a-zA-Z0-9_]+", "_", slug).strip("_")
    return slug or "youtube"


def kind_for(item):
    cid = str(item.get("id") or "").lower()
    name = str(item.get("name") or "")
    group = str(item.get("group") or "")
    s = (cid + " " + name + " " + group).lower()

    if cid == "youtube.kana_tube":
        return "kana"
    if "空港" in name or "airport" in s or "haneda" in s or "kix" in s or "centrair" in s:
        return "airport"
    if any(k in name for k in ("港", "湾")) or "waterfront" in s:
        return "port"
    if any(k in name for k in ("駅", "鉄道", "線")) or any(k in s for k in ("rail", "osaka_station", "osaka_loop")):
        return "rail"
    if "バス" in name:
        return "bus"
    if "橋" in name or "bridge" in s:
        return "bridge"
    if any(k in name for k in ("神社", "稲荷")):
        return "shrine"
    if "寺" in name:
        return "temple"
    if "城" in name:
        return "castle"
    if any(k in name for k in ("山", "スキー", "ロープウェイ", "皿ヶ嶺", "石鎚")):
        return "mountain"
    if any(k in name for k in ("川", "ダム")):
        return "river"
    if "温泉" in name or "道後" in name:
        return "onsen"
    if "クリーンセンター" in name:
        return "clean"
    if "マンダリン" in name:
        return "baseball"
    if "サービスエリア" in name or "別府町" in name or "本町" in name or "東京ドーム" in name or "向日" in name:
        return "city"
    if any(k in name for k in ("柴犬", "馬", "モンキー", "チンチラ", "ナミビア")) or group == "動物":
        if "馬" in name:
            return "horse"
        if "柴犬" in name:
            return "dog"
        if "モンキー" in name:
            return "monkey"
        return "animal"
    if any(k in name for k in ("海", "しまなみ", "八幡浜", "愛南")):
        return "coast"
    return "city"


def palette_for(kind):
    palettes = {
        "kana": ((255, 246, 249), (255, 58, 116), (33, 164, 235)),
        "airport": ((232, 248, 255), (31, 132, 223), (255, 87, 130)),
        "port": ((231, 249, 255), (19, 143, 211), (250, 116, 34)),
        "rail": ((239, 252, 238), (36, 155, 84), (44, 113, 194)),
        "bus": ((242, 252, 244), (48, 156, 91), (244, 122, 34)),
        "bridge": ((233, 248, 255), (39, 128, 214), (235, 80, 90)),
        "shrine": ((255, 241, 238), (215, 52, 45), (44, 112, 73)),
        "temple": ((247, 243, 232), (117, 77, 47), (56, 122, 77)),
        "castle": ((243, 247, 255), (46, 75, 119), (94, 139, 76)),
        "mountain": ((238, 251, 235), (49, 133, 66), (39, 145, 196)),
        "river": ((235, 249, 255), (31, 136, 207), (53, 144, 79)),
        "onsen": ((255, 244, 232), (211, 102, 47), (52, 124, 171)),
        "clean": ((241, 250, 247), (52, 133, 102), (69, 120, 170)),
        "baseball": ((255, 245, 232), (240, 117, 42), (47, 117, 186)),
        "dog": ((255, 247, 228), (206, 123, 43), (255, 72, 120)),
        "horse": ((255, 248, 230), (150, 91, 48), (56, 160, 89)),
        "monkey": ((255, 244, 228), (168, 91, 49), (67, 143, 77)),
        "animal": ((245, 248, 230), (102, 139, 60), (240, 122, 53)),
        "coast": ((233, 249, 255), (29, 145, 207), (47, 160, 110)),
        "city": ((241, 247, 255), (47, 112, 183), (244, 104, 61)),
    }
    return palettes.get(kind, palettes["city"])


def roundrect(draw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=width)


def draw_sun(draw, x, y, r=28, fill=(255, 193, 41)):
    draw.ellipse((x-r, y-r, x+r, y+r), fill=fill)
    for a in range(0, 360, 45):
        t = math.radians(a)
        x1 = x + math.cos(t) * (r + 10)
        y1 = y + math.sin(t) * (r + 10)
        x2 = x + math.cos(t) * (r + 26)
        y2 = y + math.sin(t) * (r + 26)
        draw.line((x1, y1, x2, y2), fill=fill, width=8)


def draw_cloud(draw, x, y, scale=1.0):
    c = (255, 255, 255)
    draw.ellipse((x, y+18*scale, x+90*scale, y+62*scale), fill=c)
    draw.ellipse((x+18*scale, y, x+72*scale, y+55*scale), fill=c)
    draw.ellipse((x+48*scale, y+8*scale, x+106*scale, y+60*scale), fill=c)


def draw_airplane(draw):
    white=(252,252,252); blue=(35,118,205); dark=(32,47,62)
    draw.polygon([(110,256),(286,214),(416,150),(437,164),(327,244),(434,267),(433,289),(315,280),(276,354),(247,356),(263,281),(119,293)], fill=white, outline=dark)
    draw.polygon([(253,242),(307,222),(278,271),(213,281)], fill=blue)
    draw.line((130,290,427,284), fill=blue, width=8)
    draw.ellipse((360,190,380,204), fill=dark)
    draw.ellipse((390,176,409,191), fill=dark)


def draw_port(draw):
    blue=(31,143,207); navy=(32,73,111); white=(250,250,250)
    draw.rectangle((0,320,512,390), fill=blue)
    for y in (337,366):
        for x in range(20,500,90):
            draw.arc((x,y,x+55,y+18), 10, 170, fill=(255,255,255), width=4)
    draw.polygon([(116,294),(365,294),(336,345),(150,345)], fill=white, outline=navy)
    draw.rectangle((198,240,280,294), fill=white, outline=navy, width=4)
    draw.rectangle((224,207,257,240), fill=white, outline=navy, width=4)
    draw.rectangle((242,188,248,207), fill=navy)


def draw_train(draw):
    dark=(42,54,66); white=(247,249,250); green=(40,154,83)
    roundrect(draw,(110,165,402,352),34,white,dark,8)
    draw.rectangle((132,206,380,274), fill=(54,119,176))
    draw.rectangle((128,292,385,319), fill=green)
    draw.rectangle((160,330,352,350), fill=dark)
    draw.ellipse((145,340,195,390), fill=dark)
    draw.ellipse((317,340,367,390), fill=dark)


def draw_bus(draw):
    dark=(44,60,72); white=(250,250,250); blue=(40,130,196)
    roundrect(draw,(90,190,422,345),24,white,dark,7)
    draw.rectangle((116,215,392,275), fill=(90,165,210))
    draw.rectangle((104,294,408,318), fill=blue)
    draw.ellipse((125,325,180,380), fill=dark)
    draw.ellipse((330,325,385,380), fill=dark)


def draw_bridge(draw):
    blue=(39,130,203); white=(249,249,249)
    draw.rectangle((0,335,512,390), fill=blue)
    draw.line((80,300,432,300), fill=white, width=15)
    draw.line((126,300,180,198), fill=white, width=12)
    draw.line((386,300,332,198), fill=white, width=12)
    draw.line((180,198,332,198), fill=white, width=10)
    for x in range(155,370,36):
        draw.line((x,215,x+22,300), fill=white, width=5)


def draw_shrine(draw):
    red=(211,52,45); dark=(70,49,42)
    draw.rectangle((126,195,156,340), fill=red)
    draw.rectangle((356,195,386,340), fill=red)
    draw.rectangle((102,176,410,202), fill=red)
    draw.polygon([(82,156),(430,156),(405,179),(107,179)], fill=dark)
    draw.rectangle((158,232,354,250), fill=red)
    draw.polygon([(195,340),(317,340),(300,290),(212,290)], fill=(72,105,74))


def draw_temple(draw):
    dark=(73,61,50); red=(137,72,51)
    draw.polygon([(130,235),(382,235),(344,202),(168,202)], fill=dark)
    draw.rectangle((170,235,342,330), fill=(235,221,190), outline=dark, width=5)
    draw.rectangle((205,260,232,330), fill=red)
    draw.rectangle((280,260,307,330), fill=red)
    draw.polygon([(166,202),(346,202),(320,171),(192,171)], fill=dark)


def draw_castle(draw):
    dark=(46,65,82); white=(249,249,246)
    draw.polygon([(145,327),(367,327),(338,284),(174,284)], fill=(135,139,140))
    draw.rectangle((180,226,332,284), fill=white, outline=dark, width=5)
    draw.polygon([(156,226),(356,226),(322,195),(190,195)], fill=dark)
    draw.rectangle((206,176,306,218), fill=white, outline=dark, width=4)
    draw.polygon([(190,176),(322,176),(295,151),(217,151)], fill=dark)


def draw_mountain(draw):
    draw.polygon([(62,350),(190,180),(274,292),(335,215),(455,350)], fill=(51,135,68))
    draw.polygon([(190,180),(158,222),(222,222)], fill=(245,250,248))
    draw.polygon([(335,215),(311,246),(360,246)], fill=(245,250,248))
    draw.rectangle((0,350,512,390), fill=(84,167,77))


def draw_river(draw):
    draw_mountain(draw)
    draw.rectangle((0,330,512,390), fill=(48,155,215))
    draw.polygon([(95,390),(207,332),(273,390)], fill=(226,205,158))
    draw.polygon([(278,390),(367,338),(438,390)], fill=(226,205,158))


def draw_city(draw):
    cols=[(82,270,145,360),(153,230,224,360),(238,255,302,360),(315,205,397,360)]
    colors=[(91,145,191),(62,116,174),(122,164,196),(75,125,180)]
    for box,c in zip(cols,colors):
        draw.rectangle(box,fill=c)
        for y in range(box[1]+18,box[3]-12,30):
            for x in range(box[0]+12,box[2]-10,24):
                draw.rectangle((x,y,x+10,y+13),fill=(230,240,247))
    draw.rectangle((0,360,512,390),fill=(106,112,117))
    draw.line((220,375,292,375),fill=(250,250,250),width=6)


def draw_onsen(draw):
    brown=(157,104,61); dark=(92,65,49); blue=(45,129,185)
    draw.ellipse((125,250,387,350), fill=brown, outline=dark, width=6)
    draw.rectangle((125,286,387,330), fill=brown)
    draw.ellipse((143,260,369,315), fill=(217,161,102))
    for x in (190,256,322):
        draw.arc((x-28,175,x+28,255),0,180,fill=blue,width=8)


def draw_clean(draw):
    draw.rectangle((126,240,386,350), fill=(229,235,238), outline=(68,89,98), width=6)
    draw.rectangle((166,195,208,240), fill=(123,145,151))
    draw.rectangle((290,170,330,240), fill=(123,145,151))
    draw.ellipse((230,250,282,302), outline=(52,139,97), width=10)
    draw.polygon([(256,238),(268,263),(244,263)], fill=(52,139,97))


def draw_baseball(draw):
    draw.ellipse((165,175,347,357), fill=(250,250,247), outline=(70,70,70), width=7)
    draw.arc((172,205,252,330), 290, 70, fill=(218,69,53), width=7)
    draw.arc((260,205,340,330), 110, 250, fill=(218,69,53), width=7)
    draw.rectangle((305,160,326,320), fill=(166,104,52))
    draw.ellipse((284,145,348,175), fill=(242,146,54), outline=(100,75,50), width=4)


def draw_dog(draw):
    brown=(204,126,57); cream=(255,244,219); dark=(65,48,41)
    draw.ellipse((150,170,362,360), fill=brown, outline=dark, width=6)
    draw.polygon([(165,205),(108,142),(202,166)], fill=brown, outline=dark)
    draw.polygon([(347,205),(404,142),(310,166)], fill=brown, outline=dark)
    draw.ellipse((205,245,307,332), fill=cream)
    draw.ellipse((203,228,225,251), fill=dark)
    draw.ellipse((287,228,309,251), fill=dark)
    draw.ellipse((245,267,270,288), fill=dark)


def draw_horse(draw):
    brown=(174,102,56); cream=(254,243,220); dark=(65,47,42)
    draw.ellipse((154,165,358,360), fill=brown, outline=dark, width=6)
    draw.polygon([(168,193),(132,116),(214,171)], fill=brown, outline=dark)
    draw.polygon([(344,193),(380,116),(298,171)], fill=brown, outline=dark)
    draw.polygon([(239,166),(277,166),(298,320),(216,320)], fill=cream)
    draw.ellipse((202,228,224,250), fill=dark)
    draw.ellipse((287,228,309,250), fill=dark)
    draw.ellipse((240,294,272,312), fill=dark)


def draw_monkey(draw):
    brown=(155,91,51); tan=(238,184,126); dark=(63,46,39)
    draw.ellipse((150,166,362,355), fill=brown, outline=dark, width=6)
    draw.ellipse((125,225,190,295), fill=tan, outline=dark, width=5)
    draw.ellipse((322,225,387,295), fill=tan, outline=dark, width=5)
    draw.ellipse((193,214,319,330), fill=tan)
    draw.ellipse((213,238,234,258), fill=dark)
    draw.ellipse((278,238,299,258), fill=dark)


def draw_animal(draw):
    draw.ellipse((156,176,356,356), fill=(210,182,141), outline=(67,57,48), width=6)
    draw.ellipse((128,161,210,237), fill=(210,182,141), outline=(67,57,48), width=5)
    draw.ellipse((302,161,384,237), fill=(210,182,141), outline=(67,57,48), width=5)
    draw.ellipse((210,235,230,255), fill=(62,52,45))
    draw.ellipse((282,235,302,255), fill=(62,52,45))
    draw.ellipse((244,270,270,292), fill=(62,52,45))


def draw_coast(draw):
    draw.rectangle((0,300,512,390), fill=(42,157,214))
    draw.polygon([(0,360),(120,300),(205,345),(308,280),(512,350),(512,390),(0,390)], fill=(52,144,91))
    draw.arc((365,280,470,365), 180, 360, fill=(255,255,255), width=7)


def draw_kana(draw):
    red=(245,47,82); dark=(56,37,39); blue=(48,167,224)
    roundrect(draw,(118,150,394,334),46,red,dark,8)
    draw.rectangle((232,120,246,150), fill=dark)
    draw.rectangle((300,112,314,150), fill=dark)
    draw.ellipse((225,108,252,135), fill=dark)
    draw.ellipse((293,100,320,127), fill=dark)
    draw.polygon([(224,200),(224,286),(310,243)], fill=(255,255,255))
    draw.arc((78,175,150,255),100,260,fill=blue,width=9)
    draw.arc((362,175,434,255),280,80,fill=blue,width=9)


def draw_icon(draw, kind):
    if kind == "kana": draw_kana(draw)
    elif kind == "airport": draw_airplane(draw)
    elif kind == "port": draw_port(draw)
    elif kind == "rail": draw_train(draw)
    elif kind == "bus": draw_bus(draw)
    elif kind == "bridge": draw_bridge(draw)
    elif kind == "shrine": draw_shrine(draw)
    elif kind == "temple": draw_temple(draw)
    elif kind == "castle": draw_castle(draw)
    elif kind == "mountain": draw_mountain(draw)
    elif kind == "river": draw_river(draw)
    elif kind == "onsen": draw_onsen(draw)
    elif kind == "clean": draw_clean(draw)
    elif kind == "baseball": draw_baseball(draw)
    elif kind == "dog": draw_dog(draw)
    elif kind == "horse": draw_horse(draw)
    elif kind == "monkey": draw_monkey(draw)
    elif kind == "animal": draw_animal(draw)
    elif kind == "coast": draw_coast(draw)
    else: draw_city(draw)


def fit_text(draw, text, max_width, start=48, minimum=22):
    for size in range(start, minimum-1, -2):
        f = font(size)
        box = draw.textbbox((0,0), text, font=f)
        if box[2]-box[0] <= max_width:
            return f
    return font(minimum)


def split_title(draw, text, max_width=438):
    # Prefer natural separators; otherwise split around the middle.
    text = text.replace("【", " 【").replace("・", "・")
    for sep in (" ", "・", "／", "/"):
        if sep in text:
            parts = text.split(sep)
            if len(parts) >= 2:
                mid = max(1, len(parts)//2)
                a = sep.join(parts[:mid]).strip()
                b = sep.join(parts[mid:]).strip()
                if a and b:
                    return [a, b]
    f = fit_text(draw, text, max_width, 43, 24)
    if draw.textbbox((0,0), text, font=f)[2] <= max_width:
        return [text]
    cut = max(1, len(text)//2)
    return [text[:cut], text[cut:]]


def render_logo(number, item, filename):
    kind = kind_for(item)
    bg, accent, accent2 = palette_for(kind)
    img = Image.new("RGB", (SIZE, SIZE), bg)
    d = ImageDraw.Draw(img)

    # frame + simple sky decoration
    d.rounded_rectangle((8,8,504,504), radius=34, outline=accent, width=10)
    draw_sun(d, 436, 92, 22, fill=(255,194,40))
    draw_cloud(d, 320, 92, 0.7)

    # number badge
    roundrect(d, (22,22,132,118), 30, accent, (48,40,42), 6)
    num = f"{number:02d}"
    nf = font(58)
    box = d.textbbox((0,0), num, font=nf)
    d.text((77-(box[2]-box[0])/2, 69-(box[3]-box[1])/2-box[1]), num, font=nf, fill="white")

    draw_icon(d, kind)

    # title card
    d.rounded_rectangle((28,374,484,486), radius=28, fill=(255,255,255), outline=(68,49,45), width=7)
    title = str(item.get("name") or item.get("id") or "")
    title = re.sub(r"\s+LIVE$", "", title)
    lines = split_title(d, title)
    if len(lines) == 1:
        f = fit_text(d, lines[0], 424, 48, 24)
        b = d.textbbox((0,0), lines[0], font=f)
        x = 256 - (b[2]-b[0])/2
        y = 430 - (b[3]-b[1])/2 - b[1]
        d.text((x,y), lines[0], font=f, fill=accent)
    else:
        fs=[]
        for line in lines[:2]:
            fs.append(fit_text(d, line, 424, 38, 21))
        ys=[393,438]
        for line,f,y in zip(lines[:2],fs,ys):
            b=d.textbbox((0,0), line, font=f)
            x=256-(b[2]-b[0])/2
            d.text((x,y-b[1]), line, font=f, fill=accent if y==393 else accent2)

    img.save(ROOT / filename, "PNG", optimize=True)


def canonical_mapping(rows):
    mapping = {}
    for idx, (_, item) in enumerate(rows, start=1):
        cid = str(item.get("id") or "").strip()
        filename = f"yt43_{idx:02d}_{safe_slug(cid)}_illustration.png"
        mapping[cid] = (idx, filename)
    return mapping


def patch_sources(mapping):
    for path in SOURCE_FILES:
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        changed = 0
        for item in data:
            cid = str(item.get("id") or "").strip()
            if cid in mapping:
                wanted = RAW + mapping[cid][1]
                if item.get("logo") != wanted:
                    item["logo"] = wanted
                    changed += 1
        if changed:
            path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(path, "logo mappings updated:", changed)


def patch_playlist(path, mapping):
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    out = []
    for line in text.splitlines():
        if line.startswith("#EXTINF:"):
            m = re.search(r'tvg-id="([^"]+)"', line)
            if m and m.group(1) in mapping:
                logo = RAW + mapping[m.group(1)][1]
                if re.search(r'tvg-logo="[^"]*"', line):
                    line = re.sub(r'tvg-logo="[^"]*"', f'tvg-logo="{logo}"', line, count=1)
                else:
                    line = line.replace(" group-title=", f' tvg-logo="{logo}" group-title=', 1)
        out.append(line)
    path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")


def cleanup_old(keep):
    removed = 0
    for p in ROOT.glob("yt43_*.png"):
        if p.name not in keep:
            p.unlink()
            removed += 1
    unified = ROOT / "unified"
    if unified.exists():
        shutil.rmtree(unified)
        print("removed legacy unified directory")
    print("legacy yt43 logos removed:", removed)


def main():
    rows = load_items()
    mapping = canonical_mapping(rows)
    print("canonical YouTube logo count:", len(mapping))

    keep = set()
    for path, item in rows:
        cid = str(item.get("id") or "").strip()
        number, filename = mapping[cid]
        target = ROOT / filename
        if cid == "youtube.kana_tube" and target.exists() and target.stat().st_size > 10000:
            print(f"keep adopted Kana Tube logo: {target}")
        else:
            render_logo(number, item, filename)
            print(f"generated {number:02d}: {cid} -> {filename}")
        keep.add(filename)

    patch_sources(mapping)
    for path in PLAYLIST_FILES:
        patch_playlist(path, mapping)
    cleanup_old(keep)


if __name__ == "__main__":
    main()
