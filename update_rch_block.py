from pathlib import Path
import re

FREEWIFI = Path("freewifi")

PIGOO_LOGO = "https://raw.githubusercontent.com/ajiousama/himitsu/main/logos/contrast/Pigoo_jp_daa9c17a.png"
PIGOO_BLOCK = f'''#EXTINF:-1 tvg-id="Pigoo_jp" tvg-logo="{PIGOO_LOGO}" group-title="Rch",Pigoo (haruka(9394))
http://42.113.96.247:9394/stream/234.m3u8
'''


def remove_pigoo_entries(text: str) -> str:
    # Remove every existing Pigoo EXTINF + URL pair so the move stays idempotent.
    pattern = re.compile(
        r'(?m)^#EXTINF:[^\n]*tvg-id="Pigoo_jp"[^\n]*\n[^\n]+\n*'
    )
    return pattern.sub('', text)


def main() -> None:
    text = FREEWIFI.read_text(encoding="utf-8-sig")
    if "## Rch" not in text:
        raise RuntimeError("Rch block not found")
    if "## 今日の開催場" not in text:
        raise RuntimeError("today block marker not found")

    text = remove_pigoo_entries(text)

    start = text.index("## Rch")
    end = text.index("## 今日の開催場", start)
    rch = text[start:end].rstrip()
    updated = text[:start] + rch + "\n\n" + PIGOO_BLOCK + "\n" + text[end:]

    FREEWIFI.write_text(updated.rstrip() + "\n", encoding="utf-8")
    print("Placed Pigoo haruka(9394) directly below Rch with canonical logo")


if __name__ == "__main__":
    main()
