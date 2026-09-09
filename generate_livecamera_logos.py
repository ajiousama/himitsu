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

# 44-70 are intentionally written to new v4 filenames. APTV is very aggressive
# about image caching, so changing only a query string was not enough on some devices.
SPECS = [
    ('youtube.maiko_villa_akashi', 'yt43_44_maiko_villa_akashi_v4.png', '舞子ビラ・明石海峡', '交通'),
    ('youtube.tokyo_dome_city', 'yt43_45_tokyo_dome_city_v4.png', '東京ドームシティ', 'その他LIVE'),
    ('youtube.shinhotaka_ropeway', 'yt43_46_shinhotaka_ropeway_v4.png', '新穂高ロープウェイ', 'その他LIVE'),
    ('youtube.airport_okayama', 'yt43_47_airport_okayama_v4.png', '岡山空港', '空港'),
    ('youtube.airport_hiroshima', 'yt43_48_airport_hiroshima_v4.png', '広島空港', '空港'),
    ('youtube.airport_nagasaki', 'yt43_49_airport_nagasaki_v4.png', '長崎空港', '空港'),
    ('youtube.airport_goto', 'yt43_50_airport_goto_v4.png', '五島つばき空港', '空港'),
    ('youtube.airport_kumamoto', 'yt43_51_airport_kumamoto_v4.png', '阿蘇くまもと空港', '空港'),
    ('youtube.airport_oita', 'yt43_52_airport_oita_v4.png', '大分空港', '空港'),
    ('youtube.airport_miyazaki', 'yt43_53_airport_miyazaki_v4.png', '宮崎空港', '空港'),
    ('youtube.airport_amami', 'yt43_54_airport_amami_v4.png', '奄美空港', '空港'),
    ('youtube.airport_naha', 'yt43_55_airport_naha_v4.png', '那覇空港', '空港'),
    ('youtube.airport_sendai', 'yt43_56_airport_sendai_v4.png', '仙台空港', '空港'),
    ('youtube.airport_hanamaki', 'yt43_57_airport_hanamaki_v4.png', '花巻空港', '空港'),
    ('youtube.airport_yamagata', 'yt43_58_airport_yamagata_v4.png', '山形空港', '空港'),
    ('youtube.airport_fukushima', 'yt43_59_airport_fukushima_v4.png', '福島空港', '空港'),
    ('youtube.airport_obihiro', 'yt43_60_airport_obihiro_v4.png', '帯広空港', '空港'),
    ('youtube.ehime_mishima_kawanoe_port', 'yt43_61_ehime_port_mishima_kawanoe_v4.png', '三島川之江港', '愛媛県内ライブカメラ'),
    ('youtube.ehime_toyo_port', 'yt43_62_ehime_port_toyo_v4.png', '東予港', '愛媛県内ライブカメラ'),
    ('youtube.ehime_hashihama_port', 'yt43_63_ehime_port_hashihama_v4.png', '波止浜港', '愛媛県内ライブカメラ'),
    ('youtube.ehime_misaki_port', 'yt43_64_ehime_port_misaki_v4.png', '三崎港', '愛媛県内ライブカメラ'),
    ('youtube.ehime_misho_port', 'yt43_65_ehime_port_misho_v4.png', '御荘港', '愛媛県内ライブカメラ'),
    ('youtube.ehime_kuma_skiland', 'yt43_66_ehime_kuma_skiland_v4.png', '久万スキーランド', '愛媛県内ライブカメラ'),
    ('youtube.ehime_saragamine', 'yt43_67_ehime_saragamine_v4.png', '皿ヶ嶺方面', '愛媛県内ライブカメラ'),
    ('youtube.ehime_omogo_ishizuchi', 'yt43_68_ehime_omogo_ishizuchi_v4.png', '面河・石鎚山系', '愛媛県内ライブカメラ'),
    ('youtube.ehime_ainan_ebc', 'yt43_69_ehime_ainan_ebc_v4.png', '愛南町・御荘湾', '愛媛県内ライブカメラ'),
    ('youtube.ehime_dogo_honkan', 'yt43_70_ehime_dogo_honkan_v4.png', '道後温泉本館', '愛媛県内ライブカメラ'),
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
STYLE_VALUE = 'yt43-photo-card-v4'


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
    font = ImageFont.load_default()
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


def extract_video_id(value: str) -> str | None:
    if not value:
        return None
    patterns = (
        r'(?:watch\?v=|youtu\.be/)([A-Za-z0-9_-]{11})',
        r'/id/([A-Za-z0-9_-]{11})(?:[./?]|$)',
        r'/embed/([A-Za-z0-9_-]{11})(?:[/?]|$)',
    )
    for pattern in patterns:
        m = re.search(pattern, value)
        if m:
            return m.group(1)
    return None


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
                vid = extract_video_id(line)
                if vid:
                    ids.setdefault(current, vid)
                current = None
    return ids


def fetch_url_bytes(url: str, limit: int = 5_000_000) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read(limit)
        if not data:
            return None
        with Image.open(BytesIO(data)) as test:
            if test.width < 320 or test.height < 180:
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


def candidate_score(info: dict, query: str) -> int:
    title = str(info.get('title') or '')
    status = str(info.get('live_status') or '')
    score = 0
    if status == 'is_live':
        score += 100
    elif status in {'post_live', 'was_live'}:
        score += 60
    if 'ライブカメラ' in title or 'LIVE CAMERA' in title.upper():
        score += 35
    if 'LIVE' in title.upper():
        score += 15
    for word in re.findall(r'[\w一-龯ぁ-んァ-ヶ]{2,}', query):
        if word.lower() in title.lower():
            score += 2
    return score


def yt_dlp_thumbnail(item: dict) -> bytes | None:
    page = str(item.get('page') or '').strip()
    query = str(item.get('query') or '').strip()
    targets: list[tuple[str, bool]] = []
    if page:
        targets.append((page, False))
    if query:
        targets.append(('ytsearch5:' + query, True))

    for target, is_search in targets:
        cmd = [
            'yt-dlp', '--skip-download', '--dump-single-json', '--no-warnings',
            '--socket-timeout', '12', '--retries', '1', '--playlist-end', '5', target,
        ]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=40)
        except Exception:
            continue
        if p.returncode != 0 or not p.stdout.strip():
            continue
        try:
            info = json.loads(p.stdout.splitlines()[-1])
        except Exception:
            continue

        candidates = info.get('entries') if is_search else None
        if candidates:
            candidates = [x for x in candidates if isinstance(x, dict)]
            candidates.sort(key=lambda x: candidate_score(x, query), reverse=True)
        else:
            candidates = [info]

        for candidate in candidates:
            vid = str(candidate.get('id') or '').strip()
            data = direct_youtube_thumbnail(vid if len(vid) == 11 else None)
            if data:
                return data
            thumb = str(candidate.get('thumbnail') or '').strip()
            if not thumb:
                thumbs = candidate.get('thumbnails') or []
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
    page_id = extract_video_id(str(item.get('page') or ''))
    data = direct_youtube_thumbnail(page_id)
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


