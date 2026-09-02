"""Compatibility entry point for the ajiousama-only public-sports pipeline.

The old version fetched earphone1981/public-sports-iptv at runtime.  Keep this
filename for any legacy workflow/caller, but delegate entirely to local state
and local masters generated inside ajiousama/himitsu.
"""
from pathlib import Path
from datetime import datetime, timezone, timedelta
import json

import freewifi_today_public_sports
import freewifi_today_jra

JST = timezone(timedelta(hours=9))
VERIFY = Path('verified_daily_status.json')


def main():
    if not VERIFY.exists():
        raise SystemExit('verified_daily_status.json missing; run public_sports_epg_local.py first')
    cfg = json.loads(VERIFY.read_text(encoding='utf-8-sig'))
    today = datetime.now(JST).date().isoformat()
    if cfg.get('date') != today:
        raise SystemExit(f'verified_daily_status.json is stale: {cfg.get("date")} != {today}')

    freewifi_today_public_sports.main()
    freewifi_today_jra.main()
    print('Verified daily override: applied ajiousama-local state only')


if __name__ == '__main__':
    main()
