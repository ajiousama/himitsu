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


def rewrite_start(url: str, epoch: int) -> str:
    if START_RE.search(url):
        return START_RE.sub(lambda m: m.group(1) + str(epoch), url, count=1)
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}start={epoch}"


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
                original = int(sm.group(2))
                base_jst = datetime.fromtimestamp(original, timezone.utc).astimezone(JST)
                target_jst = base_jst.replace(hour=TARGET_HOUR, minute=TARGET_MINUTE, second=0, microsecond=0)
                # If the source programme starts after 07:30, it is not the morning block we want.
                if target_jst >= base_jst and (target_jst - base_jst).total_seconds() <= 4 * 3600:
                    target = int(target_jst.timestamp())
                    clipped_source = rewrite_start(source, target)
                    proxy = (
                        PROXY
                        + "?src="
                        + urllib.parse.quote(clipped_source, safe="")
                        + f"&duration={DURATION}"
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
