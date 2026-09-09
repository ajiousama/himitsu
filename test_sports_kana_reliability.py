import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch
import xml.etree.ElementTree as ET

import public_sports_epg_local as epg
import freewifi_today_public_sports as today
import finalize_today_public_sports as final
import kana_tube_update as kana
from sports_race_time import JST, race_time


def programme(root, start='20260908201800', stop='20260908205300', title='【１２Ｒ】 20:50発走 川崎', desc='開催区分: ナイター'):
    p = ET.SubElement(root, 'programme', channel='chihou.kawasaki_keiba', start=start+' +0900', stop=stop+' +0900')
    ET.SubElement(p, 'title').text = title
    ET.SubElement(p, 'desc').text = desc
    return p


class SportsReliability(unittest.TestCase):
    def test_ending_follows_race_not_leadin(self):
        root = ET.Element('tv')
        programme(root)
        programme(root, '20260908205300', '20260909013000', '本日の開催は終了しました')
        programme(root, '20260909150000', '20260909153300', '【１Ｒ】 15:30発走 川崎')
        epg.add_next_event_notices(root, date(2026, 9, 8))
        ending = [p for p in root if '終了しました' in p.findtext('title')]
        self.assertEqual(len(ending), 1)
        self.assertEqual(ending[0].get('start'), '20260908205300 +0900')
        epg.add_next_event_notices(root, date(2026, 9, 8))
        self.assertEqual(len([p for p in root if '終了しました' in p.findtext('title')]), 1)

    def test_tomorrow_notice_does_not_extend_today(self):
        root = ET.Element('tv'); programme(root)
        programme(root, '20260908213500', '20260909000000', '翌日開催予定（仮時間）', '')
        s = final.epg_state(ET.tostring(root), datetime(2026, 9, 8, 21, 10, tzinfo=JST))
        self.assertEqual(s['chihou.kawasaki_keiba']['last_stop'].strftime('%H:%M'), '20:53')

    def test_notice_does_not_overwrite_night(self):
        root = ET.Element('tv'); programme(root)
        programme(root, '20260908213500', '20260909000000', '翌日開催予定（仮時間）', '')
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)/'epg.xml'; ET.ElementTree(root).write(p)
            with patch.object(today, 'PUBLIC_EPG', p), patch.object(today, 'datetime') as clock:
                clock.now.return_value = datetime(2026,9,8,20,0,tzinfo=JST)
                clock.strptime.side_effect = datetime.strptime
                _, modes, _ = today.epg_state()
        self.assertEqual(modes['chihou.kawasaki_keiba'], 'night')

    def test_overnight_keeps_meeting_date(self):
        root = ET.Element('tv')
        p = programme(root, '20260909000300', '20260909003300', '【８Ｒ】 24:30発走')
        self.assertEqual(race_time(p)['day'], date(2026,9,8))
        s = final.epg_state(ET.tostring(root), datetime(2026,9,8,23,50,tzinfo=JST))
        self.assertEqual(s['chihou.kawasaki_keiba']['next_race']['start'], '24:30')

    def test_future_only_not_today(self):
        root = ET.Element('tv')
        programme(root, title='翌日開催予定（仮時間）')
        self.assertEqual(final.epg_state(ET.tostring(root), datetime(2026,9,8,tzinfo=JST)), {})


