#!/usr/bin/env python3
from __future__ import annotations
import re
from pathlib import Path

FREEWIFI = Path('freewifi')
HARU_PLAYLIST = Path('haru/haru_vod.m3u')
START = '# === HARU_VOD_START ==='
END = '# === HARU_VOD_END ==='


def remove_old(text: str) -> str:
    return re.sub(r'\n?' + re.escape(START) + r'.*?' + re.escape(END) + r'\n?', '\n', text, flags=re.S)


def main() -> int:
    if not FREEWIFI.exists():
        raise RuntimeError('FreeWiFi input missing')
    text = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    cleaned = remove_old(text)
    FREEWIFI.write_text(cleaned, encoding='utf-8')
    print('HARU VOD paused: removed from FreeWiFi and publishing disabled')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
