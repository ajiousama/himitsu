from pathlib import Path
import json
import unittest

from youtube import manager


class YouTubeV2StructureTests(unittest.TestCase):
    def test_config_is_single_source_of_truth(self):
        cfg = json.loads(manager.CONFIG.read_text(encoding="utf-8"))
        self.assertEqual(cfg.get("version"), 2)
        general = cfg.get("general") or []
        self.assertGreaterEqual(len(general), 71)
        ids = [x["id"] for x in general]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertNotIn("youtube.kana_tube", set(ids))
        self.assertNotIn("youtube.ehime_mandarin", set(ids))

    def test_logos_or_default_are_valid(self):
        cfg = json.loads(manager.CONFIG.read_text(encoding="utf-8"))
        items = list(cfg["general"]) + list(cfg["special"].values())
        for item in items:
            url = item.get("logo")
            if not url:
                self.assertEqual(
                    manager.logo_url(None).split("?", 1)[0],
                    manager.DEFAULT_YOUTUBE_LOGO,
                )
                continue
            self.assertIn("/youtube/logos/", url)
            rel = url.replace("https://raw.githubusercontent.com/ajiousama/himitsu/main/", "")
            self.assertTrue(Path(rel).is_file(), rel)


    def test_search_based_general_channels_have_guards(self):
        cfg = json.loads(manager.CONFIG.read_text(encoding="utf-8"))
        unguarded = [
            item["id"] for item in cfg["general"]
            if not (item.get("page") or "").strip()
            and not (item.get("direct_url") or "").strip()
            and not (item.get("guard_terms") or [])
        ]
        self.assertEqual(unguarded, [])

    def test_general_output_has_only_configured_ids_and_unique_video_ids(self):
        import re
        cfg = json.loads(manager.CONFIG.read_text(encoding="utf-8"))
        allowed = {item["id"] for item in cfg["general"]}
        text = manager.GENERAL_OUT.read_text(encoding="utf-8-sig", errors="replace")
        lines = text.splitlines()
        seen_video = {}
        stale = []
        duplicate = []
        for i, line in enumerate(lines):
            if not line.startswith("#EXTINF:"):
                continue
            m = re.search(r'tvg-id="([^"]+)"', line)
            if not m:
                continue
            channel_id = m.group(1)
            if channel_id not in allowed:
                stale.append(channel_id)
            j = i + 1
            while j < len(lines) and not lines[j].strip():
                j += 1
            if j >= len(lines):
                continue
            key = manager.video_key(lines[j].strip())
            if key.startswith("video:"):
                if key in seen_video:
                    duplicate.append((seen_video[key], channel_id, key))
                else:
                    seen_video[key] = channel_id
        self.assertEqual(stale, [])
        self.assertEqual(duplicate, [])

    def test_volatile_live_sources_are_health_gated(self):
        cfg = json.loads(manager.CONFIG.read_text(encoding="utf-8"))
        by_id = {item["id"]: item for item in cfg["general"]}

        arashiyama = by_id["youtube.arashiyama_monkeypark"]
        self.assertEqual(
            arashiyama.get("page"),
            "https://www.youtube.com/@ArashiyamaMonkeyparkLivecam",
        )
        self.assertTrue(arashiyama.get("guard_terms"))
        self.assertFalse(arashiyama.get("persistent", False))

        for channel_id in (
            "youtube.matsuyama_kankoko",
            "youtube.matsuyama_kankoko_board",
            "youtube.matsuyama_kankoko_exterior",
        ):
            item = by_id[channel_id]
            self.assertEqual(item.get("probe"), "visual")
            self.assertFalse(item.get("persistent", False))


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

    def test_active_youtube_entries_use_current_numbered_logos(self):
        text = Path("freewifi").read_text(encoding="utf-8-sig", errors="replace")
        for line in text.splitlines():
            if not line.startswith("#EXTINF:") or 'tvg-id="youtube.' not in line:
                continue
            self.assertIn('tvg-logo="', line)
            self.assertIn("/youtube/logos/", line)
            self.assertNotIn("/logos/youtube", line)

    def test_youtube_logo_files_are_not_duplicate_blobs(self):
        logo_root = Path("youtube/logos")
        seen = {}
        import hashlib
        for path in sorted(logo_root.rglob("*")):
            if not path.is_file():
                continue
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertNotIn(
                digest,
                seen,
                f"duplicate logo content: {seen.get(digest)} and {path.as_posix()}",
            )
            seen[digest] = path.as_posix()

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
