"""Decode real AAC packets with a deliberate HLS-style timestamp gap."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from radio_tv_filemux import AUDIO_OUTPUT_ARGS


def run(*args):
    return subprocess.run(args, check=True, capture_output=True, text=True, timeout=30).stdout


def gaps(path):
    rows = json.loads(run('ffprobe', '-v', 'error', '-select_streams', 'a:0',
                          '-show_packets', '-show_entries', 'packet=pts_time,duration_time',
                          '-of', 'json', str(path)))['packets']
    return [float(b['pts_time'])-float(a['pts_time'])-float(a['duration_time'])
            for a,b in zip(rows, rows[1:])]


class RadioContinuity(unittest.TestCase):
    def test_timestamp_gap_is_normalized_without_losing_video(self):
        with tempfile.TemporaryDirectory() as d:
            source, output = Path(d)/'gap.ts', Path(d)/'normalized.ts'
            run('ffmpeg','-v','error','-f','lavfi','-i','color=size=64x64:rate=1:duration=3',
                '-f','lavfi','-i','sine=frequency=440:sample_rate=48000:duration=3',
                '-af',"aselect='not(between(t,0.8,1.2))'", '-c:v','libx264','-c:a','aac',
                '-f','mpegts',str(source))
            self.assertGreater(max(gaps(source)), .1)
            run('ffmpeg','-v','error','-i',str(source),'-map','0:v:0','-map','0:a:0',
                '-c:v','copy', *AUDIO_OUTPUT_ARGS, '-f','mpegts',str(output))
            self.assertLess(max(abs(g) for g in gaps(output)), .003)
            run('ffmpeg','-v','error','-i',str(output),'-map','0:v:0','-map','0:a:0','-f','null','-')


if __name__ == '__main__':
    unittest.main()
