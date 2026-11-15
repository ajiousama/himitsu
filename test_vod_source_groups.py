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
    def test_no_duplicate_unsplit_gccx_when_navigation_exists(self):
        content=(ROOT/"vod5/playlist.m3u").read_text(encoding="utf-8-sig")
        lines=content.splitlines()
        entries=[(lines[i],lines[i+1]) for i in range(1,len(lines)-1,2)
                 if lines[i].startswith("#EXTINF:")]
        nav_prefixes={
            match.group(1)
            for inf,_ in entries
            if (match:=re.search(r'tvg-id="kick\.gmcx\.nav\.([^".]+)\.',inf))
        }
        for inf,url in entries:
            raw=re.search(r'tvg-id="kick\.gccx2\.replay\.([^"]+)"',inf)
            if raw:
                self.assertNotIn(raw.group(1),nav_prefixes,
                                 "GCCX raw multi-hour VOD duplicates available short cuts")
            if "未分割" in inf and "kick.gmcx.special" in inf:
                length=re.search(r"[?&]duration=(\d+)",url)
                self.assertFalse(length and int(length.group(1))>=7200,
                                 "Unsplit long GCCX tail was republished")

    def test_visual_episode_49_50_are_separate(self):
        import json
        spec=json.loads((ROOT/"gmcx_visual_cuts.json").read_text(encoding="utf-8"))
        cuts={item.get("episode"):item for item in spec.get("cuts",[])
              if item.get("episode") in (49,50)}
        self.assertEqual(set(cuts),{49,50})
        self.assertEqual(cuts[49]["start_seconds"],13929)
        self.assertEqual(cuts[50]["start_seconds"],17409)
        self.assertEqual(cuts[50]["confidence"],"provisional")

    def test_existing_gccx_archives_have_provisional_titles(self):
        content = (ROOT/"vod5/playlist.m3u").read_text(encoding="utf-8-sig")
        known = ("e4f91158-8a0", "5847ae05-893",
                 "f622346e-33a", "df1386fd-4bd")
        for line in content.splitlines():
            if not line.startswith("#EXTINF"):
                continue
            if any(f'kick.gmcx.nav.{vod}.' in line for vod in known):
                self.assertNotIn("話数未確認", line)
                self.assertTrue(
                    "実映像でゲーム名確認" in line
                    or "放送順・位置から仮推定" in line
                    or "映像OCR候補" in line,
                    "Existing GCCX navigation slice lost its title evidence"
                )

    def test_kick_catalog_still_mirrored(self):
        self.assertEqual((ROOT/"VOD5").read_bytes(),(ROOT/"vod5/playlist.m3u").read_bytes())

if __name__=="__main__":
    unittest.main()
