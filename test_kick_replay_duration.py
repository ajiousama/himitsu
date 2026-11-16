"""Safeguards for a zero-second KICK archive's HLS duration recovery."""
import io
import unittest
from unittest.mock import patch

from kick_replay import hls_completed_vod_duration, normalize_vod


class HlsDurationTests(unittest.TestCase):
    MASTER="https://media.example.invalid/vods/master.m3u8"
    VARIANT="https://media.example.invalid/vods/low/index.m3u8"
    HLS_MASTER=(
        "#EXTM3U\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=400000\nlow/index.m3u8\n"
        "#EXT-X-STREAM-INF:BANDWIDTH=1000000\nhigh/index.m3u8\n"
    )
    MEDIA="#EXTM3U\n#EXT-X-TARGETDURATION:6\n"+(
        "#EXTINF:6.0,\nsegment.ts\n"*11)+"#EXT-X-ENDLIST\n"

    def request(self, payloads):
        def fake(req, timeout=0):
            target=req.full_url
            if target not in payloads:
                raise AssertionError("Unexpected HLS URL: "+target)
            return io.BytesIO(payloads[target].encode("utf-8"))
        return fake

    def test_complete_lowest_bitrate_hls_gives_exact_duration(self):
        with patch("kick_replay.urllib.request.urlopen",side_effect=self.request({
            self.MASTER:self.HLS_MASTER,self.VARIANT:self.MEDIA
        })):
            self.assertEqual(hls_completed_vod_duration(self.MASTER),66)

    def test_live_playlist_is_not_published_as_archived_recording(self):
        unfinished=self.MEDIA.replace("#EXT-X-ENDLIST\n","")
        with patch("kick_replay.urllib.request.urlopen",side_effect=self.request({
            self.MASTER:self.HLS_MASTER,self.VARIANT:unfinished
        })):
            self.assertIsNone(hls_completed_vod_duration(self.MASTER))

    def test_partial_or_invalid_media_length_rejected(self):
        broken=self.MEDIA.replace("#EXTINF:6.0,","#EXTINF:0.0,",1)
        with patch("kick_replay.urllib.request.urlopen",side_effect=self.request({
            self.MASTER:self.HLS_MASTER,self.VARIANT:broken
        })):
            self.assertIsNone(hls_completed_vod_duration(self.MASTER))

    def test_zero_metadata_of_completed_gccx_becomes_publishable(self):
        detail={"title":"ゲームセンターCX","duration":0,
                "created_at":"2026-11-15T10:40:00+09:00",
                "source":self.MASTER,"is_live":False}
        channel={"tvg_id":"kick.gccx2","name":"GCCX"}
        with patch("kick_replay.get_json",return_value=detail), \
             patch("kick_replay.hls_alive",return_value=True), \
             patch("kick_replay.hls_completed_vod_duration",return_value=172798) as get:
            result=normalize_vod("abcd1234-00",detail,channel)
        self.assertEqual(result["duration_seconds"],172798)
        self.assertTrue(result["ready_for_publish"])
        get.assert_called_once_with(self.MASTER)

    def test_live_or_generic_channels_do_not_run_fallback(self):
        detail={"title":"Game Center CX","duration":0,
                "created_at":"2026-11-15T10:40:00+09:00",
                "source":self.MASTER,"is_live":True}
        with patch("kick_replay.get_json",return_value=detail), \
             patch("kick_replay.hls_alive",return_value=True), \
             patch("kick_replay.hls_completed_vod_duration") as get:
            result=normalize_vod("abcd1234-00",detail,{"tvg_id":"kick.gccx2"})
            self.assertFalse(result["ready_for_publish"])
            get.assert_not_called()
        detail["is_live"]=False
        with patch("kick_replay.get_json",return_value=detail), \
             patch("kick_replay.hls_alive",return_value=True), \
             patch("kick_replay.hls_completed_vod_duration") as get:
            result=normalize_vod("abcd1234-00",detail,{"tvg_id":"kick.kodoku"})
            self.assertFalse(result["ready_for_publish"])
            get.assert_not_called()


if __name__=="__main__":
    unittest.main()
