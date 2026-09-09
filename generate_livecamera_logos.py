from __future__ import annotations

import json
import re
import subprocess
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, PngImagePlugin

ROOT = Path('logos/youtube')
ROOT.mkdir(parents=True, exist_ok=True)
SIZE = 418
RAW = 'https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/youtube/'

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
PLAYLIST_FILES = [Path('freewifi'), Path('general_youtube.m3u')]

FONT_CANDIDATES = [
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJKjp-Bold.otf',
    '/usr/share/fonts/opentype/noto/NotoSansJP-Bold.ttf',
    '/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
]

STYLE_KEY = 'freewifi_logo_style'
STYLE_VALUE = 'yt43-classic-card-v3'
STYLE_ENFORCE_FROM = 47


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


def fit_font(draw: ImageDraw.ImageDraw, text: str, max_width: int, start: int, minimum: int = 20):
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


def playlist_video_ids() -> dict[str, str]:
    ids: dict[str, str] = {}
    for path in PLAYLIST_FILES:
        if not path.exists():
            continue
        current = None
        text = path.read_text(encoding='utf-8-sig', errors='replace')
        for line in text.splitlines():
            if line.startswith('#EXTINF:'):
                m = re.search(r'tvg-id="([^"]+)"', line)
                current = m.group(1) if m else None
                continue
            if current and line and not line.startswith('#'):
                m = re.search(r'/id/([A-Za-z0-9_-]{11})(?:[./])', line)
                if m:
                    ids.setdefault(current, m.group(1))
                current = None
    return ids


def fetch_url_bytes(url: str, limit: int = 4_000_000) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=12) as r:
            data = r.read(limit)
        if not data:
            return None
        with Image.open(BytesIO(data)) as test:
            if test.width < 200 or test.height < 120:
                return None
        return data
    except Exception:
        return None


def direct_youtube_thumbnail(video_id: str | None) -> bytes | None:
    if not video_id:
        return None
    for name in ('maxresdefault.jpg', 'sddefault.jpg', 'hqdefault.jpg'):
        data = fetch_url_bytes(f'https://i.ytimg.com/vi/{video_id}/{name}')
        if data:
            return data
    return None


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
        if thumb:
            data = fetch_url_bytes(thumb)
            if data:
                return data
    return None


def thumbnail_for(tvg: str, item: dict, live_ids: dict[str, str]) -> bytes | None:
    data = direct_youtube_thumbnail(live_ids.get(tvg))
    if data:
        return data
    return yt_dlp_thumbnail(item)


