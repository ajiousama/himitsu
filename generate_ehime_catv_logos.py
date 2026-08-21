from pathlib import Path
import re
from PIL import Image, ImageDraw, ImageFont

W = H = 512
OUT = Path('logos/ehime_catv')
OUT.mkdir(parents=True, exist_ok=True)

CHANNELS = [
    ('たうんプレミアム', '01_town_premium.png', '#E65100', ['たうん', 'プレミアム']),
    ('たうんNews24', '02_town_news24.png', '#C62828', ['たうんNews', '24']),
    ('街カメ24', '03_machicam24.png', '#1565C0', ['街カメ24']),
    ('お知らせチャンネル', '04_info.png', '#455A64', ['お知らせ', 'チャンネル']),
    ('番組宣伝ch', '05_program_promo.png', '#7B1FA2', ['番組宣伝ch']),
    ('イベントプレミアム', '06_event_premium.png', '#AD1457', ['イベント', 'プレミアム']),
    ('イベントセレクション', '07_event_selection.png', '#6A1B9A', ['イベント', 'セレクション']),
    ('えひめチャンネル', '08_ehime_channel.png', '#EF6C00', ['えひめ', 'チャンネル']),
    ('えひめ・防災チャンネル', '09_ehime_bousai.png', '#D32F2F', ['えひめ・防災', 'チャンネル']),
    ('囲碁・将棋チャンネル(eCATV)', '10_igo_shogi.png', '#5D4037', ['囲碁・将棋', 'チャンネル']),
    ('釣りビジョン(eCATV)', '11_fishing_vision.png', '#0277BD', ['釣りビジョン']),
    ('CNNj(eCATV)', '12_cnnj.png', '#B71C1C', ['CNNj']),
    ('日経CNBC(eCATV)', '13_nikkei_cnbc.png', '#00695C', ['日経CNBC']),
    ('松山市議会中継', '14_matsuyama_gikai.png', '#283593', ['松山市議会', '中継']),
    ('愛媛県議会中継', '15_ehime_gikai.png', '#2E7D32', ['愛媛県議会', '中継']),
]

FONT_CANDIDATES = [
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc',
    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
]
FONT = next((p for p in FONT_CANDIDATES if Path(p).exists()), None)
if not FONT:
    raise RuntimeError('Japanese font not found')


def fit(draw, text, max_width=456, max_size=104, min_size=50):
    for size in range(max_size, min_size - 1, -2):
        f = ImageFont.truetype(FONT, size)
        box = draw.textbbox((0, 0), text, font=f)
        if box[2] - box[0] <= max_width:
            return f
    return ImageFont.truetype(FONT, min_size)


def make_logo(filename, color, lines):
    img = Image.new('RGB', (W, H), 'white')
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, W, 28), fill=color)
    fonts = [fit(d, line) for line in lines]
    heights = []
    for line, f in zip(lines, fonts):
        b = d.textbbox((0, 0), line, font=f)
        heights.append(b[3] - b[1])
    gap = 10
    total_h = sum(heights) + gap * (len(lines) - 1)
    y = 210 - total_h / 2
    for line, f, h in zip(lines, fonts, heights):
        b = d.textbbox((0, 0), line, font=f)
        tw = b[2] - b[0]
        d.text(((W - tw) / 2, y - b[1]), line, font=f, fill=color)
        y += h + gap
    sub = '愛媛CATV'
    sf = ImageFont.truetype(FONT, 38)
    b = d.textbbox((0, 0), sub, font=sf)
    d.text(((W - (b[2] - b[0])) / 2, 425 - b[1]), sub, font=sf, fill=color)
    d.rectangle((58, 478, 454, 486), fill=color)
    img = img.convert('P', palette=Image.Palette.ADAPTIVE, colors=16)
    img.save(OUT / filename, optimize=True)


for display, filename, color, lines in CHANNELS:
    make_logo(filename, color, lines)

m3u = Path('freewifi')
text = m3u.read_text(encoding='utf-8')
start = text.index('## 愛媛CATV')
end = text.index('# === GENERAL_YOUTUBE_MANAGED_START ===')
head, section, tail = text[:start], text[start:end], text[end:]

base = 'https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/ehime_catv/'
url_map = {display: base + filename for display, filename, _, _ in CHANNELS}

lines = section.splitlines()
for i, line in enumerate(lines):
    if not line.startswith('#EXTINF:'):
        continue
    display = line.rsplit(',', 1)[-1].strip()
    if display not in url_map:
        continue
    line = re.sub(r'\s+tvg-logo="[^"]*"', '', line)
    comma = line.rfind(',')
    line = line[:comma] + f' tvg-logo="{url_map[display]}"' + line[comma:]
    lines[i] = line

m3u.write_text(head + '\n'.join(lines) + '\n' + tail, encoding='utf-8')
print('Generated 15 Ehime CATV logos and updated freewifi logo URLs.')
