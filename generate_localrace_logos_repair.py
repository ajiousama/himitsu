from pathlib import Path
from io import BytesIO
import base64
import re
from PIL import Image, ImageFile

OUT = Path('logos/public_sports/venues')
OUT.mkdir(parents=True, exist_ok=True)
CELL = 128
SIZE = (512, 512)
ORDER = [
    'obihiro', 'mombetsu', 'morioka', 'mizusawa', 'urawa',
    'funabashi', 'oi', 'kawasaki', 'kanazawa', 'kasamatsu',
    'nagoya', 'sonoda', 'himeji', 'kochi', 'saga',
]


def extract_sheet_b64():
    text = Path('generate_localrace_logos.py').read_text(encoding='utf-8')
    m = re.search(r'SHEET_B64\s*=\s*"""(.*?)"""', text, re.S)
    if not m:
        raise SystemExit('SHEET_B64 not found')
    s = re.sub(r'[^A-Za-z0-9+/=]', '', m.group(1))
    # The current approved sheet was committed with one stray trailing base64
    # data character. Remove only the impossible modulo-4 tail and restore
    # padding; the JPEG payload itself is otherwise intact.
    while len(s) % 4 == 1:
        s = s[:-1]
    s = s.rstrip('=')
    s += '=' * (-len(s) % 4)
    return s


def main():
    ImageFile.LOAD_TRUNCATED_IMAGES = True
    raw = base64.b64decode(extract_sheet_b64(), validate=False)
    with Image.open(BytesIO(raw)) as src:
        sheet = src.convert('RGB')
    expected = (CELL * 5, CELL * 3)
    if sheet.size != expected:
        raise SystemExit(f'approved sheet size mismatch: {sheet.size} != {expected}')

    for i, slug in enumerate(ORDER):
        row, col = divmod(i, 5)
        tile = sheet.crop((col * CELL, row * CELL, (col + 1) * CELL, (row + 1) * CELL))
        tile = tile.resize(SIZE, Image.Resampling.LANCZOS)
        out = OUT / f'localrace_{slug}.png'
        tile.save(out, 'PNG', optimize=True)
        print('generated', out)


if __name__ == '__main__':
    main()
