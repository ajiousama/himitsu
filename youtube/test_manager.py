from pathlib import Path
import json
import unittest

from youtube import manager


class YouTubeV2StructureTests(unittest.TestCase):
    def test_config_is_single_source_of_truth(self):
        cfg = json.loads(manager.CONFIG.read_text(encoding="utf-8"))
        self.assertEqual(cfg.get("version"), 2)
        general = cfg.get("general") or []
        self.assertEqual(len(general), 71)
        self.assertEqual(len({x["id"] for x in general}), 71)
        self.assertNotIn("youtube.kana_tube", {x["id"] for x in general})
        self.assertNotIn("youtube.ehime_mandarin", {x["id"] for x in general})

    def test_all_logos_are_inside_youtube_v2(self):
        cfg = json.loads(manager.CONFIG.read_text(encoding="utf-8"))
        items = list(cfg["general"]) + list(cfg["special"].values())
        for item in items:
            url = item["logo"]
            self.assertIn("/youtube/logos/", url)
            rel = url.replace("https://raw.githubusercontent.com/ajiousama/himitsu/main/", "")
            self.assertTrue(Path(rel).is_file(), rel)

    def test_outputs_are_inside_youtube_v2(self):
        self.assertEqual(manager.GENERAL_OUT.as_posix().split("youtube/")[-1], "output/general.m3u")
        self.assertEqual(manager.KANA_OUT.as_posix().split("youtube/")[-1], "output/kana.m3u")
        self.assertEqual(manager.MANDARIN_OUT.as_posix().split("youtube/")[-1], "output/mandarin.m3u")

    def test_freewifi_has_no_legacy_youtube_logo_paths(self):
        text = Path("freewifi").read_text(encoding="utf-8-sig", errors="replace")
        bad = [
            line for line in text.splitlines()
            if 'tvg-id="youtube.' in line
            and any(x in line for x in ("/logos/youtube/", "/logos/youtube_live/", "/logos/youtube_special/"))
        ]
        self.assertEqual(bad, [])

    def test_rch_and_ehime_catv_do_not_contain_youtube_entries(self):
        text = Path("freewifi").read_text(encoding="utf-8-sig", errors="replace")
        lines = text.splitlines()
        for i, line in enumerate(lines):
            if not line.startswith("#EXTINF:"):
                continue
            group = ""
            import re
            m = re.search(r'group-title="([^"]*)"', line)
            if m:
                group = m.group(1)
            if group not in ("Rch", "愛媛CATV"):
                continue
            self.assertNotIn('tvg-id="youtube.', line)
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j < len(lines):
                self.assertNotIn("youtube.com", lines[j].lower())
                self.assertNotIn("youtu.be", lines[j].lower())


if __name__ == "__main__":
    unittest.main()
