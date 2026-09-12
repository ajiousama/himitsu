from pathlib import Path
from datetime import datetime, timezone, timedelta
import json
import re
from urllib.parse import quote

FREEWIFI = Path('freewifi')
VERIFIED = Path('verified_daily_status.json')
STATUS = Path('today_jra_status.json')
JST = timezone(timedelta(hours=9))
START = '# === TODAY_JRA_START ==='
END = '# === TODAY_JRA_END ==='
GROUP = '今日の開催場'
RAW_BASE = 'https://raw.githubusercontent.com/ajiousama/himitsu/main'
JRA_LOGO_BASE = 'https://raw.githubusercontent.com/earphone1981/public-sports-iptv/main'

JRA_LOGOS = {
    'jra.gch': f'{JRA_LOGO_BASE}/gch.png',
    'jra.east': f'{JRA_LOGO_BASE}/east_web3.png',
    'jra.west': f'{JRA_LOGO_BASE}/west_web4.png',
    'jra.hokkaido': f'{JRA_LOGO_BASE}/hokkaido_local.png',
}

ROUTES = {
    'jra.gch': ('グリーンチャンネル HQ', 'gchmain_master.m3u8'),
    'jra.east': ('JRA EAST HQ', 'gch_east_master.m3u8'),
    'jra.west': ('JRA WEST HQ', 'gch_west_master.m3u8'),
    'jra.hokkaido': ('JRA HOKKAIDO HQ', 'gch_hokkaido_master.m3u8'),
}


def raw(name):
    return f'{RAW_BASE}/{quote(name)}'


def strip(text):
    text = re.sub(
        re.escape(START) + r'.*?' + re.escape(END) + r'\n?',
        '',
        text,
        flags=re.S,
    )
    ids = set(ROUTES)
    lines = text.splitlines()
    out = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('#EXTINF:') and any(
            f'tvg-id="{x}"' in line for x in ids
        ):
            i += 1
            while (
                i < len(lines)
                and not lines[i].startswith('#EXTINF:')
                and not lines[i].startswith('## ')
                and not lines[i].startswith('# ===')
            ):
                i += 1
            continue
        out.append(line)
        i += 1
    return '\n'.join(out).rstrip() + '\n'


def main():
    now = datetime.now(JST)
    reported = []

    try:
        cfg = json.loads(VERIFIED.read_text(encoding='utf-8-sig'))
        if cfg.get('date') == now.date().isoformat():
            reported = [
                x for x in cfg.get('jra_active_ids', []) if x in ROUTES
            ]
    except Exception:
        pass

    # GCH HQ is always exposed on any JRA-active day. The verifier may
    # report only the local EAST/WEST/HOKKAIDO feeds.
    active = list(dict.fromkeys(['jra.gch', *reported])) if reported else []

    base = strip(FREEWIFI.read_text(encoding='utf-8-sig', errors='replace'))
    rows = []
    for cid in active:
        name, file = ROUTES[cid]
        rows += [
            (
                f'#EXTINF:-1 tvg-id="{cid}" tvg-name="{name}" '
                f'tvg-logo="{JRA_LOGOS[cid]}" group-title="{GROUP}",{name}'
            ),
            raw(file),
            '',
        ]

    managed = (
        START
        + '\n## 本日の開催場（JRA）\n'
        + '\n'.join(rows).rstrip()
        + ('\n' if rows else '')
        + END
    )
    anchor = '# === GENERAL_YOUTUBE_MANAGED_START ==='
    text = (
        base.replace(anchor, managed + '\n\n' + anchor, 1)
        if anchor in base
        else base.rstrip() + '\n\n' + managed + '\n'
    )

    FREEWIFI.write_text(text.rstrip() + '\n', encoding='utf-8')
    STATUS.write_text(
        json.dumps(
            {
                'generated_at': now.isoformat(),
                'active_count': len(active),
                'active_ids': active,
                'active_labels': [ROUTES[x][0] for x in active],
                'channels': {
                    x: {
                        'active': x in active,
                        'source': 'ajiousama HQ master',
                    }
                    for x in ROUTES
                },
            },
            ensure_ascii=False,
            indent=2,
        )
        + '\n',
        encoding='utf-8',
    )
    print('JRA HQ active:', active)


if __name__ == '__main__':
    main()
