#!/usr/bin/env python3
from pathlib import Path
import json
import re
from urllib.parse import quote
import sys

# Works both as a direct script and inside GitHub Actions.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FREEWIFI = Path("freewifi")
PLAYLIST = Path("tv/playlist.m3u")
START = "## 地上波"
END = "## ラジオ"
CONTRAST_DB = Path("logos/contrast_sources.json")
RAW_BASE = "https://raw.githubusercontent.com/ajiousama/himitsu/main"
MANUAL_START = "# === MANUAL_TV_START ==="
MANUAL_END = "# === MANUAL_TV_END ==="

def strip_retired_naori(text: str) -> str:
    """Exclude old NAORI standard, HD and CS playlist entries."""
    lines = text.splitlines(keepends=True)
    kept = []
    drop_url = False
    for line in lines:
        if line.startswith("#EXTINF:"):
            drop_url = "naori" in line.lower() or "haruka" in line.lower()
            if drop_url:
                continue
        if drop_url:
            if not line.strip():
                continue
            if not line.lstrip().startswith("#"):
                drop_url = False
                continue
            drop_url = False
        kept.append(line)
    return "".join(kept)


def payload():
    text = strip_retired_naori(PLAYLIST.read_text(encoding="utf-8-sig", errors="replace"))
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
        body = strip_retired_naori(body).strip("\n")
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


def strip_generated_newblog_vod(text: str) -> str:
    """Remove prior generated replay rows before copying the canonical TV playlist."""
    text = re.sub(
        r"(?m)^# === NEWBLOG_VOD_START ===\n.*?^# === NEWBLOG_VOD_END ===(?:\n|$)",
        "",
        text,
        flags=re.S,
    )
    lines = text.splitlines()
    kept = []
    i = 0
    while i < len(lines):
        if (lines[i].startswith("#EXTINF:")
                and re.search(r'tvg-id="newblog\.vod\.[^"]+"', lines[i])):
            i += 1
            while i < len(lines) and not lines[i].strip():
                i += 1
            if i < len(lines) and not lines[i].lstrip().startswith("#"):
                i += 1
            continue
        kept.append(lines[i])
        i += 1
    return "\n".join(kept)


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


def validate_source_groups(text: str) -> None:
    """Refuse to publish TV metadata that reverts the protected source groups."""
    legacy_groups = {"地上波", "BS", "CS", "その他", "グリーンCh"}
    for line in text.splitlines():
        if not line.startswith("#EXTINF:"):
            continue
        match = re.search(r'group-title="([^"]+)"', line)
        group = match.group(1) if match else ""
        name = line.rsplit(",", 1)[-1]
        if "（newblog系）" in name and group in legacy_groups:
            raise RuntimeError(f"newblog source group reverted: {name} => {group}")
        if "(5002直)" in name and group in {"地上波", "BS", "CS"}:
            raise RuntimeError(f"5002 source group reverted: {name} => {group}")
        if name.startswith("グリーンチャンネル") and group != "今日の開催場":
            raise RuntimeError(f"Green Channel group reverted: {name} => {group}")


def main():
    text = FREEWIFI.read_text(encoding="utf-8-sig", errors="replace")
    protected = manual_block(text)
    base = strip_generated_newblog_vod(strip_manual_block(text))

    a = base.find(START)
    b = base.find(END, a + len(START))
    if a < 0 or b < 0:
        raise SystemExit("TV section boundary missing in freewifi")

    tv = payload().rstrip() + "\n\n" + protected + "\n\n"
    updated = base[:a] + tv + base[b:]
    updated, reused = reuse_known_contrast_logos(updated)
    updated = strip_retired_naori(updated)
    validate_source_groups(updated)
    if "haruka" in updated.lower():
        raise SystemExit("Retired HARUKA entry detected in FreeWiFi; refusing publish")
    if "naori" in updated.lower():
        raise SystemExit("Retired NAORI entry detected in FreeWiFi; refusing publish")
    FREEWIFI.write_text(updated.rstrip() + "\n", encoding="utf-8")
    print(
        f"TV synced from tv/playlist.m3u; manual TV block preserved; "
        f"reused contrast logos={reused}"
    )

if __name__ == "__main__":
    main()
