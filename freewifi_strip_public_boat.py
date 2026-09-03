from pathlib import Path
from datetime import datetime, timezone, timedelta
import json
import re

FREEWIFI = Path('freewifi')
BOAT_STATUS = Path('today_boat_status.json')
START = '# === TODAY_PUBLIC_SPORTS_START ==='
END = '# === TODAY_PUBLIC_SPORTS_END ==='
JST = timezone(timedelta(hours=9))


def load_boat_status():
    if not BOAT_STATUS.exists():
        return {}
    try:
        return json.loads(BOAT_STATUS.read_text(encoding='utf-8'))
    except Exception:
        return {}


def v2_is_current(status):
    """Only let BOAT V2 replace general BOAT entries when its state is for today."""
    today = datetime.now(JST).date().isoformat()
    if status.get('date') != today:
        return False
    # A same-day resolver state is authoritative even before the first venue
    # becomes visible.  Old/stale seed state must never erase today's fallback.
    return status.get('system') in {'boat-v2-resolver', 'boat-v2-iphone-seed'}


def strip_boat(body):
    lines = body.splitlines()
    out = []
    i = 0
    removed = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('#EXTINF:') and re.search(r'tvg-id="boat\.[^"]+"', line):
            removed += 1
            i += 1
            while i < len(lines) and not lines[i].startswith('#EXTINF:') and not lines[i].startswith('## ') and not lines[i].startswith('# ==='):
                i += 1
            continue
        out.append(line)
        i += 1
    return '\n'.join(out), removed


def main():
    if not FREEWIFI.exists():
        raise SystemExit('freewifi not found')

    boat_status = load_boat_status()
    if not v2_is_current(boat_status):
        print(
            'BOAT V2 state is stale/missing; preserve TODAY_PUBLIC_SPORTS BOAT fallback '
            f"(status_date={boat_status.get('date')!r}, system={boat_status.get('system')!r})"
        )
        return 0

    text = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    m = re.search(re.escape(START) + r'(.*?)' + re.escape(END), text, re.S)
    if not m:
        print('No TODAY_PUBLIC_SPORTS block; BOAT V2 untouched')
        return 0
    body, removed = strip_boat(m.group(1))
    replacement = START + body + END
    if removed:
        text = text[:m.start()] + replacement + text[m.end():]
        FREEWIFI.write_text(text.rstrip() + '\n', encoding='utf-8')
    print(f'General FreeWiFi BOAT entries removed={removed}; current BOAT V2 block preserved')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
