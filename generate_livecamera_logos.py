from __future__ import annotations

import json
import subprocess
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont

ROOT = Path('logos/youtube')
ROOT.mkdir(parents=True, exist_ok=True)
SIZE = 418  # Match the existing yt43_01..43 series exactly.
RAW = 'https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/youtube/'

# Keep 01..43 untouched. Every later/add-on YouTube asset continues the same
# yt43 series so FreeWiFi never mixes a second logo family again.
SPECS = [
    ('youtube.maiko_villa_akashi', 'yt43_44_maiko_villa_akashi.png', '舞子ビラ・明石海峡', '交通', 'yt54_44_maiko_villa_akashi.png'),
    ('youtube.tokyo_dome_city', 'yt43_45_tokyo_dome_city.png', '東京ドームシティ', 'その他LIVE', 'yt54_45_tokyo_dome_city.png'),
    ('youtube.shinhotaka_ropeway', 'yt43_46_shinhotaka_ropeway.png', '新穂高ロープウェイ', 'その他LIVE', 'yt54_46_shinhotaka_ropeway.png'),
    ('youtube.airport_okayama', 'yt43_47_airport_okayama.png', '岡山空港', '空港', 'airport_okayama.png'),
    ('youtube.airport_hiroshima', 'yt43_48_airport_hiroshima.png', '広島空港', '空港', 'airport_hiroshima.png'),
    ('youtube.airport_nagasaki', 'yt43_49_airport_nagasaki.png', '長崎空港', '空港', 'airport_nagasaki.png'),
    ('youtube.airport_goto', 'yt43_50_airport_goto.png', '五島つばき空港', '空港', 'airport_goto.png'),
    ('youtube.airport_kumamoto', 'yt43_51_airport_kumamoto.png', '阿蘇くまもと空港', '空港', 'airport_kumamoto.png'),
    ('youtube.airport_oita', 'yt43_52_airport_oita.png', '大分空港', '空港', 'airport_oita.png'),
    ('youtube.airport_miyazaki', 'yt43_53_airport_miyazaki.png', '宮崎空港', '空港', 'airport_miyazaki.png'),
    ('youtube.airport_amami', 'yt43_54_airport_amami.png', '奄美空港', '空港', 'airport_amami.png'),
    ('youtube.airport_naha', 'yt43_55_airport_naha.png', '那覇空港', '空港', 'airport_naha.png'),
    ('youtube.airport_sendai', 'yt43_56_airport_sendai.png', '仙台空港', '空港', 'airport_sendai.png'),
    ('youtube.airport_hanamaki', 'yt43_57_airport_hanamaki.png', '花巻空港', '空港', 'airport_hanamaki.png'),
    ('youtube.airport_yamagata', 'yt43_58_airport_yamagata.png', '山形空港', '空港', 'airport_yamagata.png'),
    ('youtube.airport_fukushima', 'yt43_59_airport_fukushima.png', '福島空港', '空港', 'airport_fukushima.png'),
    ('youtube.airport_obihiro', 'yt43_60_airport_obihiro.png', '帯広空港', '空港', 'airport_obihiro.png'),
    ('youtube.ehime_mishima_kawanoe_port', 'yt43_61_ehime_port_mishima_kawanoe.png', '三島川之江港', '愛媛県内ライブカメラ', 'ehime_port_mishima_kawanoe.png'),
    ('youtube.ehime_toyo_port', 'yt43_62_ehime_port_toyo.png', '東予港', '愛媛県内ライブカメラ', 'ehime_port_toyo.png'),
    ('youtube.ehime_hashihama_port', 'yt43_63_ehime_port_hashihama.png', '波止浜港', '愛媛県内ライブカメラ', 'ehime_port_hashihama.png'),
    ('youtube.ehime_misaki_port', 'yt43_64_ehime_port_misaki.png', '三崎港', '愛媛県内ライブカメラ', 'ehime_port_misaki.png'),
    ('youtube.ehime_misho_port', 'yt43_65_ehime_port_misho.png', '御荘港', '愛媛県内ライブカメラ', 'ehime_port_misho.png'),
    ('youtube.ehime_kuma_skiland', 'yt43_66_ehime_kuma_skiland.png', '久万スキーランド', '愛媛県内ライブカメラ', 'ehime_kuma_skiland.png'),
    ('youtube.ehime_saragamine', 'yt43_67_ehime_saragamine.png', '皿ヶ嶺方面', '愛媛県内ライブカメラ', 'ehime_saragamine.png'),
    ('youtube.ehime_omogo_ishizuchi', 'yt43_68_ehime_omogo_ishizuchi.png', '面河・石鎚山系', '愛媛県内ライブカメラ', 'ehime_omogo_ishizuchi.png'),
    ('youtube.ehime_ainan_ebc', 'yt43_69_ehime_ainan_ebc.png', '愛南町・御荘湾', '愛媛県内ライブカメラ', 'ehime_ainan_ebc.png'),
    ('youtube.ehime_dogo_honkan', 'yt43_70_ehime_dogo_honkan.png', '道後温泉本館', '愛媛県内ライブカメラ', 'ehime_dogo_honkan.png'),
]