def crop_to_size(img: Image.Image, width: int, height: int) -> Image.Image:
    img = img.convert('RGB')
    src_ratio = img.width / img.height
    dst_ratio = width / height
    if src_ratio > dst_ratio:
        new_h = height
        new_w = round(new_h * src_ratio)
    else:
        new_w = width
        new_h = round(new_w / src_ratio)
    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
    left = max(0, (new_w - width) // 2)
    top = max(0, (new_h - height) // 2)
    return img.crop((left, top, left + width, top + height))


def fallback_image(legacy: str) -> Image.Image:
    p = ROOT / legacy
    if p.exists():
        try:
            return Image.open(p).convert('RGB')
        except Exception:
            pass
    img = Image.new('RGB', (SIZE, SIZE), (42, 57, 72))
    d = ImageDraw.Draw(img)
    for y in range(SIZE):
        shade = int(42 + 45 * y / SIZE)
        d.line((0, y, SIZE, y), fill=(shade // 2, shade, min(145, shade + 38)))
    return img


def spec_number(filename: str) -> int:
    try:
        return int(filename.split('_', 2)[1])
    except Exception:
        return 999


def has_current_style(path: Path) -> bool:
    try:
        with Image.open(path) as img:
            return img.info.get(STYLE_KEY) == STYLE_VALUE
    except Exception:
        return False


def should_keep_existing(path: Path, filename: str) -> bool:
    if not path.exists() or path.stat().st_size <= 12_000:
        return False
    if spec_number(filename) < STYLE_ENFORCE_FROM:
        return True
    return has_current_style(path)


def render_logo(filename: str, title: str, group: str, legacy: str, data: bytes | None):
    header_h = 94
    photo_h = SIZE - header_h

    if data:
        try:
            photo_src = Image.open(BytesIO(data)).convert('RGB')
        except Exception:
            photo_src = fallback_image(legacy)
    else:
        photo_src = fallback_image(legacy)

    photo = crop_to_size(photo_src, SIZE, photo_h)
    photo = ImageEnhance.Contrast(photo).enhance(1.03)
    photo = ImageEnhance.Color(photo).enhance(1.02)

    out = Image.new('RGB', (SIZE, SIZE), 'white')
    out.paste(photo, (0, header_h))
    draw = ImageDraw.Draw(out)

    draw.rectangle((1, 1, SIZE - 2, SIZE - 2), outline=(214, 214, 214), width=3)

    title_font = fit_font(draw, title, SIZE - 28, 46, 24)
    box = draw.textbbox((0, 0), title, font=title_font)
    tx = (SIZE - (box[2] - box[0])) / 2 - box[0]
    ty = (header_h - (box[3] - box[1])) / 2 - box[1] - 1
    draw.text((tx, ty), title, font=title_font, fill=(211, 40, 34))

    badge_w, badge_h = 112, 46
    x1, y1 = SIZE - badge_w - 10, SIZE - badge_h - 10
    x2, y2 = SIZE - 10, SIZE - 10
    draw.rounded_rectangle((x1, y1, x2, y2), radius=7, fill=(229, 25, 25))
    draw.rounded_rectangle((x1 + 7, y1 + 8, x1 + 39, y1 + 38), radius=6, fill='white')
    draw.polygon([(x1 + 18, y1 + 14), (x1 + 18, y1 + 32), (x1 + 31, y1 + 23)], fill=(229, 25, 25))
    live_font = fit_font(draw, 'LIVE', 60, 25, 18)
    live_box = draw.textbbox((0, 0), 'LIVE', font=live_font)
    draw.text((x1 + 45, y1 + (badge_h - (live_box[3] - live_box[1])) / 2 - live_box[1] - 1),
              'LIVE', font=live_font, fill='white')

    pnginfo = PngImagePlugin.PngInfo()
    pnginfo.add_text(STYLE_KEY, STYLE_VALUE)
    out.save(ROOT / filename, 'PNG', optimize=True, pnginfo=pnginfo)
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
            path.write_text(
                json.dumps(items, ensure_ascii=False, separators=(',', ':')),
                encoding='utf-8',
            )
        print(path, 'canonical yt43 logo mappings:', changed)


def render_ehime_catv_ainan():
    outdir = Path('logos/ehime_catv')
    outdir.mkdir(parents=True, exist_ok=True)
    size = 512
    img = Image.new('RGB', (size, size), 'white')
    d = ImageDraw.Draw(img)
    blue = (31, 104, 190)

    d.rectangle((0, 0, size, 29), fill=blue)

    def centered(text, top, font, fill):
        box = d.textbbox((0, 0), text, font=font)
        x = (size - (box[2] - box[0])) / 2 - box[0]
        d.text((x, top - box[1]), text, font=font, fill=fill)

    centered('愛南', 90, fit_font(d, '愛南', 320, 116, 80), blue)
    centered('ライブカメラ', 248, fit_font(d, 'ライブカメラ', 390, 64, 42), blue)
    centered('愛媛CATV', 421, fit_font(d, '愛媛CATV', 220, 39, 30), blue)
    d.rectangle((58, 478, 454, 487), fill=blue)

    for name in ('14_ainan_livecam.png', '14_ainan_livecam_v2.png'):
        img.save(outdir / name, 'PNG', optimize=True)
        print('generated', outdir / name)


def main():
    sources = load_sources()
    live_ids = playlist_video_ids()
    print('live thumbnail video IDs:', len(live_ids))
    pending = []

    for tvg, filename, title, group, legacy in SPECS:
        out = ROOT / filename
        if should_keep_existing(out, filename):
            print('keep existing', out)
            continue
        pending.append((tvg, filename, title, group, legacy))

    thumbs: dict[str, bytes | None] = {}
    if pending:
        with ThreadPoolExecutor(max_workers=4) as pool:
            jobs = {
                pool.submit(thumbnail_for, tvg, sources.get(tvg, {}), live_ids): tvg
                for tvg, *_ in pending
            }
            for future in as_completed(jobs):
                tvg = jobs[future]
                try:
                    thumbs[tvg] = future.result()
                except Exception:
                    thumbs[tvg] = None

    for tvg, filename, title, group, legacy in pending:
        render_logo(filename, title, group, legacy, thumbs.get(tvg))

    patch_source_files()
    render_ehime_catv_ainan()


if __name__ == '__main__':
    main()
