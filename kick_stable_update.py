from __future__ import annotations

import json
import re
from pathlib import Path

FREEWIFI = Path('freewifi')
CONFIG = Path('kick_channels.json')
START = '# === KICK_MANAGED_START ==='
END = '# === KICK_MANAGED_END ==='
YT_ANCHOR = '# === GENERAL_YOUTUBE_MANAGED_START ==='
RESOLVER = 'https://himitsu-six.vercel.app/api/kick'

CHANNEL_KEYS = {
    'kick.gccx': 'gccx',
    'kick.nogizaka': 'nogizaka',
}


def strip_old_kick(text: str, names: set[str]) -> str:
    text = re.sub(re.escape(START) + r'.*?' + re.escape(END) + r'\n?', '', text, flags=re.S)
    lines = text.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('#EXTINF:') and i + 1 < len(lines):
            name = line.rsplit(',', 1)[-1].strip() if ',' in line else ''
            if name in names:
                i += 2
                continue
        out.append(line)
        i += 1
    return '\n'.join(out).rstrip() + '\n'


def render_block(config: list[dict]) -> str:
    lines = [START, '## KICK']
    for item in config:
        tvg_id = str(item.get('tvg_id') or '').strip()
        key = CHANNEL_KEYS.get(tvg_id)
        if not key:
            continue
        name = str(item['name'])
        logo = str(item.get('logo') or '').strip()
        meta = '#EXTINF:-1 group-title="その他"'
        if tvg_id:
            meta += f' tvg-id="{tvg_id}"'
        if logo:
            meta += f' tvg-logo="{logo}"'
        lines.extend([f'{meta},{name}', f'{RESOLVER}?ch={key}'])
    lines.append(END)
    return '\n'.join(lines) + '\n'


def insert_block(text: str, block: str) -> str:
    if YT_ANCHOR in text:
        return text.replace(YT_ANCHOR, block + '\n' + YT_ANCHOR, 1)
    return text.rstrip() + '\n\n' + block


def main() -> int:
    original = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    config = json.loads(CONFIG.read_text(encoding='utf-8'))
    if not original.startswith('#EXTM3U'):
        raise RuntimeError('freewifi lost #EXTM3U header')
    if not isinstance(config, list) or not config:
        raise RuntimeError('kick_channels.json must contain a non-empty list')

    names = {str(x['name']) for x in config}
    cleaned = strip_old_kick(original, names)
    updated = insert_block(cleaned, render_block(config))

    if updated.count('#EXTINF:') < max(50, int(original.count('#EXTINF:') * 0.70)):
        raise RuntimeError('playlist channel count collapsed')
    if f'{RESOLVER}?ch=gccx' not in updated:
        raise RuntimeError('GCCX stable KICK resolver missing')

    FREEWIFI.write_text(updated, encoding='utf-8')
    print('KICK block switched to stable resolver URLs')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
