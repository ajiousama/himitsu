#!/usr/bin/env python3
from __future__ import annotations

import base64
import json
import re
import time
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

FREEWIFI = Path('freewifi')
STATUS = Path('today_public_sports_status.json')
START = '# === TODAY_PUBLIC_SPORTS_START ==='
END = '# === TODAY_PUBLIC_SPORTS_END ==='
SAFETY_SECONDS = 600


def jwt_exp_from_url(url: str):
    try:
        token = (parse_qs(urlsplit(url).query).get('token') or [None])[0]
        if not token or token.count('.') < 2:
            return None
        payload = token.split('.')[1]
        payload += '=' * (-len(payload) % 4)
        obj = json.loads(base64.urlsafe_b64decode(payload.encode()).decode('utf-8'))
        return int(obj['exp']) if 'exp' in obj else None
    except Exception:
        return None


def block_url(block):
    for line in block[1:]:
        s = line.strip()
        if s.startswith(('http://', 'https://')):
            return s
    return ''


def split_entries(body: str):
    lines = body.splitlines()
    out = []
    i = 0
    while i < len(lines):
        if not lines[i].startswith('#EXTINF:'):
            out.append(('raw', [lines[i]]))
            i += 1
            continue
        block = [lines[i]]
        i += 1
        while i < len(lines) and not lines[i].startswith('#EXTINF:'):
            block.append(lines[i])
            i += 1
        out.append(('entry', block))
    return out


def main():
    if not FREEWIFI.exists():
        raise SystemExit('freewifi missing')
    text = FREEWIFI.read_text(encoding='utf-8-sig', errors='replace')
    m = re.search(re.escape(START) + r'\n(.*?)\n' + re.escape(END), text, re.S)
    if not m:
        print('No TODAY_PUBLIC_SPORTS block; nothing to prune')
        return

    now = int(time.time())
    kept = []
    removed = []
    for kind, block in split_entries(m.group(1)):
        if kind != 'entry':
            kept.extend(block)
            continue
        ext = block[0]
        idm = re.search(r'tvg-id="([^"]+)"', ext)
        cid = idm.group(1) if idm else ''
        if not cid.startswith('boat.'):
            kept.extend(block)
            continue
        url = block_url(block)
        exp = jwt_exp_from_url(url)
        # Only reject a BOAT URL when we can positively prove its JWT is stale.
        # YouTube fallbacks and direct URLs without a JWT are left untouched.
        if exp is not None and exp <= now + SAFETY_SECONDS:
            removed.append((cid, exp, url))
            continue
        kept.extend(block)

    new_body = '\n'.join(kept).rstrip()
    replacement = START + '\n' + new_body + ('\n' if new_body else '') + END
    new_text = text[:m.start()] + replacement + text[m.end():]
    FREEWIFI.write_text(new_text.rstrip() + '\n', encoding='utf-8')

    if STATUS.exists() and removed:
        try:
            obj = json.loads(STATUS.read_text(encoding='utf-8-sig'))
            channels = obj.get('channels') if isinstance(obj, dict) else None
            if isinstance(channels, dict):
                for cid, _, _ in removed:
                    channels.pop(cid, None)
                obj['boat_pruned_expired'] = [cid for cid, _, _ in removed]
                STATUS.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        except Exception as e:
            print('Status JSON update skipped:', e)

    if removed:
        for cid, exp, _ in removed:
            print(f'PRUNED expired BOAT: {cid} exp={exp}')
    print(f'Expired BOAT pruned: {len(removed)}')


if __name__ == '__main__':
    main()
