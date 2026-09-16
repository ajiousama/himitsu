#!/usr/bin/env python3
from __future__ import annotations

import re
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

M3U = Path("haru_vod.m3u")
JST = ZoneInfo("Asia/Tokyo")
PROXY = "https://himitsu-six.vercel.app/api/haru-clip"
TARGET_ID = "ohayo_asahi_0730"
TARGET_HOUR = 7
TARGET_MINUTE = 30
DURATION = 600

START_RE = re.compile(r"([?&]start=)(\d+)")
TVG_RE = re.compile(rf"(haru\.vod\.{re.escape(TARGET_ID)}\.)(\d+)")


def main() -> int:
    if not M3U.exists():
        raise SystemExit("haru_vod.m3u not found")

    lines = M3U.read_text(encoding="utf-8-sig", errors="replace").splitlines()
    out: list[str] = []
    changed = 0
    i = 0

    while i < len(lines):
        line = lines[i]
        if line.startswith("#EXTINF:") and f"haru.vod.{TARGET_ID}." in line and i + 1 < len(lines):
            source = lines[i + 1].strip()
            sm = START_RE.search(source)
            if sm and "/stream/jp/abc/" in source:
                programme_start = int(sm.group(2))
                base_jst = datetime.fromtimestamp(programme_start, timezone.utc).astimezone(JST)
                target_jst = base_jst.replace(hour=TARGET_HOUR, minute=TARGET_MINUTE, second=0, microsecond=0)
                offset = int((target_jst - base_jst).total_seconds())

                # HARU replay URLs are keyed by programme start. Do not replace start= with 07:30;
                # keep the 05:00 boundary and seek 2h30m inside the replay playlist.
                if 0 <= offset <= 4 * 3600:
                    target = programme_start + offset
                    proxy = (
                        PROXY
                        + "?src="
                        + urllib.parse.quote(source, safe="")
                        + f"&offset={offset}&duration={DURATION}"
                    )
                    line = TVG_RE.sub(lambda m: m.group(1) + str(target), line)
                    if "," in line:
                        head, _ = line.split(",", 1)
                        line = f"{head},おはよう朝日です 7:30-7:40 {target_jst:%m/%d}"
                    out.extend([line, proxy])
                    changed += 1
                    i += 2
                    continue
        out.append(line)
        i += 1

    M3U.write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"HARU clip postprocess: {changed} Oha Asa 07:30 clips")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