def clean_fallback(title: str, group: str) -> Image.Image:
    img = Image.new('RGB', (SIZE, SIZE), (118, 158, 193))
    d = ImageDraw.Draw(img)
    for y in range(SIZE):
        t = y / max(1, SIZE - 1)
        if y < SIZE * 0.62:
            c = (int(108 + 55 * t), int(158 + 55 * t), int(202 + 38 * t))
        else:
            c = (44, 91, 110) if ('港' in title or '愛南' in title) else (61, 103, 64)
        d.line((0, y, SIZE, y), fill=c)

    if group == '空港' or '空港' in title:
        d.polygon([(70, 390), (348, 390), (280, 300), (142, 300)], fill=(74, 76, 82))
        d.line((209, 310, 209, 390), fill=(240, 240, 240), width=8)
        d.polygon([(165, 205), (247, 205), (272, 220), (236, 226), (218, 253),
                   (201, 253), (192, 227), (148, 220)], fill=(245, 245, 245))
    elif '港' in title or '湾' in title:
        d.rectangle((0, 290, SIZE, SIZE), fill=(39, 108, 150))
        d.polygon([(102, 300), (310, 300), (280, 342), (130, 342)], fill=(239, 239, 239))
        d.rectangle((180, 240, 230, 300), fill=(242, 242, 242))
    else:
        d.polygon([(0, 340), (100, 245), (170, 310), (250, 205), (418, 342), (418, 418), (0, 418)],
                  fill=(62, 103, 68))
    return img