class KanaReliability(unittest.TestCase):
    def test_impostor_name_and_handle_prefix_rejected(self):
        self.assertFalse(kana.official({'channel':'かなtube','channel_id':'impostor'}))
        self.assertFalse(kana.official({'channel_url':'https://youtube.com/@kana_tube_fake'}))
        self.assertTrue(kana.official({'channel_id':kana.CHANNEL_ID}))

    def test_partial_inspection_cannot_confirm_none(self):
        with patch.object(kana,'listing_ids', return_value=(['abc'],None)), patch.object(kana,'search_ids', return_value=[]), patch.object(kana,'inspect_watch',return_value=(None,'timeout')):
            selected, confirmed, _ = kana.choose_current()
        self.assertIsNone(selected); self.assertFalse(confirmed)

    def test_videos_listing_alone_cannot_confirm_none(self):
        def listing(url, limit):
            return ([], None if url.endswith('/videos') else 'timeout')
        with patch.object(kana,'listing_ids',side_effect=listing), patch.object(kana,'search_ids',return_value=[]):
            _, confirmed, _ = kana.choose_current()
        self.assertFalse(confirmed)

    def test_known_video_rechecked_when_listing_empty(self):
        info = {'id':'known','channel_id':kana.CHANNEL_ID,'live_status':'is_live'}
        with patch.object(kana,'listing_ids',return_value=([],None)), patch.object(kana,'search_ids',return_value=[]), patch.object(kana,'inspect_watch',return_value=(info,None)) as watch:
            selected, confirmed, _ = kana.choose_current({'video_id':'known'})
        self.assertEqual(selected,info); watch.assert_called_once_with('known')

    def test_search_fallback_runs_even_when_listing_has_old_entries(self):
        old = {'id':'old','channel_id':kana.CHANNEL_ID,'live_status':'was_live'}
        new = {'id':'new','channel_id':kana.CHANNEL_ID,'live_status':'is_upcoming','release_timestamp':int(datetime.now(timezone.utc).timestamp())+3600}
        def inspect(vid):
            return (new if vid == 'new' else old, None)
        with patch.object(kana,'listing_ids',return_value=(['old'],None)), patch.object(kana,'search_ids',return_value=['new']), patch.object(kana,'inspect_watch',side_effect=inspect):
            selected, confirmed, _ = kana.choose_current()
        self.assertTrue(confirmed)
        self.assertEqual(selected['id'], 'new')

    def test_next_night_reservation_beats_stale_day_reservation(self):
        now = int(datetime.now(timezone.utc).timestamp())
        stale_day = {'id':'day','channel_id':kana.CHANNEL_ID,'live_status':'is_upcoming','release_timestamp':now-3*3600}
        night = {'id':'night','channel_id':kana.CHANNEL_ID,'live_status':'is_upcoming','release_timestamp':now+3600}
        def inspect(vid):
            return ({'day':stale_day,'night':night}[vid], None)
        with patch.object(kana,'listing_ids',return_value=(['day','night'],None)), patch.object(kana,'search_ids',return_value=[]), patch.object(kana,'inspect_watch',side_effect=inspect):
            selected, _, _ = kana.choose_current()
        self.assertEqual(selected['id'], 'night')

    def test_slot_classification_covers_day_and_night(self):
        day = datetime(2026, 9, 10, 13, 30, tzinfo=JST).timestamp()
        night = datetime(2026, 9, 10, 20, 35, tzinfo=JST).timestamp()
        self.assertEqual(kana.classify_slot(day), 'day')
        self.assertEqual(kana.classify_slot(night), 'night')

    def test_publication_keeps_concurrent_boat_update(self):
        with tempfile.TemporaryDirectory() as d:
            paths = {k:Path(d)/k for k in ('OUT','GENERAL','FREEWIFI','STATUS')}
            snapshot = Path(d)/'snapshot'; snapshot.mkdir()
            other = '#EXTM3U\n#EXTINF:-1 tvg-id="boat.new",Updated boat\nhttps://boat.example/new\n'
            for key in ('FREEWIFI', 'GENERAL'): paths[key].write_text(other)
            paths['STATUS'].write_text('{}')
            with patch.multiple(kana, **paths):
                (snapshot/paths['OUT'].name).write_text('#EXTM3U\n'+kana.entry('https://youtube.com/watch?v=new','is_upcoming')+'\n')
                (snapshot/paths['STATUS'].name).write_text(json.dumps({'state':'is_upcoming'}))
                kana.publish_snapshot(snapshot)
                kana.validate_outputs()
            self.assertIn('https://boat.example/new', paths['FREEWIFI'].read_text())
            self.assertIn('watch?v=new', paths['FREEWIFI'].read_text())

    def test_none_is_valid_without_logo(self):
        with tempfile.TemporaryDirectory() as d:
            paths = {k:Path(d)/k for k in ('OUT','GENERAL','FREEWIFI','STATUS')}
            for k,p in paths.items(): p.write_text(json.dumps({'state':'none'}) if k=='STATUS' else '#EXTM3U\n')
            with patch.multiple(kana, **paths): kana.validate_outputs()

    def test_hls_failure_publishes_live_fallback_in_all_playlists(self):
        with tempfile.TemporaryDirectory() as d:
            paths = {k:Path(d)/k for k in ('OUT','GENERAL','FREEWIFI','STATUS')}
            other = '#EXTM3U\n#EXTINF:-1 tvg-id="boat.keep",Boat\nhttps://boat.example/live\n'
            paths['OUT'].write_text('#EXTM3U\n')
            paths['GENERAL'].write_text(other)
            paths['FREEWIFI'].write_text(other)
            paths['STATUS'].write_text(json.dumps({'state':'is_upcoming','video_id':'old'}))
            info = {'id':'new','channel_id':kana.CHANNEL_ID,'live_status':'is_live','title':'Night live'}
            with patch.multiple(kana, **paths), patch.object(kana,'choose_current',return_value=(info,True,[])), patch.object(kana,'direct_live_url',return_value=None):
                kana.main()
                status = kana.read_status()
                self.assertEqual(status['state'],'is_live')
                self.assertFalse(status['direct_hls'])
                self.assertTrue(status['hls_retry_required'])
                kana.validate_outputs()
            for k in ('OUT','GENERAL','FREEWIFI'):
                self.assertIn('watch?v=new', paths[k].read_text())
            self.assertIn('https://boat.example/live', paths['FREEWIFI'].read_text())

    def test_unreachable_check_reapplies_last_owned_entry_after_rebuild(self):
        with tempfile.TemporaryDirectory() as d:
            paths = {k:Path(d)/k for k in ('OUT','GENERAL','FREEWIFI','STATUS')}
            payload = kana.entry('https://youtube.com/watch?v=known','is_upcoming')
            paths['OUT'].write_text('#EXTM3U\n'+payload+'\n')
            paths['GENERAL'].write_text('#EXTM3U\n')
            paths['FREEWIFI'].write_text('#EXTM3U\n')
            paths['STATUS'].write_text(json.dumps({'state':'is_upcoming','video_id':'known'}))
            with patch.multiple(kana, **paths), patch.object(kana,'choose_current',return_value=(None,False,['timeout'])):
                kana.main()
                status = kana.read_status()
                self.assertEqual(status['state'],'is_upcoming')
                self.assertTrue(status['check_error'])
                kana.validate_outputs()
            self.assertIn('watch?v=known', paths['GENERAL'].read_text())
            self.assertIn('watch?v=known', paths['FREEWIFI'].read_text())


if __name__ == '__main__':
    unittest.main()