SOURCE_FILES = [
    Path('general_youtube_sources.json'),
    Path('general_youtube_sources_airports.json'),
    Path('general_youtube_sources_ports.json'),
]

FONT_CANDIDATES = [
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJKjp-Bold.otf',
    '/usr/share/fonts/opentype/noto/NotoSansJP-Bold.ttf',
    '/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
]


def choose_font() -> str:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            try:
                ImageFont.truetype(path, 30)
                return path
            except Exception:
                pass
    return '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'


FONT = choose_font()


def fit_font(draw: ImageDraw.ImageDraw, text: str, max_width: int, start: int, minimum: int = 22):
    for size in range(start, minimum - 1, -2):
        try:
            font = ImageFont.truetype(FONT, size)
        except Exception:
            font = ImageFont.load_default()
        box = draw.textbbox((0, 0), text, font=font)
        if box[2] - box[0] <= max_width:
            return font
    return font


def load_sources() -> dict[str, dict]:
    found: dict[str, dict] = {}
    for path in SOURCE_FILES:
        if not path.exists():
            continue
        try:
            items = json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            continue
        for item in items:
            tvg = str(item.get('id') or '').strip()
            if tvg:
                found[tvg] = item
    return found


def yt_dlp_thumbnail(item: dict) -> bytes | None:
    targets = []
    page = str(item.get('page') or '').strip()
    query = str(item.get('query') or '').strip()
    if page:
        targets.append(page)
    if query:
        targets.append('ytsearch1:' + query)
    for target in targets:
        cmd = [
            'yt-dlp', '--skip-download', '--dump-single-json', '--no-warnings',
            '--socket-timeout', '10', '--retries', '1', '--playlist-end', '1', target,
        ]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=28)
        except Exception:
            continue
        if p.returncode != 0 or not p.stdout.strip():
            continue
        try:
            info = json.loads(p.stdout.splitlines()[-1])
        except Exception:
            continue
        thumb = str(info.get('thumbnail') or '').strip()
        if not thumb:
            thumbs = info.get('thumbnails') or []
            if thumbs:
                thumb = str(thumbs[-1].get('url') or '').strip()
        if not thumb:
            continue
        try:
            req = urllib.request.Request(thumb, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=12) as r:
                data = r.read(4_000_000)
            if data:
                return data
        except Exception:
            continue
    return None


def crop_square(img: Image.Image) -> Image.Image:
    img = img.convert('RGB')
    w, h = img.size
    side = min(w, h)
    left = (w - side) // 2
    top = (h - side) // 2
    img = img.crop((left, top, left + side, top + side))
    return img.resize((SIZE, SIZE), Image.Resampling.LANCZOS)


