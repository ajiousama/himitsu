#!/usr/bin/env python3
"""No-network regression tests for the 3-source GCCX BGM cut detector."""
import unittest
from unittest.mock import patch
import numpy as np
import gmcx_bgm_autocut as ac

class BgmCuts(unittest.TestCase):
    def test_signature_offset_in_same_audio(self):
        rng=np.random.default_rng(10)
        source=rng.normal(size=(850,32)).astype(np.float32)
        observed=rng.normal(size=(1700,32)).astype(np.float32)
        # Insert the same signal with an 11-second late onset.
        delay=11
        begin=(ac.WINDOW_BEFORE+delay)*ac.FRAME_RATE
        observed[begin:begin+850]=source
        hit=ac.correlate_one(source,observed)
        self.assertEqual(hit["status"],"matched")
        self.assertAlmostEqual(hit["raw_delay_seconds"],11,delta=.1)
        self.assertGreaterEqual(hit["strong"],3)

    def test_unrelated_sound_not_marked_as_match(self):
        rng=np.random.default_rng(19)
        source=rng.normal(size=(850,32)).astype(np.float32)
        observed=rng.normal(size=(1700,32)).astype(np.float32)
        hit=ac.correlate_one(source,observed)
        self.assertNotEqual(hit["status"],"matched")

    def test_outlier_is_not_considered_a_match(self):
        rng=np.random.default_rng(4)
        source=rng.normal(size=(850,32)).astype(np.float32)
        observed=rng.normal(size=(1700,32)).astype(np.float32)
        for offset, delay in ((10,0),(15,12),(20,-17),(55,41),(60,-40)):
            window=ac.TEMPLATE_LENGTH*ac.FRAME_RATE
            i=offset*ac.FRAME_RATE
            j=(ac.WINDOW_BEFORE+delay+offset)*ac.FRAME_RATE
            observed[j:j+window]=source[i:i+window]
        result=ac.correlate_one(source,observed)
        self.assertNotEqual(result["status"],"matched")

    def test_manual_protected_and_refs_must_agree(self):
        chapters=[]
        for i, ep in enumerate((387,388,389,390)):
            chapters.append({
                "kind":"episode","episode":ep,"start_seconds":i*3480+(8 if i>0 else 0),
                "method":"manual-playback-confirmed" if ep==388 else "manual-playback-offset-propagated",
                "confidence":"confirmed" if ep==388 else "provisional",
            })
        group={"status":"ready","chapters":chapters,"duration_seconds":15000}
        samples={388:{"378":14,"388":7,"398":-2},389:{"378":21,"388":14,"398":5},
                 390:{"378":14,"388":7,"398":19}}
        refs={378:np.zeros((1,32)),388:np.zeros((1,32)),398:np.zeros((1,32))}
        def decode(url,start,seconds):
            ep=next(k for k,x in ((int(c["episode"]),int(c["start_seconds"])) for c in chapters)
                    if start==x-ac.WINDOW_BEFORE)
            return np.array([ep],dtype=np.int32)
        def fingerprint(data):
            return data
        def match(ref,observed):
            ep=int(observed[0]); r=int(ref[0,0])
            delay=samples[ep][str(r)]
            return {"status":"matched","raw_delay_seconds":delay,"mean_similarity":.91,"strong":5}
        refs={k:np.array([[k]],dtype=np.int32) for k in refs}
        with patch.object(ac,"_lowest_hls_variant",return_value="url"),\
             patch.object(ac,"read_audio",side_effect=decode),\
             patch.object(ac,"fingerprint",side_effect=fingerprint),\
             patch.object(ac,"correlate_one",side_effect=match):
            out=ac.analyze_group(group,{"playable":True,"source_url":"url"},refs)
        per={x["episode"]:x for x in out["rows"]}
        self.assertEqual(per[388]["status"],"protected_confirmed")
        self.assertEqual(per[389]["status"],"candidate")
        self.assertEqual(per[389]["proposed_shift_seconds"],7)
        self.assertEqual(per[390]["status"],"disagreement")


    def test_404_requires_shared_external_reference_alignment(self):
        group = {"episode_start":404,"status":"ready","duration_seconds":7500,
                 "chapters":[
                     {"kind":"episode","episode":404,"start_seconds":0,"method":"user-test-broadcast-order","confidence":"provisional"},
                     {"kind":"episode","episode":405,"start_seconds":3480,"method":"user-test-broadcast-order","confidence":"provisional"},
                 ]}
        refs={k:np.array([[k]],dtype=np.float32) for k in (378,388,398)}
        source={"playable":True,"source_url":"https://example.invalid/a.m3u8"}
        no_cal=ac.analyze_group(group,source,refs)
        self.assertEqual(no_cal["status"],"needs_verified_cross_recording_alignment")
        def decode(url, start, duration):
            return np.array([405],dtype=np.float32)
        raw={378:2.0,388:-4.5,398:-4.8}
        def compare(reference,observed):
            ep=int(reference[0,0])
            return {"status":"matched","raw_delay_seconds":raw[ep],
                    "mean_similarity":.92,"strong":5}
        with patch.object(ac,"_lowest_hls_variant",return_value="local"), \
             patch.object(ac,"read_audio",side_effect=decode), \
             patch.object(ac,"fingerprint",side_effect=lambda x:x), \
             patch.object(ac,"correlate_one",side_effect=compare):
            result=ac.analyze_group(group,source,refs,
                                    external_calibration={"378":0.0,"388":-6.5,"398":-6.8})
        self.assertEqual(result["status"],"review_only")
        self.assertEqual(result["calibration_mode"],"cross-recording-manual-anchor")
        self.assertEqual(result["candidates"],1)
        self.assertEqual(result["rows"][0]["proposed_start_seconds"],3482)

if __name__=="__main__":
    unittest.main()
