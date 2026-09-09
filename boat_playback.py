"""Bounded playback checks. Never log signed URLs or publish untested sources."""
import json
import re
import subprocess
import urllib.parse
import urllib.request

HEADERS = {
    'User-Agent': 'Mozilla/5.0',
    'Origin': 'https://front.player.boatrace-cdn.jp',
    'Referer': 'https://front.player.boatrace-cdn.jp/',
    'Cache-Control': 'no-cache',
}


def read_url(url, limit=1048576):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=8) as response:
        return response.read(limit)


def media_playlist(url):
    for _ in range(4):
        text = read_url(url).decode('utf-8-sig')
        if not text.lstrip().startswith('#EXTM3U'):
            raise ValueError('invalid HLS playlist')
        lines = [line.strip() for line in text.splitlines()]
        if '#EXT-X-STREAM-INF:' in text:
            # Select an actual video variant, not a separate audio rendition.
            index = next(i for i, line in enumerate(lines) if line.startswith('#EXT-X-STREAM-INF:'))
            child = next(line for line in lines[index + 1:] if line and not line.startswith('#'))
            url = urllib.parse.urljoin(url, child)
            continue
        segments = [line for line in lines if line and not line.startswith('#')]
        if not segments:
            raise ValueError('HLS has no media segments yet')
        if '#EXT-X-ENDLIST' in lines:
            raise ValueError('ended VOD playlist is not a live stream')
        sequence = re.search(r'#EXT-X-MEDIA-SEQUENCE:(\d+)', text)
        return url, segments, int(sequence.group(1)) if sequence else None
    raise ValueError('too many HLS playlist levels')


def probe(url, previous=None):
    """Check live media bytes and decode both video and audio, with hard deadlines."""
    try:
        playlist_url, segments, sequence = media_playlist(url)
        segment = urllib.parse.urljoin(playlist_url, segments[-1])
        if not read_url(segment, 4096):
            raise ValueError('empty media segment')
        previous = previous or {}
        # Called >= 5 minutes apart after success: an unchanged last segment is stale.
        segment_key = urllib.parse.urlsplit(segment).path
        if previous.get('last_segment') == segment_key:
            raise ValueError('live media has stopped advancing')
        if sequence is not None and previous.get('sequence') is not None and sequence < previous['sequence']:
            raise ValueError('live media sequence moved backwards')
        # Some venues take longer than one second before both elementary streams
        # are available. Retry a short bounded decode twice and include the same
        # headers/User-Agent used by the HTTP preflight.
        last_kind = 'decode'
        for attempt in range(2):
            try:
                result = subprocess.run(
                    ['ffmpeg', '-nostdin', '-v', 'error',
                     '-rw_timeout', '10000000',
                     '-user_agent', HEADERS['User-Agent'],
                     '-headers', 'Origin: https://front.player.boatrace-cdn.jp\r\nReferer: https://front.player.boatrace-cdn.jp/\r\n',
                     '-reconnect', '1', '-reconnect_streamed', '1',
                     '-reconnect_delay_max', '2',
                     '-i', url, '-t', '3',
                     '-map', '0:v:0', '-map', '0:a:0',
                     '-f', 'null', '-'],
                    capture_output=True, timeout=45,
                )
            except subprocess.TimeoutExpired:
                last_kind = 'decode_timeout'
                continue
            if result.returncode == 0:
                return {'ok': True, 'sequence': sequence, 'last_segment': segment_key,
                        'video_decoded': True, 'audio_decoded': True}
            last_kind = 'audio_video_decode_failed'
        raise ValueError(last_kind)
    except Exception as exc:
        # Never expose stderr or signed URLs; retain a useful category only.
        detail = str(exc)
        safe = detail if detail in {
            'invalid HLS playlist', 'HLS has no media segments yet',
            'ended VOD playlist is not a live stream',
            'live media has stopped advancing',
            'live media sequence moved backwards',
            'empty media segment', 'too many HLS playlist levels',
            'decode_timeout', 'audio_video_decode_failed'
        } else 'playback check failed'
        return {'ok': False, 'error': f'{type(exc).__name__}: {safe}'}


def direct_source(jcd, day, slug):
    """Independent official Playback API fallback; no previous-date/media guessing."""
    ref = f'lm-br-{jcd}{slug}-tokyo-{day:%Y%m%d}'
    url = f'https://playback.api.streaks.jp/v1/projects/cp-boatrace-prod/medias/ref:{ref}?audio_only=false'
    data = json.loads(read_url(url))
    return next((item.get('src', '') for item in data.get('sources', [])
                 if str(item.get('src', '')).startswith('https://manifest.streaks.jp/')
                 and '.m3u8' in item.get('src', '')), '')
