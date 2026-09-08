from datetime import date, datetime, timedelta
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import xml.etree.ElementTree as ET

import boat_auto_system as boat
import boat_playback as playback
import boat_publish
from test_boat_auto_system import card, fake_stream


class ReliabilityTests(unittest.TestCase):
    def setUp(self):
        self.day = date(2026, 9, 8)
        self.now = datetime(2026, 9, 8, 9, 0, tzinfo=boat.JST)
        self.url = fake_stream(self.day)

    def test_verified_url_not_reacquired(self):
        stream = {'url': self.url, 'playback_verified': True,
                  'checked_at': self.now.isoformat()}
        with patch.object(boat, 'fetch_seed') as fetch, patch.object(boat, 'token_expired', return_value=False), patch.object(playback, 'probe') as probe:
            result, error = boat.maintain_stream('10', stream, self.day, self.now)
        fetch.assert_not_called()
        probe.assert_not_called()
        self.assertEqual(result['url'], self.url)
        self.assertFalse(error)

    def test_audio_video_failure_not_accepted(self):
        with patch.object(boat, 'fetch_seed', return_value=('10', self.url, '')), patch.object(playback, 'probe', return_value={'ok': False, 'error': 'decode failed'}):
            stream, error = boat.maintain_stream('10', {}, self.day, self.now)
        self.assertNotIn('url', stream)
        self.assertTrue(error)

    def test_decoded_first_acquisition_records_evidence(self):
        with patch.object(boat, 'fetch_seed', return_value=('10', self.url, '')), patch.object(playback, 'probe', return_value={'ok': True, 'video_decoded': True, 'audio_decoded': True}):
            stream, error = boat.maintain_stream('10', {}, self.day, self.now)
        self.assertTrue(stream['playback_verified'])
        self.assertEqual(stream['first_verified_at'], self.now.isoformat())
        self.assertFalse(error)

    def test_transient_failure_keeps_good_url(self):
        stream = {'url': self.url, 'playback_verified': True,
                  'checked_at': (self.now - timedelta(minutes=6)).isoformat()}
        with patch.object(boat, 'token_expired', return_value=False), patch.object(boat, 'fetch_seed') as fetch, patch.object(playback, 'probe', return_value={'ok': False}):
            result, error = boat.maintain_stream('10', stream, self.day, self.now)
        self.assertTrue(result['playback_verified'])
        self.assertEqual(result['consecutive_failures'], 1)
        fetch.assert_not_called()

    def test_second_failure_reacquires_without_waiting_five_minutes(self):
        stream = {'url': self.url, 'playback_verified': True, 'consecutive_failures': 1,
                  'checked_at': (self.now - timedelta(seconds=61)).isoformat()}
        with patch.object(boat, 'token_expired', return_value=False), patch.object(boat, 'fetch_seed', return_value=('10', '', 'unavailable')) as fetch, patch.object(playback, 'probe', return_value={'ok': False}):
            result, error = boat.maintain_stream('10', stream, self.day, self.now)
        fetch.assert_called_once()
        self.assertFalse(result['playback_verified'])
        self.assertEqual(result['url'], self.url)

    def test_previous_day_never_valid(self):
        self.assertFalse(boat.current_day_stream(self.url, self.day + timedelta(days=1)))

    def test_wrong_venue_cloud_response_uses_official_fallback(self):
        with patch.object(boat, 'request_json', return_value={'ok': True, 'url': self.url, 'venue': '24', 'date': '20260908'}), patch.object(playback, 'direct_source', return_value='') as direct:
            result = boat.fetch_seed('10', self.day)
        direct.assert_called_once()
        self.assertFalse(result[1])

    def test_duplicate_venue_stream_rejected(self):
        streams = {'boat.omura': {'url': self.url}}
        with patch.object(boat, 'maintain_stream', return_value=({'url': self.url, 'playback_verified': True}, '')):
            result = boat.refresh_cloud_streams({'10': card(self.day, 8)}, streams, self.day)
        self.assertNotIn('boat.mikuni', streams)
        self.assertEqual(result['failures'][0]['error'], 'duplicate venue URL rejected')

    def test_schedule_outage_preserves_current_cards(self):
        state = {'date': self.day.isoformat(), 'venues': {'boat.mikuni': {
            'jcd': '10', 'races': [{'race': r['race'], 'start': r['start'].strftime('%H:%M'), 'name': r['name']} for r in card(self.day, 8)]}}}
        with patch.object(boat, 'official_cards', side_effect=RuntimeError), patch.object(boat, 'fetch_cards', side_effect=RuntimeError):
            cards, checked, warnings = boat.load_schedule(self.now, state)
        self.assertEqual(len(cards['10']), 12)
        self.assertEqual(len(warnings), 2)

    def test_midnight_cannot_reuse_schedule(self):
        state = {'date': '2026-09-07', 'venues': {'boat.mikuni': {'jcd': '10', 'races': []}}}
        self.assertEqual(boat.cached_cards(state, self.day), {})

    def test_schedule_drop_cannot_remove_held_venue(self):
        state = {'date': self.day.isoformat(), 'venues': {'boat.mikuni': {
            'jcd': '10', 'races': [{'race': r['race'], 'start': r['start'].strftime('%H:%M')} for r in card(self.day, 8)]}}}
        with patch.object(boat, 'official_cards', return_value={'24': card(self.day, 15)}):
            cards, _, warnings = boat.load_schedule(self.now, state)
        self.assertEqual(set(cards), {'10', '24'})
        self.assertTrue(warnings)

    def test_epg_retains_other_sports_and_extends_finished_to_midnight(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'guides.xml'
            root = ET.Element('tv')
            p = ET.SubElement(root, 'programme', channel='auto.iizuka', start='20260908200000 +0900', stop='20260909003000 +0900')
            ET.SubElement(p, 'title').text = '飯塚'
            ET.ElementTree(root).write(path)
            boat.overlay_epg_file(path, {'10': card(self.day, 8)}, self.day)
            boat.overlay_epg_file(path, {'10': card(self.day, 8)}, self.day)
            root = ET.parse(path).getroot()
            self.assertEqual(len([p for p in root.findall('programme') if p.get('channel') == 'auto.iizuka']), 1)
            progs = [p for p in root.findall('programme') if p.get('channel') == 'boat.mikuni']
            self.assertEqual(len(progs), 13)
            self.assertEqual(progs[-1].get('stop'), '20260909000000 +0900')

    def test_stopped_and_vod_playlists_rejected(self):
        with patch.object(playback, 'read_url', return_value=b'#EXTM3U\n#EXT-X-MEDIA-SEQUENCE:5\n#EXTINF:6,\nseg.ts\n#EXT-X-ENDLIST\n'):
            self.assertFalse(playback.probe(self.url)['ok'])
        with patch.object(playback, 'media_playlist', return_value=('https://test.example/live/', ['seg.ts'], 5)), patch.object(playback, 'read_url', return_value=b'video'):
            self.assertFalse(playback.probe(self.url, {'last_segment': '/live/seg.ts'})['ok'])
            self.assertFalse(playback.probe(self.url, {'sequence': 6})['ok'])

    def test_schedule_requires_all_races(self):
        races = {str(n): {'closed_at': f'2026-09-08 {8+n//2:02d}:{30*(n%2):02d}:00'} for n in range(1, 11)}
        self.assertEqual(boat.cards_from_snapshot({'programs': {'stadiums': {'10': {'races': races}}}}, self.day), {})


if __name__ == '__main__':
    unittest.main()
