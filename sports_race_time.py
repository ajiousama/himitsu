"""Race timestamps are independent of the XMLTV programme's lead-in start."""
from datetime import datetime, timedelta, timezone, time
import re

JST = timezone(timedelta(hours=9))
NORMALIZE = str.maketrans('０１２３４５６７８９：Ｒ', '0123456789:R')


def race_time(programme):
    raw_title = (programme.findtext('title') or '').strip()
    # EPG guidance/waiting rows can mention "1R HH:MM発走" but are not the
    # race programme itself. Keep them out of race-boundary normalization.
    if (
        ('本日' in raw_title and '開催' in raw_title and re.search(r'1\s*[ＲR].*発走', raw_title))
        or '開催待ち' in raw_title
        or raw_title.startswith('⏳ 待機')
    ):
        return None
    title = raw_title.translate(NORMALIZE)
    number = re.search(r'(\d{1,2})\s*R', title, re.I)
    clock = re.search(r'(\d{1,2}):([0-5]\d)\s*発走', title)
    if not number or not clock:
        return None
    hour, minute = map(int, clock.groups())
    if hour > 47:
        return None
    try:
        anchor = datetime.strptime(programme.get('stop'), '%Y%m%d%H%M%S %z').astimezone(JST)
    except (ValueError, TypeError):
        return None
    # A programme ends shortly after its advertised race. Its start can be
    # hours earlier, even on the previous calendar day.
    candidates = [datetime.combine(anchor.date() + timedelta(days=d), time(hour % 24, minute), JST)
                  for d in (-1, 0, 1)]
    actual = min(candidates, key=lambda dt: abs((anchor - dt).total_seconds()))
    meeting_day = actual.date() - timedelta(days=hour // 24)
    return {'race': int(number.group(1)), 'dt': actual, 'day': meeting_day,
            'start': f'{hour:02d}:{minute:02d}', 'stop': max(anchor, actual + timedelta(minutes=3))}
