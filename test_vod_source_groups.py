"""Regression: KICK replays stay; retired blog sources do not return."""
from pathlib import Path
import re
import unittest
ROOT = Path(__file__).resolve().parent

def ids(path):
    content=(ROOT / path).read_text(encoding="utf-8-sig")
    rows=[]
    for inf in content.splitlines():
        if inf.startswith("#EXTINF:"):
            ident=re.search(r'tvg-id="([^"]+)"',inf)
            group=re.search(r'group-title="([^"]+)"',inf)
            rows.append((ident.group(1) if ident else "",group.group(1) if group else ""))
    return rows

class VodGroupTests(unittest.TestCase):
    def test_freewifi_kick_only(self):
        rows=ids("freewifi")
        self.assertFalse(any(cid.startswith("newblog.vod.") for cid,g in rows))
        self.assertTrue(any(cid.startswith(("kick.gmcx.","kick.gccx2.replay.")) and g=="KICK系VOD" for cid,g in rows))
    def test_canonical_without_blog_replays(self):
        self.assertFalse(any(cid.startswith("newblog.vod.") for cid,g in ids("tv/playlist.m3u")))
    def test_yovi_retired_blog_absent(self):
        content=(ROOT/"yovi").read_text(encoding="utf-8-sig")
        self.assertFalse(any(cid.startswith("newblog.vod.") for cid,g in ids("yovi")))
        for value in ("haru.charandom.blog/stream/jp/", "0i4neux01.charandom.blog/stream/jp/",
                      "# === NEWBLOG_VOD_START ===", "# === NEWBLOG_VOD_END ==="):
            self.assertNotIn(value,content)
    def test_kick_catalog_still_mirrored(self):
        self.assertEqual((ROOT/"VOD5").read_bytes(),(ROOT/"vod5/playlist.m3u").read_bytes())

if __name__=="__main__":
    unittest.main()
