#!/usr/bin/env python3
"""GCCX #404-416 up-to-date playback boundaries."""
import unittest
from kick_gmcx_chapters import make_fixed_test_chapters

VOD={"vod_id":"4b6ff754-ab2f-43b3-bc30-ec3e9f0d8208","duration_seconds":57956}
STARTS={404:10,405:3505,406:7000,407:10495,408:13990,409:17485,410:20896,
        411:24391,412:28755,413:32250,414:35745,415:39240,416:42735}
class Cuts(unittest.TestCase):
    def setUp(self):
        self.rows=make_fixed_test_chapters(VOD,404,416,{})
        self.eps={x["episode"]:x for x in self.rows if x["kind"]=="episode"}
        self.sp={x["special_key"]:x for x in self.rows if x["kind"]=="special"}
    def test_chronology(self):
        self.assertEqual(len(self.rows),16)
        for ep,start in STARTS.items():
            x=self.eps[ep];duration=(3411 if ep==409 else 3457 if ep==411 else 3420 if ep==416 else 3495)
            self.assertEqual((x["start_seconds"],x["duration_seconds"]),(start,duration))
        for x,y in zip(self.rows,self.rows[1:]):
            self.assertEqual(x["stop_seconds"],y["start_seconds"])
    def test_specials(self):
        a=self.sp["404-416-yearend-15min-after-411"]
        b=self.sp["2022-dvdbox19-metal-gear-solid"]
        t=self.sp["404-416-unclassified-tail"]
        self.assertEqual((a["start_seconds"],a["stop_seconds"]),(27848,28755))
        self.assertEqual((b["start_seconds"],b["stop_seconds"]),(46155,56930))
        self.assertEqual(b["method"],"user-playback-confirmed-start-and-end")
        self.assertEqual((t["start_seconds"],t["stop_seconds"]),(56930,57956))
        self.assertTrue(t["cut_candidate"])
if __name__=="__main__":unittest.main()
