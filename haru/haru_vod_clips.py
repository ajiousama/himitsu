#!/usr/bin/env python3
from __future__ import annotations

import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

M3U = Path("haru/haru_vod.m3u")
JST = ZoneInfo("Asia/Tokyo")
PROXY = "https://kick-resolver.onrender.com/haru-clip"
TARGET_ID = "ohayo_asahi_0730"
TARGET_HOUR = 7
TARGET_MINUTE = 30
TARGET_DURATION = 600

START_RE = re.compile(r"([?&]start=)(\d+)")
TVG_RE = re.compile(rf"(haru\.vod\.{re.escape(TARGET_ID)}\.)(\d+)")
DUR_RE = re.compile(r"^#EXTINF:([0-9]+(?:\.[0-9]+)?)")


def proxy_url(source: str, offset: int, duration: int) -> str:
    return (
        PROXY
        + "?src="
        + urllib.parse.quote(source, safe="")
        + f"&offset={max(0, int(offset))}&duration={max(30, min(int(duration), 8 * 3600))}"
    )


def extinf_duration(line: str) -> int:
    m = DUR_RE.match(line)
    if not m:
        return 3600
    try:
        return max(30, min(int(float(m.group(1))), 8 * 3600))
    except Exception:
        return 3600


def make_indefinite(line: str) -> str:
    return DUR_RE.sub("#EXTINF:-1", line, count=1)


def main() -> int:
    if not M3U.exists():
        raise SystemExit("haru_vod.m3u not found")

    lines = M3U.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    out: list[str] = []
    clipped = 0
    special = 0
    i = 0

    while i < len(lines):
        line = lines[i]
        if line.startswith("#EXTINF:") and "haru.vod." in line and i + 1 < len(lines):
            source = lines[i + 1].strip()
            if source.startswith("https://haru.charandom.blog/stream/jp/") and "/replay.m3u8" in source:
                duration = extinf_duration(line)
                offset = 0

                if f"haru.vod.{TARGET_ID}." in line and "/stream/jp/abc/" in source:
                    sm = START_RE.search(source)
                    if sm:
                        programme_start = int(sm.group(2))
                        base_jst = datetime.fromtimestamp(programme_start, timezone.utc).astimezone(JST)
                        target_jst = base_jst.replace(hour=TARGET_HOUR, minute=TARGET_MINUTE, second=0, microsecond=0)
                        candidate_offset = int((target_jst - base_jst).total_seconds())
                        if 0 <= candidate_offset <= 4 * 3600:
                            offset = candidate_offset
                            duration = TARGET_DURATION
                            target = programme_start + offset
                            line = TVG_RE.sub(lambda m: m.group(1) + str(target), line)
                            if "," in line:
                                head, _ = line.split(",", 1)
                                line = f"{head},📼 おはよう朝日です 7:30-7:40 {target_jst:%m/%d}"
                            special += 1

                out.extend([make_indefinite(line), proxy_url(source, offset, duration)])
                clipped += 1
                i += 2
                continue
        out.append(line)
        i += 1

    M3U.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"HARU clip postprocess: {clipped} proxied VODs ({special} Oha Asa 07:30 clips)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