def fallback_image(legacy: str) -> Image.Image:
    p = ROOT / legacy
    if p.exists():
        try:
            return crop_square(Image.open(p))
        except Exception:
            pass
    # Neutral fallback, still using the same square/photo-card structure.
    img = Image.new('RGB', (SIZE, SIZE), '#243447')
    d = ImageDraw.Draw(img)
    for y in range(SIZE):
        shade = int(36 + 52 * y / SIZE)
        d.line((0, y, SIZE, y), fill=(shade // 2, shade, min(140, shade + 38)))
    return img


def render_logo(filename: str, title: str, group: str, legacy: str, data: bytes | None):
    if data:
        try:
            base = crop_square(Image.open(BytesIO(data)))
        except Exception:
            base = fallback_image(legacy)
    else:
        base = fallback_image(legacy)

    # The original 01..43 set is compact, image-led and square. Keep the same
    # proportions: full-bleed source image, small YouTube badge, readable name.
    base = ImageEnhance.Contrast(base).enhance(1.05)
    base = ImageEnhance.Color(base).enhance(1.04)
    img = base.convert('RGBA')
    overlay = Image.new('RGBA', img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Top badge.
    draw.rounded_rectangle((16, 15, 160, 61), radius=12, fill=(255, 0, 0, 238))
    draw.polygon([(31, 27), (31, 49), (52, 38)], fill='white')
    badge_font = fit_font(draw, 'YouTube', 92, 24, 18)
    draw.text((61, 22), 'YouTube', font=badge_font, fill='white')

    # Bottom readable title area, without turning the logo into a generic white tile.
    draw.rounded_rectangle((12, 292, SIZE - 12, SIZE - 12), radius=18, fill=(0, 0, 0, 184))
    title_font = fit_font(draw, title, SIZE - 48, 42, 24)
    box = draw.textbbox((0, 0), title, font=title_font)
    tx = (SIZE - (box[2] - box[0])) / 2 - box[0]
    draw.text((tx, 315 - box[1]), title, font=title_font, fill='white')

    group_label = 'LIVE CAMERA' if group not in {'空港'} else 'AIRPORT LIVE'
    sub_font = fit_font(draw, group_label, 240, 21, 17)
    box = draw.textbbox((0, 0), group_label, font=sub_font)
    sx = (SIZE - (box[2] - box[0])) / 2 - box[0]
    draw.text((sx, 371 - box[1]), group_label, font=sub_font, fill=(235, 235, 235, 255))

    out = Image.alpha_composite(img, overlay).convert('RGB')
    out.save(ROOT / filename, 'PNG', optimize=True)
    print('generated', ROOT / filename, 'thumbnail=' + ('yes' if data else 'fallback'))


def patch_source_files():
    logo_by_id = {tvg: RAW + filename for tvg, filename, *_ in SPECS}
    for path in SOURCE_FILES:
        if not path.exists():
            continue
        items = json.loads(path.read_text(encoding='utf-8'))
        changed = 0
        for item in items:
            tvg = str(item.get('id') or '').strip()
            wanted = logo_by_id.get(tvg)
            if wanted and item.get('logo') != wanted:
                item['logo'] = wanted
                changed += 1
        if changed:
            path.write_text(json.dumps(items, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        print(path, 'canonical yt43 logo mappings:', changed)


def main():
    sources = load_sources()
    pending = []
    for tvg, filename, title, group, legacy in SPECS:
        out = ROOT / filename
        if out.exists() and out.stat().st_size > 12_000:
            print('keep existing', out)
            continue
        pending.append((tvg, filename, title, group, legacy))

    thumbs: dict[str, bytes | None] = {}
    if pending:
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs = {pool.submit(yt_dlp_thumbnail, sources.get(tvg, {})): tvg for tvg, *_ in pending}
            for future in as_completed(jobs):
                tvg = jobs[future]
                try:
                    thumbs[tvg] = future.result()
                except Exception:
                    thumbs[tvg] = None

    for tvg, filename, title, group, legacy in pending:
        render_logo(filename, title, group, legacy, thumbs.get(tvg))

    patch_source_files()


if __name__ == '__main__':
    main()