def has_current_style(path: Path) -> bool:
    try:
        with Image.open(path) as img:
            return img.info.get(STYLE_KEY) == STYLE_VALUE
    except Exception:
        return False


def render_logo(filename: str, title: str, group: str, data: bytes | None):
    header_h = 94
    photo_h = SIZE - header_h
    if data:
        try:
            photo_src = Image.open(BytesIO(data)).convert('RGB')
        except Exception:
            photo_src = clean_fallback(title, group)
    else:
        photo_src = clean_fallback(title, group)

    photo = crop_to_size(photo_src, SIZE, photo_h)
    photo = ImageEnhance.Contrast(photo).enhance(1.05)
    photo = ImageEnhance.Color(photo).enhance(1.04)

    out = Image.new('RGB', (SIZE, SIZE), 'white')
    out.paste(photo, (0, header_h))
    draw = ImageDraw.Draw(out)
    accent = (29, 78, 160) if group != '愛媛県内ライブカメラ' else (230, 91, 28)
    draw.rectangle((1, 1, SIZE - 2, SIZE - 2), outline=(214, 214, 214), width=3)

    num = int(filename.split('_', 2)[1])
    badge_w = 56
    draw.rounded_rectangle((10, 12, 10 + badge_w, 12 + 56), radius=8, fill=accent)
    num_font = fit_font(draw, str(num), badge_w - 10, 35, 24)
    nbox = draw.textbbox((0, 0), str(num), font=num_font)
    nx = 10 + badge_w / 2 - (nbox[2] - nbox[0]) / 2 - nbox[0]
    ny = 12 + 28 - (nbox[3] - nbox[1]) / 2 - nbox[1]
    draw.text((nx, ny), str(num), font=num_font, fill='white')

    title_font = fit_font(draw, title, SIZE - 90, 39, 22)
    box = draw.textbbox((0, 0), title, font=title_font)
    tx = 78
    ty = (header_h - (box[3] - box[1])) / 2 - box[1] - 1
    draw.text((tx, ty), title, font=title_font, fill=accent)

    live_w, live_h = 112, 46
    x1, y1 = SIZE - live_w - 10, SIZE - live_h - 10
    x2, y2 = SIZE - 10, SIZE - 10
    draw.rounded_rectangle((x1, y1, x2, y2), radius=7, fill=(229, 25, 25))
    draw.rounded_rectangle((x1 + 7, y1 + 8, x1 + 39, y1 + 38), radius=6, fill='white')
    draw.polygon([(x1 + 18, y1 + 14), (x1 + 18, y1 + 32), (x1 + 31, y1 + 23)], fill=(229, 25, 25))
    live_font = fit_font(draw, 'LIVE', 60, 25, 18)
    live_box = draw.textbbox((0, 0), 'LIVE', font=live_font)
    draw.text((x1 + 45, y1 + (live_h - (live_box[3] - live_box[1])) / 2 - live_box[1] - 1),
              'LIVE', font=live_font, fill='white')

    pnginfo = PngImagePlugin.PngInfo()
    pnginfo.add_text(STYLE_KEY, STYLE_VALUE)
    pnginfo.add_text('thumbnail_source', 'youtube' if data else 'clean-fallback')
    out.save(ROOT / filename, 'PNG', optimize=True, pnginfo=pnginfo)
    print('generated', ROOT / filename, 'thumbnail=' + ('yes' if data else 'clean-fallback'))


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
            path.write_text(json.dumps(items, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(path, 'canonical yt43 v4 logo mappings:', changed)


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
    for tvg, filename, title, group in SPECS:
        out = ROOT / filename
        if out.exists() and out.stat().st_size > 12_000 and has_current_style(out):
            print('keep existing', out)
            continue
        pending.append((tvg, filename, title, group))

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

    for tvg, filename, title, group in pending:
        render_logo(filename, title, group, thumbs.get(tvg))

    patch_source_files()
    render_ehime_catv_ainan()


if __name__ == '__main__':
    main()
