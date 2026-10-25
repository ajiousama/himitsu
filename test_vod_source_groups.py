#!/usr/bin/env python3
"""Regression: independent FreeWiFi KICK/blog VOD groups survive every rebuild."""
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parent
KICK = "KICK系VOD"
BLOG = "blog系VOD"
TVG = re.compile(r'tvg-id="([^"]+)"')
GROUP = re.compile(r'group-title="([^"]+)"')

def entries(path):
    result=[]
    for line in (ROOT/path).read_text(encoding="utf-8-sig").splitlines():
        if not line.startswith("#EXTINF:"):
            continue
        i=TVG.search(line);g=GROUP.search(line)
        result.append((i.group(1) if i else "",g.group(1) if g else ""))
    return result

def validate(test,path,allowed):
    vod=[]
    for tvgid,group in entries(path):
        test.assertNotEqual(group,"VOD",(path,tvgid))
        if tvgid.startswith("newblog.vod."):
            test.assertEqual(group,BLOG,(path,tvgid))
            test.assertIn(BLOG,allowed)
            vod.append(tvgid)
        elif tvgid.startswith(("kick.gmcx.","kick.gccx2.replay.")):
            test.assertEqual(group,KICK,(path,tvgid))
            test.assertIn(KICK,allowed)
            vod.append(tvgid)
    test.assertTrue(vod,"No replay VOD found in "+path)
    test.assertEqual(len(vod),len(set(vod)),"Duplicate VOD IDs in "+path)
    return set(vod)

class VodGroupTests(unittest.TestCase):
    def test_freewifi_two_groups(self):
        ids=validate(self,"freewifi",{KICK,BLOG})
        self.assertTrue(any(i.startswith("newblog.vod.") for i in ids))
        self.assertTrue(any(i.startswith("kick.") for i in ids))

    def test_catalogs_and_mirrors(self):
        blog=validate(self,"tv/playlist.m3u",{BLOG})
        kick=validate(self,"vod5/playlist.m3u",{KICK})
        self.assertTrue(blog and kick)
        validate(self,"VOD5",{KICK})
        self.assertEqual((ROOT/"VOD5").read_bytes(),(ROOT/"vod5/playlist.m3u").read_bytes())

    def test_freewifi_contains_exact_source_entries(self):
        all_ids=validate(self,"tv/playlist.m3u",{BLOG})
        all_ids.update(validate(self,"vod5/playlist.m3u",{KICK}))
        self.assertEqual(validate(self,"freewifi",{KICK,BLOG}),all_ids)

if __name__=="__main__":
    unittest.main()
