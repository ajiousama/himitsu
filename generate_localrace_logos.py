from pathlib import Path
from io import BytesIO
import base64
from PIL import Image

OUT = Path("logos/public_sports/venues")
SRC = Path("assets/localrace_source")
OUT.mkdir(parents=True, exist_ok=True)
CELL = 128
SIZE = (512, 512)
ORDER = [
    "obihiro", "mombetsu", "morioka", "mizusawa", "urawa",
    "funabashi", "oi", "kawasaki", "kanazawa", "kasamatsu",
    "nagoya", "sonoda", "himeji", "kochi", "saga",
]

# Approved 2026-09-07 local-racing logo sheet.
# Morioka/Mizusawa: shared Iwate mark, venue text changed only.
# Sonoda/Himeji: shared approved horse mark, SONODA/HIMEJI + Japanese venue text.
def main():
    encoded = "".join(
        (SRC / f"part{i:02d}.b64").read_text(encoding="ascii").strip()
        for i in range(1, 9)
    )
    raw = base64.b64decode(encoded, validate=True)
    with Image.open(BytesIO(raw)) as src:
        sheet = src.convert("RGB")
    assert sheet.size == (CELL * 5, CELL * 3), sheet.size

    for i, slug in enumerate(ORDER):
        row, col = divmod(i, 5)
        tile = sheet.crop((
            col * CELL,
            row * CELL,
            (col + 1) * CELL,
            (row + 1) * CELL,
        ))
        tile = tile.resize(SIZE, Image.Resampling.LANCZOS)
        out = OUT / f"localrace_{slug}.png"
        tile.save(out, "PNG", optimize=True)
        print("generated", out)

if __name__ == "__main__":
    main()
