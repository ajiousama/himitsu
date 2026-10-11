#!/usr/bin/env python3
from pathlib import Path
import json
import re
import time
from urllib.parse import quote

FREEWIFI = Path("freewifi")
CONTRAST_DB = Path("logos/contrast_sources.json")
RAW_BASE = "https://raw.githubusercontent.com/ajiousama/himitsu/main"
PLAYLIST = Path("tver/playlist.m3u")
START = "### TVerﾘｱﾙﾀｲﾑ"
END_CANDIDATES = ("# === PATAPATA_TV_START ===", "## YouTube")

def reuse_known_contrast_logos(text: str) -> tuple[str, int]:
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
        text = text.replace(source, f"{RAW_BASE}/{quote(relpath, safe='/._-')}")
        replaced += count
    return text, replaced


def payload():
    text = PLAYLIST.read_text(encoding="utf-8-sig", errors="replace")
    lines = text.splitlines()
    if lines and lines[0].startswith("#EXTM3U"):
        lines = lines[1:]

    # Other FreeWiFi rebuilds may reuse an older tver/playlist.m3u before the
    # next TVer worker runs. Enforce endAt here too, so expired rows cannot
    # reappear when another workflow refreshes FreeWiFi.
    allowed_ids = None
    status_path = Path("tver/live_status.json")
    if status_path.exists():
        state = json.loads(status_path.read_text(encoding="utf-8"))
        now = int(time.time())
        allowed_ids = set()
        for row in state.get("entries") or []:
            try:
                end = int(row.get("end_at") or 0)
                start = int(row.get("start_at") or 0)
            except (TypeError, ValueError):
                continue
            if (not end or now < end) and (not start or now >= start):
                allowed_ids.add(str(row.get("tvg_id") or ""))

    visible = []
    skip = False
    suppressed = 0
    for line in lines:
        if line.startswith("#EXTINF:"):
            match = re.search(r'tvg-id="([^"]+)"', line)
            skip = bool(
                allowed_ids is not None and match
                and match.group(1).startswith("tver.")
                and match.group(1) not in allowed_ids
            )
            if skip:
                suppressed += 1
        if not skip:
            visible.append(line)
    if suppressed:
        print(f"TVer expired/unlisted entries suppressed on sync: {suppressed}")
    return "\n".join(visible).strip() + "\n\n"

def main():
    text = FREEWIFI.read_text(encoding="utf-8-sig", errors="replace")
    a = text.find(START)
    b = -1
    if a >= 0:
        positions = [
            text.find(marker, a + len(START))
            for marker in END_CANDIDATES
        ]
        positions = [pos for pos in positions if pos >= 0]
        b = min(positions) if positions else -1
    if a < 0 or b < 0:
        raise SystemExit("TVer realtime section boundary missing in freewifi")
    updated = text[:a] + payload() + text[b:]
    updated, reused = reuse_known_contrast_logos(updated)
    FREEWIFI.write_text(updated.rstrip() + "\n", encoding="utf-8")
    print(f"TVer realtime synced from tver/playlist.m3u; reused white-card logos={reused}")

if __name__ == "__main__":
    main()
