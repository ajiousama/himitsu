#!/usr/bin/env python3
"""Build number-free Rch channel icons from the exact existing GitHub PNGs.

Preparation only: writes logos/rch_numberless and does NOT edit FreeWiFi,
the source logos, stream URLs, channel IDs, or EPG.
"""
from pathlib import Path
from PIL import Image

SOURCE = Path("logos/contrast")
OUTPUT = Path("logos/rch_numberless")
FILES = (
    "rch_30_0ff7a069.png",
    "rch_35_b75aa72f.png",
    "rch_37_9e6b1bb9.png",
    "rch_86_ddfe8550.png",
    "rch_113_2882cf68.png",
    "rch_46_e0c5bb04.png",
    "rch_125_9c62a3d1.png",
    "rch_124_d8f804e4.png",
    "rch_41_7dd05c57.png",
    "rch_123_43ddebaa.png",
    "rch_122_9c8157af.png",
)

def build():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    for filename in FILES:
        src = SOURCE / filename
        if not src.is_file():
            raise FileNotFoundError(src)
        with Image.open(src) as image:
            if image.size != (512, 512):
                raise ValueError(f"{src}: expected 512x512, got {image.size}")
            # Every verified Rch card has its artwork between Y60 and Y312;
            # the CH number is beneath that region, around Y348..410.
            # Move the original artwork unchanged to the center of a white card.
            artwork = image.convert("RGB").crop((0, 58, 512, 314))
        card = Image.new("RGB", (512, 512), "#ffffff")
        card.paste(artwork, (0, 128))
        destination = OUTPUT / filename
        card.save(destination, "PNG", optimize=True)
        with Image.open(destination) as result:
            result.verify()
        print(f"{src} -> {destination}")
    assert len(list(OUTPUT.glob("rch_*.png"))) == len(FILES)

if __name__ == "__main__":
    build()
