#!/usr/bin/env python3
import argparse
import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATA = ROOT / 'japan_iptv_channels.csv'


def main():
    p = argparse.ArgumentParser(description='URLなし候補DBを絞り込み')
    p.add_argument('--decision', default='')
    p.add_argument('--priority', default='')
    p.add_argument('--genre', default='')
    p.add_argument('--system', default='')
    p.add_argument('--out', default='')
    a = p.parse_args()

    rows = list(csv.DictReader(DATA.open(encoding='utf-8-sig', newline='')))
    rows = [
        r for r in rows
        if (not a.decision or r['decision'] == a.decision)
        and (not a.priority or r['priority'] == a.priority)
        and (not a.genre or r['genre'] == a.genre)
        and (not a.system or a.system.lower() in r['system_candidates'].lower())
    ]

    if a.out:
        out = ROOT / a.out
        with out.open('w', encoding='utf-8-sig', newline='') as f:
            if rows:
                w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                w.writeheader()
                w.writerows(rows)
        print(f'wrote {out} ({len(rows)} rows)')
    else:
        for r in rows:
            print(
                f"{r['decision']}\t{r['priority']}\t{r['genre']}\t"
                f"{r['display_name_ja']}\t{r['system_primary']}\t{r['slug_or_id_candidate']}"
            )
        print(f'-- {len(rows)} rows')


if __name__ == '__main__':
    main()
