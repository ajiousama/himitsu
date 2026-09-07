from pathlib import Path
from io import BytesIO
import base64
import hashlib
from PIL import Image

OUT = Path('logos/public_sports/venues')
SRC = Path('assets/localrace_sheet_b64')
OUT.mkdir(parents=True, exist_ok=True)
CELL = 128
SIZE = (512, 512)
ORDER = [
    'obihiro', 'mombetsu', 'morioka', 'mizusawa', 'urawa',
    'funabashi', 'oi', 'kawasaki', 'kanazawa', 'kasamatsu',
    'nagoya', 'sonoda', 'himeji', 'kochi', 'saga',
]
EXPECTED = [
    (7000, '993577a64285801ee970c6952472e82972457f2224ce9b2cf800c7ab923d7339'),
    (7000, '6b02b10de11dff5649b346076330f3e6ef99f31f64670fe21c3f43cdab01448e'),
    (7000, '75bef179660c7f749b05823454cb36720c396669c3465fff63cb26f22149fb90'),
    (5912, '5565e1e9c01a1ec9497c951c88a4b3d6e1e9b97ebde03af3f7d5acf9a32abf0a'),
]


def main():
    chunks = []
    for i, (exp_len, exp_sha) in enumerate(EXPECTED, 1):
        chunk = (SRC / f'part{i}.txt').read_text(encoding='ascii').strip()
        got_sha = hashlib.sha256(chunk.encode('ascii')).hexdigest()
        print(f'part{i}: len={len(chunk)} sha256={got_sha}')
        if len(chunk) != exp_len or got_sha != exp_sha:
            raise SystemExit(f'part{i} mismatch: expected len={exp_len} sha256={exp_sha}')
        chunks.append(chunk)
    encoded = ''.join(chunks)
    full_sha = hashlib.sha256(encoded.encode('ascii')).hexdigest()
    print(f'full: len={len(encoded)} sha256={full_sha}')
    if len(encoded) != 26912 or full_sha != '2f400c865081b6eef2a1e64324e53fb7cea06877aa0b75ac603ea90745802636':
        raise SystemExit('full approved logo sheet base64 mismatch')
    raw = base64.b64decode(encoded, validate=True)
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
