#!/usr/bin/env python3
from pathlib import Path
import json
import re
from urllib.parse import quote

FREEWIFI = Path("freewifi")
PLAYLIST = Path("tv/playlist.m3u")
START = "## 地上波"
END = "## ラジオ"
CONTRAST_DB = Path("logos/contrast_sources.json")
RAW_BASE = "https://raw.githubusercontent.com/ajiousama/himitsu/main"
MANUAL_START = "# === MANUAL_TV_START ==="
MANUAL_END = "# === MANUAL_TV_END ==="

def payload():
    text = PLAYLIST.read_text(encoding="utf-8-sig", errors="replace")
    lines = text.splitlines()
    if lines and lines[0].startswith("#EXTM3U"):
        lines = lines[1:]
    return "\n".join(lines).strip() + "\n\n"

def manual_block(text: str) -> str:
    """Keep user-added TV rows across every canonical FreeWiFi rebuild."""
    match = re.search(
        re.escape(MANUAL_START) + r"(.*?)" + re.escape(MANUAL_END),
        text,
        flags=re.S,
    )
    if match:
        body = match.group(1).strip("\n")
    else:
        body = (
            "# 手動追加TV保護枠: この2つのマーカーの間は自動更新でも保持されます。\n"
            "# EXTINF行とURLをここへ手動で追加してください。"
        )
    return MANUAL_START + "\n" + body + "\n" + MANUAL_END


def strip_manual_block(text: str) -> str:
    return re.sub(
        r"\n*" + re.escape(MANUAL_START) + r".*?" + re.escape(MANUAL_END) + r"\n*",
        "\n\n",
        text,
        flags=re.S,
    )


def reuse_known_contrast_logos(text: str) -> tuple[str, int]:
    """Reuse already-generated local contrast logos without fetching/rebuilding images."""
    if not CONTRAST_DB.exists():
        return text, 0
    try:
        db = json.loads(CONTRAST_DB.read_text(encoding="utf-8"))
    except Exception:
        return text, 0

    replaced = 0
    for source, meta in db.items():
        if not isinstance(source, str) or not isinstance(meta, dict):
            continue
        relpath = meta.get("path")
        if not isinstance(relpath, str) or not relpath or not Path(relpath).is_file():
            continue
        count = text.count(source)
        if not count:
            continue
        local = f"{RAW_BASE}/{quote(relpath, safe='/._-')}"
        text = text.replace(source, local)
        replaced += count
    return text, replaced


def main():
    text = FREEWIFI.read_text(encoding="utf-8-sig", errors="replace")
    protected = manual_block(text)
    base = strip_manual_block(text)

    a = base.find(START)
    b = base.find(END, a + len(START))
    if a < 0 or b < 0:
        raise SystemExit("TV section boundary missing in freewifi")

    tv = payload().rstrip() + "\n\n" + protected + "\n\n"
    updated = base[:a] + tv + base[b:]
    updated, reused = reuse_known_contrast_logos(updated)
    FREEWIFI.write_text(updated.rstrip() + "\n", encoding="utf-8")
    print(
        f"TV synced from tv/playlist.m3u; manual TV block preserved; "
        f"reused contrast logos={reused}"
    )

if __name__ == "__main__":
    main()
